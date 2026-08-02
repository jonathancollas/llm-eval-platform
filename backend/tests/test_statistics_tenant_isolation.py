"""Statistics router tenant isolation for run-scoped endpoints.

/statistics/compare-runs, /run/{id}/confidence, /run/{id}/fingerprint, and
/validate-reproducibility loaded EvalRun/EvalResult by ID with no campaign
tenant check. Knowing another tenant's run ID was enough to read scores and
experiment config fingerprints.
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
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-statistics-tenant-isolation-32b")

from core.auth import require_tenant  # noqa: E402
from core.models import (  # noqa: E402
    Benchmark,
    BenchmarkType,
    Campaign,
    EvalResult,
    EvalRun,
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
    # Ensure package context for relative imports inside the module.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


statistics = _load_module("statistics_tenant_isolation_module", "api/routers/statistics.py")


def _seed(engine):
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
        benchmark = Benchmark(
            name=f"b-{uuid.uuid4().hex[:8]}",
            type=BenchmarkType.CUSTOM,
            is_builtin=False,
        )
        session.add(tenant_a)
        session.add(tenant_b)
        session.add(model)
        session.add(benchmark)
        session.commit()
        session.refresh(tenant_a)
        session.refresh(tenant_b)
        session.refresh(model)
        session.refresh(benchmark)

        campaign_a = Campaign(
            name="Secret campaign A",
            description="tenant-a-only",
            model_ids=f"[{model.id}]",
            benchmark_ids=f"[{benchmark.id}]",
            tenant_id=tenant_a.id,
            status=JobStatus.COMPLETED,
        )
        session.add(campaign_a)
        session.commit()
        session.refresh(campaign_a)

        run_a = EvalRun(
            campaign_id=campaign_a.id,
            model_id=model.id,
            benchmark_id=benchmark.id,
            status=JobStatus.COMPLETED,
            score=0.91,
            num_items=2,
            run_context_json='{"seed": 7, "temperature": 0.0}',
        )
        session.add(run_a)
        session.commit()
        session.refresh(run_a)

        session.add(
            EvalResult(
                run_id=run_a.id,
                item_index=0,
                prompt="secret-prompt-a",
                response="secret-response-a",
                score=0.9,
            )
        )
        session.add(
            EvalResult(
                run_id=run_a.id,
                item_index=1,
                prompt="secret-prompt-b",
                response="secret-response-b",
                score=0.92,
            )
        )
        session.commit()

        return {
            "tenant_a_slug": tenant_a.slug,
            "tenant_b_slug": tenant_b.slug,
            "run_a_id": run_a.id,
        }


def _setup():
    db_path = f"/tmp/statistics-tenant-{uuid.uuid4().hex}.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    ids = _seed(engine)

    app = FastAPI()
    app.include_router(statistics.router, prefix="/api")

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

    app.dependency_overrides[statistics.get_session] = _get_session_override
    app.dependency_overrides[statistics.require_tenant] = _require_tenant_override
    app.dependency_overrides[require_tenant] = _require_tenant_override

    return TestClient(app), engine, ids


def test_owner_can_read_run_confidence():
    client, _engine, ids = _setup()
    r = client.get(
        f"/api/statistics/run/{ids['run_a_id']}/confidence",
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["run_id"] == ids["run_a_id"]
    assert body["n_items"] == 2


def test_other_tenant_cannot_read_run_confidence():
    client, _engine, ids = _setup()
    r = client.get(
        f"/api/statistics/run/{ids['run_a_id']}/confidence",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 404


def test_other_tenant_cannot_read_run_fingerprint():
    client, _engine, ids = _setup()
    r = client.get(
        f"/api/statistics/run/{ids['run_a_id']}/fingerprint",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 404


def test_other_tenant_cannot_compare_runs():
    client, _engine, ids = _setup()
    r = client.post(
        "/api/statistics/compare-runs",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
        json={"run_id_a": ids["run_a_id"], "run_id_b": ids["run_a_id"]},
    )
    assert r.status_code == 404


def test_other_tenant_cannot_validate_reproducibility():
    client, _engine, ids = _setup()
    r = client.post(
        "/api/statistics/validate-reproducibility",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
        json={"run_id_a": ids["run_a_id"], "run_id_b": ids["run_a_id"]},
    )
    assert r.status_code == 404
