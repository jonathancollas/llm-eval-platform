"""Research OS tenant isolation — workspaces and experiment manifests.

Auth re-enable (#361) scoped campaigns, but /api/research/* never gained
require_tenant / ownership checks. Private hypotheses, protocols, and
campaign-derived manifests were world-readable by numeric ID.
"""
import importlib.util
import os
import sys
import uuid

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-research-tenant-isolation-32")

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
RESEARCH_PATH = os.path.join(BACKEND_DIR, "api", "routers", "research.py")
_spec = importlib.util.spec_from_file_location("research_tenant_isolation_module", RESEARCH_PATH)
research = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(research)


def _setup():
    db_path = f"/tmp/research-tenant-{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        tenant_a = Tenant(name="Tenant A", slug=f"ta-{uuid.uuid4().hex[:8]}", api_key_hash="a")
        tenant_b = Tenant(name="Tenant B", slug=f"tb-{uuid.uuid4().hex[:8]}", api_key_hash="b")
        model = LLMModel(
            name="m1",
            provider=ModelProvider.CUSTOM,
            model_id=f"m-{uuid.uuid4().hex[:8]}",
        )
        benchmark = Benchmark(
            name=f"b-{uuid.uuid4().hex[:8]}",
            type=BenchmarkType.CUSTOM,
            is_builtin=False,
            dataset_path="secret/path.jsonl",
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

        campaign = Campaign(
            name="Secret campaign",
            description="tenant A only",
            model_ids=f"[{model.id}]",
            benchmark_ids=f"[{benchmark.id}]",
            tenant_id=tenant_a.id,
            status=JobStatus.COMPLETED,
        )
        session.add(campaign)
        session.commit()
        session.refresh(campaign)

        run = EvalRun(
            campaign_id=campaign.id,
            model_id=model.id,
            benchmark_id=benchmark.id,
            status=JobStatus.COMPLETED,
            score=0.91,
            num_items=3,
        )
        session.add(run)
        session.commit()
        campaign_id = campaign.id
        tenant_a_slug = tenant_a.slug
        tenant_b_slug = tenant_b.slug

    app = FastAPI()
    app.include_router(research.router)

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
            # Detach a plain Tenant copy so the request session can close.
            return Tenant(
                id=tenant.id,
                name=tenant.name,
                slug=tenant.slug,
                api_key_hash=tenant.api_key_hash,
                is_active=tenant.is_active,
            )

    app.dependency_overrides[research.get_session] = _get_session_override
    app.dependency_overrides[require_tenant] = _require_tenant_override
    return app, tenant_a_slug, tenant_b_slug, campaign_id


def test_tenant_b_cannot_list_or_read_tenant_a_private_workspace():
    app, tenant_a_slug, tenant_b_slug, _campaign_id = _setup()
    client = TestClient(app)

    create = client.post(
        "/research/workspaces",
        headers={"X-Tenant-Key": tenant_a_slug},
        json={
            "name": "Private Hypothesis Lab",
            "hypothesis": "confidential research question",
            "protocol": "do not leak",
            "visibility": "private",
        },
    )
    assert create.status_code == 200, create.text
    ws_id = create.json()["id"]

    list_b = client.get("/research/workspaces", headers={"X-Tenant-Key": tenant_b_slug})
    assert list_b.status_code == 200
    assert all(w["id"] != ws_id for w in list_b.json()["workspaces"])

    get_b = client.get(
        f"/research/workspaces/{ws_id}",
        headers={"X-Tenant-Key": tenant_b_slug},
    )
    assert get_b.status_code == 404


def test_tenant_b_cannot_generate_manifest_for_tenant_a_campaign():
    app, tenant_a_slug, tenant_b_slug, campaign_id = _setup()
    client = TestClient(app)

    denied = client.post(
        f"/research/manifests/generate/{campaign_id}",
        headers={"X-Tenant-Key": tenant_b_slug},
    )
    assert denied.status_code == 404

    allowed = client.post(
        f"/research/manifests/generate/{campaign_id}",
        headers={"X-Tenant-Key": tenant_a_slug},
    )
    assert allowed.status_code == 200, allowed.text
    manifest_id = allowed.json()["manifest_id"]

    leak = client.get(
        f"/research/manifests/{manifest_id}",
        headers={"X-Tenant-Key": tenant_b_slug},
    )
    assert leak.status_code == 404

    ok = client.get(
        f"/research/manifests/{manifest_id}",
        headers={"X-Tenant-Key": tenant_a_slug},
    )
    assert ok.status_code == 200
    assert ok.json()["campaign_id"] == campaign_id


def test_tenant_b_cannot_patch_tenant_a_workspace():
    app, tenant_a_slug, tenant_b_slug, _campaign_id = _setup()
    client = TestClient(app)

    create = client.post(
        "/research/workspaces",
        headers={"X-Tenant-Key": tenant_a_slug},
        json={"name": "Owned Workspace", "hypothesis": "mine", "visibility": "private"},
    )
    ws_id = create.json()["id"]

    patch = client.patch(
        f"/research/workspaces/{ws_id}",
        headers={"X-Tenant-Key": tenant_b_slug},
        json={"hypothesis": "hijacked"},
    )
    assert patch.status_code == 404

    still_a = client.get(
        f"/research/workspaces/{ws_id}",
        headers={"X-Tenant-Key": tenant_a_slug},
    )
    assert still_a.status_code == 200
    assert still_a.json()["hypothesis"] == "mine"
