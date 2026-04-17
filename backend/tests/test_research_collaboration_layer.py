import importlib.util
import os
import sys
import types
import uuid
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.models import Benchmark, BenchmarkType, LLMModel, ModelProvider, Tenant  # noqa: E402

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
CAMPAIGNS_PATH = os.path.join(BACKEND_DIR, "api", "routers", "campaigns.py")
BENCHMARKS_PATH = os.path.join(BACKEND_DIR, "api", "routers", "benchmarks.py")


def _load_campaigns_router():
    fake_job_queue = types.ModuleType("core.job_queue")
    fake_job_queue.submit_campaign = lambda *_args, **_kwargs: "fake-task"
    fake_job_queue.cancel_campaign = lambda *_args, **_kwargs: True
    fake_job_queue.is_running = lambda *_args, **_kwargs: False
    fake_job_queue.get_queue_status = lambda *_args, **_kwargs: {"mode": "celery"}
    sys.modules["core.job_queue"] = fake_job_queue

    spec = importlib.util.spec_from_file_location("campaigns_router_module", CAMPAIGNS_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_benchmarks_router():
    spec = importlib.util.spec_from_file_location("benchmarks_router_module", BENCHMARKS_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _setup_app():
    db_path = Path("/tmp") / f"research-collab-{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        tenant_a = Tenant(name=f"Tenant A {uuid.uuid4().hex[:6]}", slug=f"tenant-a-{uuid.uuid4().hex[:6]}", api_key_hash="a")
        tenant_b = Tenant(name=f"Tenant B {uuid.uuid4().hex[:6]}", slug=f"tenant-b-{uuid.uuid4().hex[:6]}", api_key_hash="b")
        model = LLMModel(name="Shared Model", provider=ModelProvider.CUSTOM, model_id=f"provider/{uuid.uuid4().hex[:8]}")
        benchmark_a = Benchmark(name=f"bench-{uuid.uuid4().hex[:8]}", type=BenchmarkType.CUSTOM, is_builtin=False, metric="accuracy")
        benchmark_b = Benchmark(name=f"bench-{uuid.uuid4().hex[:8]}", type=BenchmarkType.SAFETY, is_builtin=False, metric="pass_rate")
        session.add(tenant_a)
        session.add(tenant_b)
        session.add(model)
        session.add(benchmark_a)
        session.add(benchmark_b)
        session.commit()
        session.refresh(tenant_a)
        session.refresh(tenant_b)
        session.refresh(model)
        session.refresh(benchmark_a)
        session.refresh(benchmark_b)

    campaigns = _load_campaigns_router()
    benchmarks = _load_benchmarks_router()

    app = FastAPI()
    app.include_router(campaigns.router)
    app.include_router(benchmarks.router)

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
    app.dependency_overrides[benchmarks.get_session] = _get_session_override
    app.dependency_overrides[campaigns.require_tenant] = _require_tenant_override

    return app, tenant_a, tenant_b, model, benchmark_a, benchmark_b


def test_campaign_sharing_comments_reviews_and_bundle_import():
    app, tenant_a, tenant_b, model, benchmark_a, _ = _setup_app()
    client = TestClient(app)

    create_resp = client.post(
        "/campaigns/",
        headers={"X-Tenant-Key": tenant_a.slug},
        json={
            "name": "Shared Campaign",
            "description": "cross-lab evaluation",
            "model_ids": [model.id],
            "benchmark_ids": [benchmark_a.id],
            "seed": 42,
            "temperature": 0.1,
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    campaign_id = create_resp.json()["id"]

    share_resp = client.post(
        f"/campaigns/{campaign_id}/share",
        headers={"X-Tenant-Key": tenant_a.slug},
        json={"visibility": "shared", "collaborator_tenant_ids": [tenant_b.id]},
    )
    assert share_resp.status_code == 200, share_resp.text
    assert share_resp.json()["visibility"] == "shared"

    shared_list_resp = client.get("/campaigns/shared/available", headers={"X-Tenant-Key": tenant_b.slug})
    assert shared_list_resp.status_code == 200, shared_list_resp.text
    assert any(c["id"] == campaign_id for c in shared_list_resp.json())

    comment_resp = client.post(
        f"/campaigns/{campaign_id}/comments",
        headers={"X-Tenant-Key": tenant_b.slug},
        json={"author": "Peer Reviewer", "message": "Please add additional robustness trials."},
    )
    assert comment_resp.status_code == 200, comment_resp.text

    review_resp = client.post(
        f"/campaigns/{campaign_id}/reviews",
        headers={"X-Tenant-Key": tenant_b.slug},
        json={"reviewer": "Peer Reviewer", "decision": "request_changes", "summary": "Need broader benchmark coverage."},
    )
    assert review_resp.status_code == 200, review_resp.text
    assert review_resp.json()["review_state"] == "changes_requested"

    export_resp = client.get(f"/campaigns/{campaign_id}/bundle/export", headers={"X-Tenant-Key": tenant_b.slug})
    assert export_resp.status_code == 200, export_resp.text
    bundle = export_resp.json()
    assert bundle["campaign"]["name"] == "Shared Campaign"

    import_resp = client.post(
        "/campaigns/bundle/import",
        headers={"X-Tenant-Key": tenant_b.slug},
        json={"bundle": bundle, "import_collaboration": True},
    )
    assert import_resp.status_code == 201, import_resp.text
    assert import_resp.json()["name"] == "Shared Campaign"


def test_benchmark_pack_publishing_and_changelog_versions():
    app, _tenant_a, _tenant_b, _model, benchmark_a, benchmark_b = _setup_app()
    client = TestClient(app)

    v1_resp = client.post(
        "/benchmarks/packs",
        json={
            "name": "AISI Safety Pack",
            "slug": "aisi-safety-pack",
            "version": "1.0.0",
            "publisher": "AISI Lab",
            "family": "aisi",
            "changelog": "Initial release.",
            "benchmark_ids": [benchmark_a.id],
            "is_public": True,
        },
    )
    assert v1_resp.status_code == 201, v1_resp.text

    v2_resp = client.post(
        "/benchmarks/packs",
        json={
            "name": "AISI Safety Pack",
            "slug": "aisi-safety-pack",
            "version": "1.1.0",
            "publisher": "AISI Lab",
            "family": "aisi",
            "changelog": "Added robustness benchmark.",
            "benchmark_ids": [benchmark_a.id, benchmark_b.id],
            "is_public": True,
        },
    )
    assert v2_resp.status_code == 201, v2_resp.text

    list_resp = client.get("/benchmarks/packs?family=aisi")
    assert list_resp.status_code == 200, list_resp.text
    assert len(list_resp.json()["packs"]) >= 2

    details_resp = client.get("/benchmarks/packs/aisi-safety-pack")
    assert details_resp.status_code == 200, details_resp.text
    payload = details_resp.json()
    assert payload["latest_version"] == "1.1.0"
    assert len(payload["versions"]) == 2
    assert payload["changelog"][0]["version"] == "1.1.0"
