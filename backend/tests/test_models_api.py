"""
Tests for api/routers/models.py
Covers: list (with filters), create (dedup, API-key encryption), get, update,
        delete, SSRF endpoint validation, slim list.
"""
import importlib.util
import json
import os
import secrets
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

_spec = importlib.util.spec_from_file_location(
    "models_router",
    Path(__file__).parent.parent / "api" / "routers" / "models.py",
)
models_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(models_mod)


@pytest.fixture(scope="module")
def db_engine(tmp_path_factory):
    db = tmp_path_factory.mktemp("models_tests") / "models.db"
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="module")
def app(db_engine):
    def _get_session():
        with Session(db_engine) as s:
            yield s

    test_app = FastAPI()
    test_app.include_router(models_mod.router)
    test_app.dependency_overrides[models_mod.get_session] = _get_session
    return test_app


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as c:
        yield c


# ── Create ────────────────────────────────────────────────────────────────────

def test_create_model_returns_201(client):
    resp = client.post("/models/", json={
        "name": "GPT-4o",
        "provider": "custom",
        "model_id": "openai/gpt-4o",
        "context_length": 128000,
        "cost_input_per_1k": 0.005,
        "cost_output_per_1k": 0.015,
        "tags": ["flagship"],
        "notes": "Main model",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["model_id"] == "openai/gpt-4o"
    assert body["has_api_key"] is False


def test_create_model_encrypts_api_key(client):
    resp = client.post("/models/", json={
        "name": "Claude",
        "provider": "anthropic",
        "model_id": "anthropic/claude-sonnet",
        "api_key": "sk-ant-secret",
    })
    assert resp.status_code == 201
    body = resp.json()
    # The read schema exposes has_api_key, not the plaintext key
    assert body["has_api_key"] is True
    assert "sk-ant-secret" not in json.dumps(body)


def test_create_model_duplicate_returns_409(client):
    resp = client.post("/models/", json={
        "name": "GPT-4o Again",
        "provider": "custom",
        "model_id": "openai/gpt-4o",
    })
    assert resp.status_code == 409


def test_create_model_invalid_ssrf_endpoint_rejected(client):
    """Endpoints pointing to private IPs must be rejected."""
    resp = client.post("/models/", json={
        "name": "Malicious",
        "provider": "custom",
        "model_id": "evil/model",
        "endpoint": "http://192.168.1.1/v1",
    })
    assert resp.status_code == 422


def test_create_model_localhost_endpoint_rejected(client):
    resp = client.post("/models/", json={
        "name": "Local",
        "provider": "custom",
        "model_id": "local/bad",
        "endpoint": "http://localhost/v1",
    })
    assert resp.status_code == 422


def test_create_model_invalid_scheme_rejected(client):
    resp = client.post("/models/", json={
        "name": "FTP Model",
        "provider": "custom",
        "model_id": "ftp/model",
        "endpoint": "ftp://example.com/v1",
    })
    assert resp.status_code == 422


# ── List ──────────────────────────────────────────────────────────────────────

def test_list_models_returns_all(client):
    resp = client.get("/models/")
    assert resp.status_code == 200
    ids = [m["model_id"] for m in resp.json()]
    assert "openai/gpt-4o" in ids


def test_list_models_filter_by_provider(client):
    resp = client.get("/models/?provider=anthropic")
    assert resp.status_code == 200
    for m in resp.json():
        assert m["provider"] == "anthropic"


def test_list_models_search(client):
    resp = client.get("/models/?search=gpt")
    assert resp.status_code == 200
    names = [m["name"].lower() for m in resp.json()]
    assert all("gpt" in n for n in names)


def test_list_models_pagination(client):
    resp_all = client.get("/models/")
    total = len(resp_all.json())
    resp_page = client.get("/models/?limit=1&offset=0")
    assert resp_page.status_code == 200
    assert len(resp_page.json()) == min(1, total)


def test_list_models_slim_endpoint(client):
    resp = client.get("/models/slim")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) > 0
    # Slim response only has lightweight fields
    for item in items:
        assert "id" in item
        assert "model_id" in item
        assert "provider" in item
        assert "is_local" in item
        # Full details should NOT be in the slim response
        assert "api_key_encrypted" not in item


# ── Get ───────────────────────────────────────────────────────────────────────

def _get_gpt4o_id(client) -> int:
    resp = client.get("/models/")
    return next(m["id"] for m in resp.json() if m["model_id"] == "openai/gpt-4o")


def test_get_model_returns_detail(client):
    mid = _get_gpt4o_id(client)
    resp = client.get(f"/models/{mid}")
    assert resp.status_code == 200
    assert resp.json()["model_id"] == "openai/gpt-4o"


def test_get_model_not_found_returns_404(client):
    resp = client.get("/models/99999")
    assert resp.status_code == 404


# ── Update ────────────────────────────────────────────────────────────────────

def test_update_model_name(client):
    mid = _get_gpt4o_id(client)
    resp = client.patch(f"/models/{mid}", json={"name": "GPT-4o Updated"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "GPT-4o Updated"


def test_update_model_tags(client):
    mid = _get_gpt4o_id(client)
    resp = client.patch(f"/models/{mid}", json={"tags": ["flagship", "vision"]})
    assert resp.status_code == 200
    assert "vision" in resp.json()["tags"]


def test_update_model_deactivate(client):
    mid = _get_gpt4o_id(client)
    resp = client.patch(f"/models/{mid}", json={"is_active": False})
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


def test_update_model_not_found_returns_404(client):
    resp = client.patch("/models/99999", json={"name": "Ghost"})
    assert resp.status_code == 404


def test_update_model_ssrf_endpoint_rejected(client):
    mid = _get_gpt4o_id(client)
    resp = client.patch(f"/models/{mid}", json={"endpoint": "http://10.0.0.1/v1"})
    assert resp.status_code == 422


# ── Delete ────────────────────────────────────────────────────────────────────

def test_delete_model_returns_204(client):
    # Create a throwaway model first
    resp = client.post("/models/", json={
        "name": "Throwaway",
        "provider": "custom",
        "model_id": "test/throwaway",
    })
    assert resp.status_code == 201
    mid = resp.json()["id"]

    del_resp = client.delete(f"/models/{mid}")
    assert del_resp.status_code == 204

    get_resp = client.get(f"/models/{mid}")
    assert get_resp.status_code == 404


def test_delete_model_not_found_returns_404(client):
    resp = client.delete("/models/99999")
    assert resp.status_code == 404
