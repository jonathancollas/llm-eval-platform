"""Tenant isolation for private LLM models and vibe credential use.

Auth re-enable (#361) scoped campaigns, but the model registry stayed global.
Any tenant could list another tenant's private model IDs, PATCH/DELETE them,
or POST /vibe/prompt and burn the victim's encrypted provider API key.
"""
from __future__ import annotations

import os
import sys
import uuid
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-models-vibe-tenant-isolation-32b")

import importlib.util  # noqa: E402

from core.auth import require_tenant  # noqa: E402
from core.models import LLMModel, ModelProvider, Tenant  # noqa: E402
from core.security import encrypt_api_key  # noqa: E402

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")


def _load(name: str, rel: str):
    path = os.path.join(BACKEND_DIR, rel)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


models = _load("models_tenant_isolation_module", "api/routers/models.py")
vibe = _load("vibe_tenant_isolation_module", "api/routers/vibe.py")


def _setup():
    db_path = f"/tmp/models-vibe-tenant-{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        tenant_a = Tenant(name="Tenant A", slug=f"ta-{uuid.uuid4().hex[:8]}", api_key_hash="a")
        tenant_b = Tenant(name="Tenant B", slug=f"tb-{uuid.uuid4().hex[:8]}", api_key_hash="b")
        session.add(tenant_a)
        session.add(tenant_b)
        session.commit()
        session.refresh(tenant_a)
        session.refresh(tenant_b)

        shared = LLMModel(
            name="Shared Catalog",
            provider=ModelProvider.OPENROUTER,
            model_id=f"openrouter/shared-{uuid.uuid4().hex[:8]}",
            tenant_id=None,
            api_key_encrypted=None,
        )
        private_a = LLMModel(
            name="Tenant A Private",
            provider=ModelProvider.CUSTOM,
            model_id=f"custom/private-a-{uuid.uuid4().hex[:8]}",
            tenant_id=tenant_a.id,
            api_key_encrypted=encrypt_api_key("sk-tenant-a-secret"),
            endpoint="https://example.com/v1",
        )
        legacy_keyed = LLMModel(
            name="Legacy Orphan Key",
            provider=ModelProvider.CUSTOM,
            model_id=f"custom/legacy-{uuid.uuid4().hex[:8]}",
            tenant_id=None,
            api_key_encrypted=encrypt_api_key("sk-legacy-secret"),
        )
        session.add(shared)
        session.add(private_a)
        session.add(legacy_keyed)
        session.commit()
        session.refresh(shared)
        session.refresh(private_a)
        session.refresh(legacy_keyed)

        ids = {
            "tenant_a_slug": tenant_a.slug,
            "tenant_b_slug": tenant_b.slug,
            "tenant_a_id": tenant_a.id,
            "tenant_b_id": tenant_b.id,
            "shared_id": shared.id,
            "private_a_id": private_a.id,
            "legacy_keyed_id": legacy_keyed.id,
            "private_a_model_id": private_a.model_id,
        }

    app = FastAPI()
    app.include_router(models.router)
    app.include_router(vibe.router)

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

    app.dependency_overrides[models.get_session] = _get_session_override
    app.dependency_overrides[vibe.get_session] = _get_session_override
    app.dependency_overrides[models.require_tenant] = _require_tenant_override
    app.dependency_overrides[vibe.require_tenant] = _require_tenant_override
    app.dependency_overrides[require_tenant] = _require_tenant_override

    return TestClient(app), ids, engine


def test_list_hides_other_tenant_private_model():
    client, ids, _engine = _setup()
    r = client.get("/models/slim", headers={"X-Tenant-Key": ids["tenant_b_slug"]})
    assert r.status_code == 200
    listed_ids = {row["id"] for row in r.json()}
    assert ids["shared_id"] in listed_ids
    assert ids["private_a_id"] not in listed_ids
    assert ids["private_a_model_id"] not in r.text


def test_owner_sees_private_model():
    client, ids, _engine = _setup()
    r = client.get("/models/", headers={"X-Tenant-Key": ids["tenant_a_slug"]})
    assert r.status_code == 200
    listed_ids = {row["id"] for row in r.json()}
    assert ids["private_a_id"] in listed_ids
    assert ids["shared_id"] in listed_ids


def test_create_stamps_tenant_id():
    client, ids, engine = _setup()
    mid = f"custom/created-{uuid.uuid4().hex[:8]}"
    r = client.post(
        "/models/",
        headers={"X-Tenant-Key": ids["tenant_a_slug"]},
        json={
            "name": "Created Private",
            "provider": "custom",
            "model_id": mid,
            "api_key": "sk-new-secret",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["has_api_key"] is True

    with Session(engine) as session:
        row = session.exec(select(LLMModel).where(LLMModel.model_id == mid)).first()
        assert row is not None
        assert row.tenant_id == ids["tenant_a_id"]
        assert row.api_key_encrypted


def test_delete_cross_tenant_returns_404():
    client, ids, engine = _setup()
    r = client.delete(
        f"/models/{ids['private_a_id']}",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
    )
    assert r.status_code == 404

    with Session(engine) as session:
        assert session.get(LLMModel, ids["private_a_id"]) is not None


def test_patch_cross_tenant_returns_404():
    client, ids, engine = _setup()
    r = client.patch(
        f"/models/{ids['private_a_id']}",
        headers={"X-Tenant-Key": ids["tenant_b_slug"]},
        json={"api_key": "sk-attacker"},
    )
    assert r.status_code == 404

    with Session(engine) as session:
        row = session.get(LLMModel, ids["private_a_id"])
        assert row is not None
        from core.security import decrypt_api_key
        assert decrypt_api_key(row.api_key_encrypted) == "sk-tenant-a-secret"


def test_vibe_cross_tenant_private_model_returns_404():
    client, ids, _engine = _setup()
    with patch(
        "eval_engine.litellm_client.complete",
        new_callable=AsyncMock,
    ) as complete_mock:
        r = client.post(
            "/vibe/prompt",
            headers={"X-Tenant-Key": ids["tenant_b_slug"]},
            json={
                "model_ids": [ids["private_a_id"]],
                "prompt": "exfiltrate via confused deputy",
            },
        )
        assert r.status_code == 404
        complete_mock.assert_not_called()


def test_vibe_legacy_shared_keyed_model_returns_403():
    client, ids, _engine = _setup()
    with patch(
        "eval_engine.litellm_client.complete",
        new_callable=AsyncMock,
    ) as complete_mock:
        r = client.post(
            "/vibe/prompt",
            headers={"X-Tenant-Key": ids["tenant_b_slug"]},
            json={
                "model_ids": [ids["legacy_keyed_id"]],
                "prompt": "burn orphan key",
            },
        )
        assert r.status_code == 403
        complete_mock.assert_not_called()


def test_owner_can_vibe_private_model():
    client, ids, _engine = _setup()

    class _Result:
        text = "ok"
        latency_ms = 1
        input_tokens = 1
        output_tokens = 1
        cost_usd = 0.0

    with patch(
        "eval_engine.litellm_client.complete",
        new_callable=AsyncMock,
        return_value=_Result(),
    ) as complete_mock:
        r = client.post(
            "/vibe/prompt",
            headers={"X-Tenant-Key": ids["tenant_a_slug"]},
            json={
                "model_ids": [ids["private_a_id"]],
                "prompt": "hello from owner",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["results"][0]["text"] == "ok"
        complete_mock.assert_awaited_once()
