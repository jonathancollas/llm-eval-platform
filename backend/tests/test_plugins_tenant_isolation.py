"""Plugins export tenant isolation.

POST /plugins/export/{run_id} previously loaded EvalRun by ID with no tenant or
campaign check, so any caller who knew a run ID could export another tenant's
score / model / benchmark metadata.
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
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-plugins-tenant-isolation-32b")

from core.auth import require_tenant  # noqa: E402
from core.models import (  # noqa: E402
    Benchmark,
    BenchmarkType,
    Campaign,
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
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


plugins = _load_module("plugins_tenant_isolation_module", "api/routers/plugins.py")


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
            score=0.88,
            num_items=3,
        )
        session.add(run_a)
        session.commit()
        session.refresh(run_a)

        return {
            "tenant_a_slug": tenant_a.slug,
            "tenant_b_slug": tenant_b.slug,
            "run_a_id": run_a.id,
            "score": 0.88,
        }


def _setup():
    db_path = f"/tmp/plugins-tenant-{uuid.uuid4().hex}.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    ids = _seed(engine)

    app = FastAPI()
    app.include_router(plugins.router)

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

    app.dependency_overrides[plugins.get_session] = _get_session_override
    app.dependency_overrides[plugins.require_tenant] = _require_tenant_override
    app.dependency_overrides[require_tenant] = _require_tenant_override

    return TestClient(app), engine, ids


def test_owner_can_export_run():
    client, _engine, ids = _setup()
    r = client.post(
        f"/plugins/export/{ids['run_a_id']}",
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
        params={"format": "json_ld"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "export" in body
    assert "0.88" in r.text or "0.88" in str(body)


def test_other_tenant_cannot_export_run():
    client, _engine, ids = _setup()
    r = client.post(
        f"/plugins/export/{ids['run_a_id']}",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
        params={"format": "json_ld"},
    )
    assert r.status_code == 404
    assert "0.88" not in r.text
