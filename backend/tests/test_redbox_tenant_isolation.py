"""REDBOX exploit tenant isolation.

Auth re-enable (#361) scoped campaigns, but /api/redbox exploit endpoints
never gained require_tenant checks. Any caller who listed exploits, opened
the heatmap/live feed, or replayed by ID could read another tenant's
adversarial prompts and model responses.
"""
from __future__ import annotations

import os
import sys
import uuid

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-redbox-tenant-isolation-32b")

import importlib.util  # noqa: E402

from core.auth import require_tenant  # noqa: E402
from core.models import LLMModel, ModelProvider, RedboxExploit, Tenant  # noqa: E402

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
REDBOX_PATH = os.path.join(BACKEND_DIR, "api", "routers", "redbox.py")
_spec = importlib.util.spec_from_file_location("redbox_tenant_isolation_module", REDBOX_PATH)
redbox = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(redbox)


def _setup():
    db_path = f"/tmp/redbox-tenant-{uuid.uuid4().hex}.db"
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

        exploit = RedboxExploit(
            tenant_id=tenant_a.id,
            model_id=model.id,
            seed_prompt="tenant A secret seed",
            mutation_type="jailbreak",
            adversarial_prompt="TENANT-A-SECRET-ADVERSARIAL-PROMPT",
            model_response="TENANT-A-SECRET-MODEL-RESPONSE",
            difficulty=0.8,
            severity=0.9,
            breached=True,
            expected_failure="safety_bypass",
            failure_detected="safety_bypass",
            latency_ms=12,
        )
        session.add(exploit)
        session.commit()
        session.refresh(exploit)

        ids = {
            "tenant_a_slug": tenant_a.slug,
            "tenant_b_slug": tenant_b.slug,
            "tenant_a_id": tenant_a.id,
            "tenant_b_id": tenant_b.id,
            "model_id": model.id,
            "exploit_a_id": exploit.id,
        }

    app = FastAPI()
    app.include_router(redbox.router)

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

    app.dependency_overrides[redbox.get_session] = _get_session_override
    app.dependency_overrides[redbox.require_tenant] = _require_tenant_override
    app.dependency_overrides[require_tenant] = _require_tenant_override

    return TestClient(app), ids, engine


def test_list_exploits_hides_other_tenant():
    client, ids, _engine = _setup()
    r = client.get(
        "/redbox/exploits",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["exploits"] == []
    assert "TENANT-A-SECRET-ADVERSARIAL-PROMPT" not in r.text


def test_owner_can_list_own_exploits():
    client, ids, _engine = _setup()
    r = client.get(
        "/redbox/exploits",
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["exploits"][0]["adversarial_prompt"].startswith("TENANT-A-SECRET")


def test_heatmap_excludes_other_tenant():
    client, ids, _engine = _setup()
    r = client.get(
        "/redbox/heatmap",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 200
    assert r.json()["computed"] is False


def test_live_feed_excludes_other_tenant():
    client, ids, _engine = _setup()
    r = client.get(
        f"/redbox/live/{ids['model_id']}",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total_exploits"] == 0
    assert body["items"] == []
    assert "TENANT-A-SECRET" not in r.text


def test_replay_cross_tenant_returns_404():
    client, ids, _engine = _setup()
    r = client.post(
        f"/redbox/replay/{ids['exploit_a_id']}",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
        json={"model_id": ids["model_id"]},
    )
    assert r.status_code == 404
