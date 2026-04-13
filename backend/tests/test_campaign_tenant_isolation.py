import os
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.routers import campaigns  # noqa: E402
from core.models import Benchmark, BenchmarkType, LLMModel, ModelProvider, Tenant  # noqa: E402


def _setup_app():
    db_path = Path("/tmp") / f"tenant-isolation-{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        tenant_a = Tenant(name="Tenant A", slug="tenant-a", api_key_hash="a")
        tenant_b = Tenant(name="Tenant B", slug="tenant-b", api_key_hash="b")
        model = LLMModel(name="m1", provider=ModelProvider.CUSTOM, model_id=f"m-{uuid.uuid4().hex[:8]}")
        benchmark = Benchmark(name=f"b-{uuid.uuid4().hex[:8]}", type=BenchmarkType.CUSTOM, is_builtin=False)
        session.add(tenant_a)
        session.add(tenant_b)
        session.add(model)
        session.add(benchmark)
        session.commit()
        session.refresh(tenant_a)
        session.refresh(tenant_b)
        session.refresh(model)
        session.refresh(benchmark)

    app = FastAPI()
    app.include_router(campaigns.router)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    def _require_tenant_override(tenant_key: str | None = Header(default=None, alias="X-Tenant-Key")):
        if not tenant_key:
            raise HTTPException(status_code=401, detail="X-Tenant-Key header required.")
        with Session(engine) as session:
            tenant = session.exec(select(Tenant).where(Tenant.slug == tenant_key)).first()
            if not tenant:
                raise HTTPException(status_code=401, detail="Invalid tenant.")
            return tenant

    app.dependency_overrides[campaigns.get_session] = _get_session_override
    app.dependency_overrides[campaigns.require_tenant] = _require_tenant_override
    return app, model.id, benchmark.id


def test_tenant_a_cannot_read_tenant_b_campaigns():
    app, model_id, benchmark_id = _setup_app()
    client = TestClient(app)

    create_resp = client.post(
        "/campaigns/",
        headers={"X-Tenant-Key": "tenant-a"},
        json={
            "name": "A campaign",
            "description": "",
            "model_ids": [model_id],
            "benchmark_ids": [benchmark_id],
            "seed": 42,
            "max_samples": 1,
            "temperature": 0.0,
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    campaign_id = create_resp.json()["id"]

    list_b_resp = client.get("/campaigns/", headers={"X-Tenant-Key": "tenant-b"})
    assert list_b_resp.status_code == 200
    assert list_b_resp.json() == []

    get_b_resp = client.get(f"/campaigns/{campaign_id}", headers={"X-Tenant-Key": "tenant-b"})
    assert get_b_resp.status_code == 404
