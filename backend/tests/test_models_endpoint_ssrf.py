"""Regression tests for model endpoint SSRF validation.

The previous validator raised ValueError for private/resolved IPs, then
caught that same ValueError and fell back to hostname prefix checks that
omitted 172.16.0.0/12. Creating a CUSTOM model with
``http://172.16.0.1/v1`` (Docker/K8s) succeeded; later ``/models/{id}/test``
or a campaign run sent provider credentials to that address via LiteLLM
``api_base``.
"""
from __future__ import annotations

import importlib.util
import os
import secrets
import socket
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlmodel import Session, SQLModel, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

BACKEND_DIR = Path(__file__).resolve().parent.parent
MODELS_PATH = BACKEND_DIR / "api" / "routers" / "models.py"
_spec = importlib.util.spec_from_file_location("models_router_ssrf", MODELS_PATH)
models = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(models)


@pytest.fixture()
def db_engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'models_ssrf.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture()
def client(db_engine):
    def _get_session_override():
        with Session(db_engine) as session:
            yield session

    app = FastAPI()
    app.include_router(models.router)
    app.dependency_overrides[models.get_session] = _get_session_override
    with TestClient(app) as test_client:
        yield test_client


def _create_payload(endpoint: str, model_id: str = "ssrf/probe") -> dict:
    return {
        "name": "SSRF probe",
        "provider": "custom",
        "model_id": model_id,
        "endpoint": endpoint,
        "context_length": 4096,
        "cost_input_per_1k": 0.0,
        "cost_output_per_1k": 0.0,
        "tags": [],
        "notes": "",
    }


@pytest.mark.parametrize(
    "url",
    [
        "http://172.16.0.1/v1",
        "http://172.17.0.1:8000/v1",  # default Docker bridge gateway
        "https://10.0.0.8/v1",
        "http://192.168.1.20/v1",
        "http://127.0.0.1/v1",
        "http://127.0.0.1:11434",
        "http://localhost/v1",
        "http://localhost:11434",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/v1",
        "http://0.0.0.0/v1",
    ],
)
def test_validate_endpoint_rejects_non_routable_literals(url):
    with pytest.raises(ValueError, match="not allowed|non-routable"):
        models._validate_endpoint(url)


def test_validate_endpoint_rejects_hostname_that_resolves_private(monkeypatch):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        assert host == "metadata.internal"
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("169.254.169.254", 0))]

    monkeypatch.setattr(models.socket, "getaddrinfo", _fake_getaddrinfo)
    with pytest.raises(ValueError, match="non-routable"):
        models._validate_endpoint("http://metadata.internal/latest/meta-data/")


def test_validate_endpoint_allows_public_literal():
    assert models._validate_endpoint("https://1.1.1.1/v1") == "https://1.1.1.1/v1"


def test_validate_endpoint_allows_unresolved_public_hostname(monkeypatch):
    def _fail_dns(host, port, *args, **kwargs):
        raise socket.gaierror("name or service not known")

    monkeypatch.setattr(models.socket, "getaddrinfo", _fail_dns)
    assert models._validate_endpoint("https://openrouter.ai/api/v1") == "https://openrouter.ai/api/v1"


def test_validate_endpoint_rejects_bad_scheme():
    with pytest.raises(ValueError, match="scheme"):
        models._validate_endpoint("file:///etc/passwd")


def test_create_model_rejects_docker_bridge_endpoint(client):
    response = client.post("/models/", json=_create_payload("http://172.17.0.1/v1"))
    assert response.status_code == 422
    assert client.get("/models/").json() == []


def test_create_model_rejects_rfc1918_172_16(client):
    response = client.post(
        "/models/",
        json=_create_payload("http://172.16.0.1/v1", model_id="ssrf/172-16"),
    )
    assert response.status_code == 422


def test_model_create_schema_rejects_private_endpoint():
    with pytest.raises(ValidationError):
        models.ModelCreate(**_create_payload("http://172.16.0.1/v1"))


def test_create_model_accepts_public_https_endpoint(client):
    response = client.post(
        "/models/",
        json=_create_payload("https://openrouter.ai/api/v1", model_id="ssrf/public"),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["endpoint"] == "https://openrouter.ai/api/v1"
    assert body["has_api_key"] is False
