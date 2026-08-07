"""Search router tenant isolation for campaign discovery and ASK answers.

/search/typeahead, /search/intent, and /search/execute previously queried
Campaign / EvalRun globally. A valid tenant key was enough to discover
another tenant's campaign names/IDs/status and aggregate counts.
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
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-search-tenant-isolation-32bytes")

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


search = _load_module("search_tenant_isolation_module", "api/routers/search.py")


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

        secret_name = f"Secret Acquisition Eval {uuid.uuid4().hex[:6]}"
        campaign_a = Campaign(
            name=secret_name,
            description="tenant-a-only",
            model_ids=f"[{model.id}]",
            benchmark_ids=f"[{benchmark.id}]",
            tenant_id=tenant_a.id,
            status=JobStatus.COMPLETED,
        )
        campaign_b = Campaign(
            name=f"Tenant B Publicish {uuid.uuid4().hex[:6]}",
            description="tenant-b-only",
            model_ids=f"[{model.id}]",
            benchmark_ids=f"[{benchmark.id}]",
            tenant_id=tenant_b.id,
            status=JobStatus.RUNNING,
        )
        session.add(campaign_a)
        session.add(campaign_b)
        session.commit()
        session.refresh(campaign_a)
        session.refresh(campaign_b)

        run_a = EvalRun(
            campaign_id=campaign_a.id,
            model_id=model.id,
            benchmark_id=benchmark.id,
            status=JobStatus.COMPLETED,
            score=0.97,
            num_items=1,
        )
        session.add(run_a)
        session.commit()

        return {
            "tenant_a_slug": tenant_a.slug,
            "tenant_b_slug": tenant_b.slug,
            "secret_name": secret_name,
            "secret_fragment": "Secret Acquisition",
            "campaign_a_id": campaign_a.id,
            "model_name": model.name,
        }


def _setup():
    db_path = f"/tmp/search-tenant-{uuid.uuid4().hex}.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    ids = _seed(engine)

    app = FastAPI()
    app.include_router(search.router, prefix="/api")

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

    app.dependency_overrides[search.get_session] = _get_session_override
    app.dependency_overrides[search.require_tenant] = _require_tenant_override
    app.dependency_overrides[require_tenant] = _require_tenant_override

    return TestClient(app), engine, ids


def test_owner_typeahead_finds_own_campaign():
    client, _engine, ids = _setup()
    r = client.get(
        "/api/search/typeahead",
        params={"q": ids["secret_fragment"]},
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    campaign_items = [
        item
        for group in body.get("groups", [])
        if group.get("kind") == "campaign"
        for item in group.get("items", [])
    ]
    assert any(item.get("label") == ids["secret_name"] for item in campaign_items)
    assert any(
        item.get("id") == f"campaign:{ids['campaign_a_id']}" for item in campaign_items
    )


def test_other_tenant_typeahead_cannot_discover_campaign():
    client, _engine, ids = _setup()
    r = client.get(
        "/api/search/typeahead",
        params={"q": ids["secret_fragment"]},
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    campaign_items = [
        item
        for group in body.get("groups", [])
        if group.get("kind") == "campaign"
        for item in group.get("items", [])
    ]
    assert campaign_items == []
    assert ids["secret_name"] not in r.text
    assert f"campaign:{ids['campaign_a_id']}" not in r.text


def test_other_tenant_latest_campaign_ignores_foreign_campaign():
    client, _engine, ids = _setup()
    # Leading '?' forces the ASK fast path so answer_deterministic runs.
    r = client.post(
        "/api/search/intent",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
        json={"query": "? latest campaign"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    answer = body.get("payload", {}).get("answer", "")
    assert ids["secret_name"] not in answer
    assert f"campaign:{ids['campaign_a_id']}" not in r.text
    # Tenant B's own campaign should still be visible as latest.
    assert "Tenant B Publicish" in answer or "No campaigns" not in answer


def test_owner_latest_campaign_returns_own_secret():
    client, _engine, ids = _setup()
    r = client.post(
        "/api/search/intent",
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
        json={"query": "? latest campaign"},
    )
    assert r.status_code == 200, r.text
    assert ids["secret_name"] in r.json()["payload"]["answer"]


def test_campaign_count_is_tenant_scoped():
    client, _engine, ids = _setup()
    r_a = client.post(
        "/api/search/intent",
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
        json={"query": "how many campaigns"},
    )
    r_b = client.post(
        "/api/search/intent",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
        json={"query": "how many campaigns"},
    )
    assert r_a.status_code == 200, r_a.text
    assert r_b.status_code == 200, r_b.text
    assert "1 campaigns total" in r_a.json()["payload"]["answer"]
    assert "1 campaigns total" in r_b.json()["payload"]["answer"]
    # Must not report the global total of 2.
    assert "2 campaigns total" not in r_a.json()["payload"]["answer"]
    assert "2 campaigns total" not in r_b.json()["payload"]["answer"]


def test_top_model_scores_are_tenant_scoped():
    client, _engine, ids = _setup()
    # Tenant B has no completed runs — must not see Tenant A's 0.97 score.
    r = client.post(
        "/api/search/intent",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
        json={"query": "? top model"},
    )
    assert r.status_code == 200, r.text
    answer = r.json().get("payload", {}).get("answer", "")
    assert "0.97" not in answer
    assert "0.970" not in answer


def test_execute_ask_latest_is_tenant_scoped():
    client, _engine, ids = _setup()
    r = client.post(
        "/api/search/execute",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
        json={"query": "? latest campaign"},
    )
    assert r.status_code == 200, r.text
    assert ids["secret_name"] not in r.text
    assert f"campaign:{ids['campaign_a_id']}" not in r.text
