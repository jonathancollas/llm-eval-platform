import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SECRET_KEY", "TEST_SECRET_KEY_DO_NOT_USE_IN_PRODUCTION")
os.environ["ADMIN_API_KEY"] = "test-admin-key"

import main as main_app_module  # noqa: E402


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.middleware("http")(main_app_module.api_key_auth)

    @app.get("/api/models/")
    def list_models():
        return {"ok": True}

    @app.post("/api/campaigns/")
    def create_campaign():
        return {"ok": True}

    @app.post("/api/benchmarks/")
    def create_benchmark():
        return {"ok": True}

    return app


@pytest.fixture
def client():
    main_app_module._ADMIN_API_KEY = "test-admin-key"
    return TestClient(_build_test_app())


def test_unauthenticated_models_request_returns_401(client):
    resp = client.get("/api/models/")
    assert resp.status_code == 401


def test_unauthenticated_campaign_create_returns_401(client):
    resp = client.post("/api/campaigns/", json={"name": "x"})
    assert resp.status_code == 401


def test_unauthenticated_benchmark_create_returns_401(client):
    resp = client.post("/api/benchmarks/", json={"name": "x"})
    assert resp.status_code == 401


def test_missing_tenant_key_returns_401_even_with_api_key(client):
    resp = client.get("/api/models/", headers={"X-API-Key": "test-admin-key"})
    assert resp.status_code == 401


def test_viewer_cannot_perform_write_operations(client):
    resp = client.post("/api/campaigns/", headers={"X-API-Key": "test-admin-key", "X-Role": "viewer"}, json={"name": "x"})
    assert resp.status_code == 403
