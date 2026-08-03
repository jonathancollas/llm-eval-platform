"""Evidence (RCT/RWD/RWE) tenant isolation.

Auth re-enable (#361) scoped campaigns, but /api/evidence never gained
require_tenant checks. Any caller who listed trials/RWD/RWE, opened a
trial by ID, analyzed another tenant's trial, or collected RWD could
read/mutate another tenant's experimental design and production
telemetry aggregates.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, UTC

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-evidence-tenant-isolation-32b")

import importlib.util  # noqa: E402

from core.auth import require_tenant  # noqa: E402
from core.models import (  # noqa: E402
    EvalTrial,
    LLMModel,
    ModelProvider,
    RealWorldDataset,
    RealWorldEvidence,
    TelemetryEvent,
    Tenant,
)

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
EVIDENCE_PATH = os.path.join(BACKEND_DIR, "api", "routers", "evidence.py")
_spec = importlib.util.spec_from_file_location("evidence_tenant_isolation_module", EVIDENCE_PATH)
evidence = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(evidence)


def _setup():
    db_path = f"/tmp/evidence-tenant-{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        tenant_a = Tenant(name="Tenant A", slug=f"ta-{uuid.uuid4().hex[:8]}", api_key_hash="a")
        tenant_b = Tenant(name="Tenant B", slug=f"tb-{uuid.uuid4().hex[:8]}", api_key_hash="b")
        model = LLMModel(
            name="m1",
            provider=ModelProvider.CUSTOM,
            model_id=f"m-{uuid.uuid4().hex[:8]}",
            cost_input_per_1k=0.001,
            cost_output_per_1k=0.002,
        )
        session.add(tenant_a)
        session.add(tenant_b)
        session.add(model)
        session.commit()
        session.refresh(tenant_a)
        session.refresh(tenant_b)
        session.refresh(model)

        trial = EvalTrial(
            tenant_id=tenant_a.id,
            name="Tenant A secret trial",
            hypothesis="TENANT-A-SECRET-HYPOTHESIS",
            arms_json=json.dumps([
                {"name": "control", "model_ids": [model.id], "benchmark_ids": [1]},
                {"name": "treatment", "model_ids": [model.id], "benchmark_ids": [1]},
            ]),
            results_json=json.dumps({
                "arms": {
                    "control": {"n": 10, "mean": 0.4, "std": 0.1, "min": 0.2, "max": 0.6},
                    "treatment": {"n": 10, "mean": 0.8, "std": 0.1, "min": 0.6, "max": 0.9},
                }
            }),
            p_value=0.01,
            campaign_ids="[]",
        )
        rwd = RealWorldDataset(
            tenant_id=tenant_a.id,
            name="Tenant A secret RWD",
            model_id=model.id,
            total_events=42,
            avg_score=0.77,
            safety_flag_rate=0.12,
        )
        session.add(trial)
        session.add(rwd)
        session.commit()
        session.refresh(trial)
        session.refresh(rwd)

        rwe = RealWorldEvidence(
            tenant_id=tenant_a.id,
            name="Tenant A secret RWE",
            trial_id=trial.id,
            rwd_dataset_id=rwd.id,
            rct_score=0.6,
            rwd_score=0.77,
            concordance=0.78,
            evidence_grade="B",
            conclusion="TENANT-A-SECRET-CONCLUSION",
        )
        session.add(
            TelemetryEvent(
                tenant_id=tenant_a.id,
                model_id=model.id,
                event_type="inference",
                score=0.91,
                latency_ms=100,
                safety_flag="injection_detected",
                timestamp=datetime.now(UTC),
            )
        )
        session.add(rwe)
        session.commit()
        session.refresh(rwe)

        ids = {
            "tenant_a_slug": tenant_a.slug,
            "tenant_b_slug": tenant_b.slug,
            "tenant_a_id": tenant_a.id,
            "tenant_b_id": tenant_b.id,
            "model_id": model.id,
            "trial_a_id": trial.id,
            "rwd_a_id": rwd.id,
            "rwe_a_id": rwe.id,
        }

    app = FastAPI()
    app.include_router(evidence.router)

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
                is_active=tenant.is_active,
            )

    app.dependency_overrides[evidence.get_session] = _get_session_override
    app.dependency_overrides[evidence.require_tenant] = _require_tenant_override
    app.dependency_overrides[require_tenant] = _require_tenant_override

    return TestClient(app), ids, engine


def test_list_trials_hides_other_tenant():
    client, ids, _engine = _setup()
    r = client.get("/evidence/trials", headers={"X-Tenant-Key": ids["tenant_b_slug"]})
    assert r.status_code == 200
    assert r.json()["trials"] == []
    assert "TENANT-A-SECRET-HYPOTHESIS" not in r.text


def test_owner_can_list_own_trials():
    client, ids, _engine = _setup()
    r = client.get("/evidence/trials", headers={"X-Tenant-Key": ids["tenant_a_slug"]})
    assert r.status_code == 200
    body = r.json()
    assert len(body["trials"]) == 1
    assert body["trials"][0]["hypothesis"].startswith("TENANT-A-SECRET")


def test_get_trial_cross_tenant_returns_404():
    client, ids, _engine = _setup()
    r = client.get(
        f"/evidence/trials/{ids['trial_a_id']}",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 404
    assert "TENANT-A-SECRET" not in r.text


def test_analyze_trial_cross_tenant_returns_404():
    client, ids, _engine = _setup()
    r = client.post(
        f"/evidence/trials/{ids['trial_a_id']}/analyze",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 404


def test_list_rwd_hides_other_tenant():
    client, ids, _engine = _setup()
    r = client.get("/evidence/rwd", headers={"X-Tenant-Key": ids["tenant_b_slug"]})
    assert r.status_code == 200
    assert r.json()["datasets"] == []


def test_rwd_collect_does_not_use_other_tenant_telemetry():
    client, ids, _engine = _setup()
    r = client.post(
        f"/evidence/rwd/collect?model_id={ids['model_id']}&hours=168",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 400
    assert "No telemetry events" in r.json()["detail"]


def test_list_rwe_hides_other_tenant():
    client, ids, _engine = _setup()
    r = client.get("/evidence/rwe", headers={"X-Tenant-Key": ids["tenant_b_slug"]})
    assert r.status_code == 200
    assert r.json()["evidence"] == []
    assert "TENANT-A-SECRET-CONCLUSION" not in r.text


def test_get_rwe_cross_tenant_returns_404():
    client, ids, _engine = _setup()
    r = client.get(
        f"/evidence/rwe/{ids['rwe_a_id']}",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 404


def test_synthesize_cross_tenant_trial_returns_404():
    client, ids, _engine = _setup()
    r = client.post(
        f"/evidence/rwe/synthesize?trial_id={ids['trial_a_id']}&rwd_dataset_id={ids['rwd_a_id']}",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 404


def test_create_trial_stamps_tenant():
    client, ids, engine = _setup()
    r = client.post(
        "/evidence/trials",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
        json={
            "name": "Tenant B trial",
            "hypothesis": "B-only",
            "arms": [
                {"name": "a", "model_ids": [ids["model_id"]], "benchmark_ids": [1]},
                {"name": "b", "model_ids": [ids["model_id"]], "benchmark_ids": [1]},
            ],
        },
    )
    assert r.status_code == 200
    trial_id = r.json()["trial_id"]
    with Session(engine) as session:
        trial = session.get(EvalTrial, trial_id)
        assert trial is not None
        assert trial.tenant_id == ids["tenant_b_id"]
