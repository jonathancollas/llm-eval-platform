"""
Tests for api/routers/tenants.py
Covers: create_tenant, list_tenants, get_tenant, rotate_api_key, add_user,
        _require_admin (dev-mode and with key).
"""
import os
import secrets
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

import importlib.util
from pathlib import Path

# Load the tenants router module directly so we can patch its ADMIN_API_KEY
_spec = importlib.util.spec_from_file_location(
    "tenants_router",
    Path(__file__).parent.parent / "api" / "routers" / "tenants.py",
)
tenants_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tenants_mod)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db_engine(tmp_path_factory):
    db = tmp_path_factory.mktemp("tenants_tests") / "tenants.db"
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="module")
def app(db_engine):
    def _get_session():
        with Session(db_engine) as s:
            yield s

    test_app = FastAPI()
    test_app.include_router(tenants_mod.router)
    test_app.dependency_overrides[tenants_mod.get_session] = _get_session
    return test_app


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as c:
        yield c


# ── Dev-mode (no ADMIN_API_KEY set) ──────────────────────────────────────────

def test_create_tenant_dev_mode(client, monkeypatch):
    """In dev mode (no ADMIN_API_KEY), all requests pass through."""
    monkeypatch.setattr(tenants_mod, "_ADMIN_API_KEY", "")
    resp = client.post("/tenants/", json={"name": "Acme Corp", "slug": "acme", "plan": "pro"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == "acme"
    assert body["plan"] == "pro"
    assert body["api_key"].startswith("mr_")
    assert "Save this API key" in body["warning"]


def test_create_tenant_duplicate_slug_returns_409(client, monkeypatch):
    monkeypatch.setattr(tenants_mod, "_ADMIN_API_KEY", "")
    resp = client.post("/tenants/", json={"name": "Acme 2", "slug": "acme", "plan": "free"})
    assert resp.status_code == 409


def test_list_tenants_returns_created_tenant(client, monkeypatch):
    monkeypatch.setattr(tenants_mod, "_ADMIN_API_KEY", "")
    resp = client.get("/tenants/")
    assert resp.status_code == 200
    slugs = [t["slug"] for t in resp.json()["tenants"]]
    assert "acme" in slugs


def test_get_tenant_returns_detail(client, monkeypatch):
    monkeypatch.setattr(tenants_mod, "_ADMIN_API_KEY", "")
    # First get the id
    resp = client.get("/tenants/")
    tenant = next(t for t in resp.json()["tenants"] if t["slug"] == "acme")
    tid = tenant["id"]

    resp2 = client.get(f"/tenants/{tid}")
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["slug"] == "acme"
    assert "users" in body
    assert "created_at" in body


def test_get_tenant_not_found_returns_404(client, monkeypatch):
    monkeypatch.setattr(tenants_mod, "_ADMIN_API_KEY", "")
    resp = client.get("/tenants/99999")
    assert resp.status_code == 404


def test_rotate_api_key_returns_new_key(client, monkeypatch):
    monkeypatch.setattr(tenants_mod, "_ADMIN_API_KEY", "")
    resp = client.get("/tenants/")
    tenant = next(t for t in resp.json()["tenants"] if t["slug"] == "acme")
    tid = tenant["id"]

    resp2 = client.post(f"/tenants/{tid}/rotate-key")
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["new_api_key"].startswith("mr_")
    assert "old key is now invalid" in body["warning"]


def test_rotate_api_key_not_found_returns_404(client, monkeypatch):
    monkeypatch.setattr(tenants_mod, "_ADMIN_API_KEY", "")
    resp = client.post("/tenants/99999/rotate-key")
    assert resp.status_code == 404


def test_add_user_to_tenant(client, monkeypatch):
    monkeypatch.setattr(tenants_mod, "_ADMIN_API_KEY", "")
    resp = client.get("/tenants/")
    tenant = next(t for t in resp.json()["tenants"] if t["slug"] == "acme")
    tid = tenant["id"]

    resp2 = client.post(
        f"/tenants/{tid}/users",
        json={"email": "alice@example.com", "name": "Alice", "role": "evaluator"},
    )
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["email"] == "alice@example.com"
    assert body["role"] == "evaluator"


def test_add_duplicate_user_returns_409(client, monkeypatch):
    monkeypatch.setattr(tenants_mod, "_ADMIN_API_KEY", "")
    resp = client.get("/tenants/")
    tenant = next(t for t in resp.json()["tenants"] if t["slug"] == "acme")
    tid = tenant["id"]
    resp2 = client.post(
        f"/tenants/{tid}/users",
        json={"email": "alice@example.com", "name": "Alice2", "role": "viewer"},
    )
    assert resp2.status_code == 409


def test_add_user_tenant_not_found(client, monkeypatch):
    monkeypatch.setattr(tenants_mod, "_ADMIN_API_KEY", "")
    resp = client.post(
        "/tenants/99999/users",
        json={"email": "bob@example.com", "name": "Bob", "role": "viewer"},
    )
    assert resp.status_code == 404


def test_get_tenant_includes_added_user(client, monkeypatch):
    monkeypatch.setattr(tenants_mod, "_ADMIN_API_KEY", "")
    resp = client.get("/tenants/")
    tenant = next(t for t in resp.json()["tenants"] if t["slug"] == "acme")
    tid = tenant["id"]

    resp2 = client.get(f"/tenants/{tid}")
    users = resp2.json()["users"]
    emails = [u["email"] for u in users]
    assert "alice@example.com" in emails


# ── Admin-key enforcement ─────────────────────────────────────────────────────

def test_require_admin_rejects_missing_key(client, monkeypatch):
    monkeypatch.setattr(tenants_mod, "_ADMIN_API_KEY", "supersecret")
    resp = client.post("/tenants/", json={"name": "Hacker", "slug": "hacker"})
    assert resp.status_code == 401


def test_require_admin_rejects_wrong_key(client, monkeypatch):
    monkeypatch.setattr(tenants_mod, "_ADMIN_API_KEY", "supersecret")
    resp = client.post(
        "/tenants/",
        json={"name": "Hacker", "slug": "hacker"},
        headers={"X-API-Key": "wrongkey"},
    )
    assert resp.status_code == 403


def test_require_admin_accepts_correct_key(client, monkeypatch):
    monkeypatch.setattr(tenants_mod, "_ADMIN_API_KEY", "supersecret")
    resp = client.post(
        "/tenants/",
        json={"name": "Legit Org", "slug": "legit-org"},
        headers={"X-API-Key": "supersecret"},
    )
    assert resp.status_code == 200
    assert resp.json()["slug"] == "legit-org"


def test_list_tenants_requires_admin_key(client, monkeypatch):
    monkeypatch.setattr(tenants_mod, "_ADMIN_API_KEY", "supersecret")
    resp = client.get("/tenants/")
    assert resp.status_code == 401


def test_rotate_key_requires_admin(client, monkeypatch):
    monkeypatch.setattr(tenants_mod, "_ADMIN_API_KEY", "supersecret")
    resp = client.post("/tenants/1/rotate-key")
    assert resp.status_code == 401
