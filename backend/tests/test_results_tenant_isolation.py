import os
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.routers import results  # noqa: E402
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


def _setup_app():
    db_path = Path("/tmp") / f"results-tenant-isolation-{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        tenant_a = Tenant(name="Tenant A", slug="tenant-a", api_key_hash="a")
        tenant_b = Tenant(name="Tenant B", slug="tenant-b", api_key_hash="b")
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
        session.refresh(model)
        session.refresh(benchmark)

        campaign = Campaign(
            tenant_id=tenant_a.id,
            name="A campaign",
            description="",
            model_ids=f"[{model.id}]",
            benchmark_ids=f"[{benchmark.id}]",
            status=JobStatus.COMPLETED,
            progress=1.0,
        )
        session.add(campaign)
        session.commit()
        session.refresh(campaign)

        run = EvalRun(
            campaign_id=campaign.id,
            model_id=model.id,
            benchmark_id=benchmark.id,
            status=JobStatus.COMPLETED,
            score=0.8,
            num_items=1,
            total_latency_ms=120,
        )
        session.add(run)
        session.commit()
        session.refresh(run)

        result = EvalResult(
            run_id=run.id,
            item_index=0,
            prompt="secret prompt",
            response="secret response",
            expected="expected",
            score=0.8,
            latency_ms=120,
        )
        session.add(result)
        session.commit()
        session.refresh(result)

        ids = {
            "campaign_id": campaign.id,
            "run_id": run.id,
            "result_id": result.id,
        }

    app = FastAPI()
    app.include_router(results.router)

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

    app.dependency_overrides[results.get_session] = _get_session_override
    app.dependency_overrides[results.require_tenant] = _require_tenant_override
    return app, ids


def test_dashboard_cache_does_not_bypass_tenant_access():
    app, ids = _setup_app()
    client = TestClient(app)

    owner_resp = client.get(
        f"/results/campaign/{ids['campaign_id']}/dashboard",
        headers={"X-Tenant-Key": "tenant-a"},
    )
    assert owner_resp.status_code == 200, owner_resp.text
    assert owner_resp.json()["campaign_name"] == "A campaign"

    other_resp = client.get(
        f"/results/campaign/{ids['campaign_id']}/dashboard",
        headers={"X-Tenant-Key": "tenant-b"},
    )
    assert other_resp.status_code == 404


def test_run_items_require_campaign_tenant_access():
    app, ids = _setup_app()
    client = TestClient(app)

    owner_resp = client.get(
        f"/results/run/{ids['run_id']}/items",
        headers={"X-Tenant-Key": "tenant-a"},
    )
    assert owner_resp.status_code == 200, owner_resp.text
    assert owner_resp.json()["items"][0]["prompt"] == "secret prompt"

    other_resp = client.get(
        f"/results/run/{ids['run_id']}/items",
        headers={"X-Tenant-Key": "tenant-b"},
    )
    assert other_resp.status_code == 404


def test_human_review_mutation_requires_result_tenant_access():
    app, ids = _setup_app()
    client = TestClient(app)

    other_resp = client.patch(
        f"/results/{ids['result_id']}/human-review",
        headers={"X-Tenant-Key": "tenant-b"},
        json={"verdict": False},
    )
    assert other_resp.status_code == 404
