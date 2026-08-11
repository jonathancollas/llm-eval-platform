"""Forecasting router tenant isolation for in-memory stores + campaign metrics.

Auth re-enable (#361) scoped campaigns, but /api/forecasting kept process-global
``_calibration_store`` / ``_frontier_leaderboard`` with no require_tenant, and
``GET /metrics/{run_id}`` loaded AgentTrajectory by campaign_id with no ownership
check.

Trigger:
  1. Tenant A POST /forecasting/calibration/record with secret predicted/actual
     scores → Tenant B GET /forecasting/calibration reads them.
  2. Tenant A POST /forecasting/metrics/compute → Tenant B GET
     /forecasting/metrics/leaderboard sees A's frontier grades.
  3. Tenant A owns campaign with trajectories → Tenant B GET
     /forecasting/metrics/{campaign_id} learns trajectory presence/count.

Impact: Cross-tenant disclosure (and leaderboard poisoning) of forecasting /
frontier metrics; campaign existence oracle via trajectory metrics.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import uuid

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-forecasting-tenant-isolation-32b")

from core.auth import require_tenant  # noqa: E402
from core.models import (  # noqa: E402
    AgentTrajectory,
    Campaign,
    JobStatus,
    LLMModel,
    ModelProvider,
    Tenant,
)

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")


def _load_module(name: str, rel_path: str):
    path = os.path.join(BACKEND_DIR, rel_path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


forecasting = _load_module(
    "forecasting_tenant_isolation_module",
    "api/routers/forecasting.py",
)


def _metrics_body(model_name: str = "secret-model-a") -> dict:
    return {
        "model_name": model_name,
        "steps": [
            {"tokens": 10, "is_error": False, "is_retry": False, "capability": "reasoning"},
            {"tokens": 12, "is_error": True, "is_retry": True, "capability": "reasoning"},
            {"tokens": 8, "is_error": False, "is_retry": False, "capability": "reasoning"},
        ],
        "benchmark_scores": {"mmlu": 0.81, "gsm8k": 0.77},
        "capability_score": 0.8,
        "propensity_score": 0.2,
        "safety_score": 0.9,
        "max_steps": 10,
        "task_completed": True,
        "version": "v-secret-a",
    }


def _setup():
    db_path = f"/tmp/forecasting-tenant-{uuid.uuid4().hex}.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        tenant_a = Tenant(
            name="Tenant A",
            slug=f"ta-{uuid.uuid4().hex[:8]}",
            api_key_hash="hash-a",
        )
        tenant_b = Tenant(
            name="Tenant B",
            slug=f"tb-{uuid.uuid4().hex[:8]}",
            api_key_hash="hash-b",
        )
        model = LLMModel(
            name="m1",
            provider=ModelProvider.CUSTOM,
            model_id=f"m-{uuid.uuid4().hex[:8]}",
        )
        session.add(tenant_a)
        session.add(tenant_b)
        session.add(model)
        session.commit()
        session.refresh(tenant_a)
        session.refresh(tenant_b)
        session.refresh(model)

        campaign_a = Campaign(
            name="Secret campaign A",
            description="tenant-a-only",
            model_ids=f"[{model.id}]",
            benchmark_ids="[]",
            tenant_id=tenant_a.id,
            status=JobStatus.COMPLETED,
        )
        session.add(campaign_a)
        session.commit()
        session.refresh(campaign_a)

        session.add(
            AgentTrajectory(
                campaign_id=campaign_a.id,
                model_id=model.id,
                task_description="TENANT-A-SECRET-TASK",
                num_steps=3,
                task_completed=True,
                final_answer="secret-final-answer",
            )
        )
        session.commit()

        ids = {
            "tenant_a_slug": tenant_a.slug,
            "tenant_b_slug": tenant_b.slug,
            "tenant_a_id": tenant_a.id,
            "tenant_b_id": tenant_b.id,
            "campaign_a_id": campaign_a.id,
        }

    forecasting._reset_stores()

    # Seed Tenant A's calibration + leaderboard directly (same shape as API writes).
    forecasting._calibration_for(ids["tenant_a_id"]).setdefault("reasoning", []).append(
        {
            "capability": "reasoning",
            "predicted_score": 0.91,
            "actual_score": 0.88,
            "absolute_error": 0.03,
            "horizon_label": "TENANT-A-SECRET-HORIZON",
            "recorded_at": "2026-08-11T00:00:00+00:00",
            "tenant_id": ids["tenant_a_id"],
        }
    )
    forecasting._leaderboard_for(ids["tenant_a_id"]).setdefault("secret-model-a", []).append(
        {
            "model_name": "secret-model-a",
            "composite_frontier_score": 0.93,
            "frontier_grade": "A+",
            "frontier_grade_interpretation": "TENANT-A-SECRET-GRADE",
            "autonomy": {"value": 0.9},
            "adaptivity": {"value": 0.8},
            "efficiency": {"value": 0.7},
            "generalization": {"value": 0.85},
            "created_at": "2026-08-11T00:00:00+00:00",
            "version": "v-secret-a",
            "tenant_id": ids["tenant_a_id"],
        }
    )

    app = FastAPI()
    app.include_router(forecasting.router, prefix="/api")

    def _get_session_override():
        with Session(engine) as session:
            yield session

    def _require_tenant_override(
        tenant_key: str | None = Header(default=None, alias="X-Tenant-Key"),
    ):
        if not tenant_key:
            raise HTTPException(status_code=401, detail="X-Tenant-Key header required.")
        with Session(engine) as session:
            tenant = session.exec(select(Tenant).where(Tenant.slug == tenant_key)).first()
            if not tenant:
                raise HTTPException(status_code=401, detail="Invalid tenant.")
            return Tenant(
                id=tenant.id,
                name=tenant.name,
                slug=tenant.slug,
                api_key_hash=tenant.api_key_hash,
            )

    from core.database import get_session

    app.dependency_overrides[get_session] = _get_session_override
    app.dependency_overrides[require_tenant] = _require_tenant_override
    app.dependency_overrides[forecasting.require_tenant] = _require_tenant_override

    client = TestClient(app)
    return client, ids, engine


def test_calibration_hides_other_tenant_records():
    client, ids, _ = _setup()
    r = client.get(
        "/api/forecasting/calibration",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["records"] == []
    assert "TENANT-A-SECRET-HORIZON" not in str(body)


def test_owner_can_see_own_calibration():
    client, ids, _ = _setup()
    r = client.get(
        "/api/forecasting/calibration",
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["records"]) == 1
    assert "TENANT-A-SECRET-HORIZON" in str(body)


def test_calibration_record_stays_in_calling_tenant():
    client, ids, _ = _setup()
    r = client.post(
        "/api/forecasting/calibration/record",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
        json={
            "capability": "reasoning",
            "predicted_score": 0.5,
            "actual_score": 0.4,
            "horizon_label": "TENANT-B-OWN-HORIZON",
        },
    )
    assert r.status_code == 200

    r_a = client.get(
        "/api/forecasting/calibration",
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
    )
    r_b = client.get(
        "/api/forecasting/calibration",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r_a.status_code == 200 and r_b.status_code == 200
    assert "TENANT-A-SECRET-HORIZON" in str(r_a.json())
    assert "TENANT-B-OWN-HORIZON" in str(r_b.json())
    assert "TENANT-A-SECRET-HORIZON" not in str(r_b.json())
    assert "TENANT-B-OWN-HORIZON" not in str(r_a.json())


def test_leaderboard_hides_other_tenant_entries():
    client, ids, _ = _setup()
    r = client.get(
        "/api/forecasting/metrics/leaderboard",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert "secret-model-a" not in str(body)
    assert "TENANT-A-SECRET-GRADE" not in str(body)


def test_owner_can_see_own_leaderboard():
    client, ids, _ = _setup()
    r = client.get(
        "/api/forecasting/metrics/leaderboard",
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["rows"][0]["model_name"] == "secret-model-a"
    assert "TENANT-A-SECRET-GRADE" in str(body)


def test_metrics_compute_does_not_poison_other_tenant_leaderboard():
    client, ids, _ = _setup()
    r = client.post(
        "/api/forecasting/metrics/compute",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
        json=_metrics_body("tenant-b-model"),
    )
    assert r.status_code == 200

    r_a = client.get(
        "/api/forecasting/metrics/leaderboard",
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
    )
    r_b = client.get(
        "/api/forecasting/metrics/leaderboard",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r_a.status_code == 200 and r_b.status_code == 200
    assert "secret-model-a" in str(r_a.json())
    assert "tenant-b-model" in str(r_b.json())
    assert "tenant-b-model" not in str(r_a.json())
    assert "secret-model-a" not in str(r_b.json())


def test_leaderboard_trend_other_tenant_is_404():
    client, ids, _ = _setup()
    r = client.get(
        "/api/forecasting/metrics/leaderboard/trend/secret-model-a",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 404


def test_run_metrics_other_tenant_campaign_is_404():
    client, ids, _ = _setup()
    r = client.get(
        f"/api/forecasting/metrics/{ids['campaign_a_id']}",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 404
    assert "n_trajectories" not in r.json()


def test_owner_can_read_own_run_metrics():
    client, ids, _ = _setup()
    r = client.get(
        f"/api/forecasting/metrics/{ids['campaign_a_id']}",
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["n_trajectories"] == 1
    assert body["run_id"] == ids["campaign_a_id"]
