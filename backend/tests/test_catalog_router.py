"""
Tests for api/routers/catalog.py
Covers: model catalog (OpenRouter + fallback) and benchmark catalog.
"""
import importlib.util
import json
import os
import secrets
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

_spec = importlib.util.spec_from_file_location(
    "catalog_router",
    Path(__file__).parent.parent / "api" / "routers" / "catalog.py",
)
mod = importlib.util.module_from_spec(_spec)
sys.modules["catalog_router"] = mod
_spec.loader.exec_module(mod)

from core.models import LLMModel, ModelProvider

MOCK_OPENROUTER_RESPONSE = {
    "data": [
        {
            "id": "meta-llama/llama-3-8b-instruct",
            "name": "Llama 3 8B Instruct",
            "context_length": 8192,
            "pricing": {"prompt": "0.0001", "completion": "0.0002"},
            "description": "Llama 3 8B model",
        },
        {
            "id": "openai/gpt-4",
            "name": "GPT-4",
            "context_length": 128000,
            "pricing": {"prompt": "0.03", "completion": "0.06"},
            "description": "GPT-4 model",
        },
        {
            "id": "mistralai/mistral-7b:free",
            "name": "Mistral 7B Free",
            "context_length": 32768,
            "pricing": {"prompt": "0", "completion": "0"},
            "description": "Mistral 7B free model",
        },
    ]
}


@pytest.fixture(scope="module")
def db_engine(tmp_path_factory):
    db = tmp_path_factory.mktemp("catalog_tests") / "test.db"
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="module")
def app(db_engine):
    def _get_session():
        with Session(db_engine) as s:
            yield s
    test_app = FastAPI()
    test_app.include_router(mod.router)
    test_app.dependency_overrides[mod.get_session] = _get_session
    return test_app


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as c:
        yield c


def _fresh_cache():
    """Reset the module-level catalog cache."""
    import catalog_router
    catalog_router._catalog_cache = []
    catalog_router._catalog_cache_ts = 0.0


def _mock_httpx_client(response_data):
    """Build a mock httpx.AsyncClient that returns response_data."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = response_data
    mock_resp.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


# ── Model Catalog ─────────────────────────────────────────────────────────────

def test_get_model_catalog(client):
    _fresh_cache()
    mock_client = _mock_httpx_client(MOCK_OPENROUTER_RESPONSE)
    with patch("catalog_router.httpx.AsyncClient", return_value=mock_client):
        resp = client.get("/catalog/models")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 3
    ids = [m["id"] for m in data]
    assert "meta-llama/llama-3-8b-instruct" in ids
    assert "openai/gpt-4" in ids


def test_get_model_catalog_provider_filter(client):
    _fresh_cache()
    mock_client = _mock_httpx_client(MOCK_OPENROUTER_RESPONSE)
    with patch("catalog_router.httpx.AsyncClient", return_value=mock_client):
        resp = client.get("/catalog/models?provider=openai")
    assert resp.status_code == 200
    data = resp.json()
    # Only GPT-4 has "openai" in provider
    assert len(data) == 1
    assert data[0]["id"] == "openai/gpt-4"


def test_get_model_catalog_free_only(client):
    _fresh_cache()
    mock_client = _mock_httpx_client(MOCK_OPENROUTER_RESPONSE)
    with patch("catalog_router.httpx.AsyncClient", return_value=mock_client):
        resp = client.get("/catalog/models?free_only=true")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    for m in data:
        assert m["is_free"] is True


def test_get_model_catalog_search_filter(client):
    _fresh_cache()
    mock_client = _mock_httpx_client(MOCK_OPENROUTER_RESPONSE)
    with patch("catalog_router.httpx.AsyncClient", return_value=mock_client):
        resp = client.get("/catalog/models?search=llama")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    for m in data:
        assert "llama" in m["id"].lower() or "llama" in m["name"].lower()


def test_get_model_catalog_openrouter_down_empty_fallback(client):
    _fresh_cache()
    with patch("catalog_router.httpx.AsyncClient") as mock_cls:
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_instance.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_cls.return_value = mock_instance
        resp = client.get("/catalog/models")
    # When OpenRouter is down and no local DB models, returns empty list
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_model_catalog_openrouter_down_local_db_fallback(client, db_engine):
    _fresh_cache()
    # Seed a local model
    with Session(db_engine) as s:
        m = LLMModel(
            name="Local Fallback Model",
            provider=ModelProvider.OPENAI,
            model_id="local/fallback-model",
        )
        s.add(m)
        s.commit()

    with patch("catalog_router.httpx.AsyncClient") as mock_cls:
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_instance.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_cls.return_value = mock_instance
        resp = client.get("/catalog/models")
    assert resp.status_code == 200
    data = resp.json()
    # Local DB model should appear in fallback
    ids = [m["id"] for m in data]
    assert "local/fallback-model" in ids


def test_get_model_catalog_open_source_only(client):
    _fresh_cache()
    mock_client = _mock_httpx_client(MOCK_OPENROUTER_RESPONSE)
    with patch("catalog_router.httpx.AsyncClient", return_value=mock_client):
        resp = client.get("/catalog/models?open_source_only=true")
    assert resp.status_code == 200
    data = resp.json()
    for m in data:
        assert m["is_open_source"] is True


def test_get_model_catalog_max_cost_filter(client):
    _fresh_cache()
    mock_client = _mock_httpx_client(MOCK_OPENROUTER_RESPONSE)
    # max_cost_per_1k=0.5 should exclude GPT-4 (cost_input_per_1k = 0.03*1000=30)
    with patch("catalog_router.httpx.AsyncClient", return_value=mock_client):
        resp = client.get("/catalog/models?max_cost_per_1k=0.5")
    assert resp.status_code == 200
    data = resp.json()
    for m in data:
        assert m["cost_input_per_1k"] <= 0.5


# ── Benchmark Catalog ─────────────────────────────────────────────────────────

def test_get_benchmark_catalog_no_filter(client):
    with patch("catalog_router._harness_catalog", return_value=[]):
        resp = client.get("/catalog/benchmarks")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    bench = data[0]
    assert "key" in bench
    assert "name" in bench
    assert "type" in bench
    assert "domain" in bench


def test_get_benchmark_catalog_type_filter(client):
    with patch("catalog_router._harness_catalog", return_value=[]):
        resp = client.get("/catalog/benchmarks?type=safety")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0
    for b in data:
        assert b["type"] == "safety"


def test_get_benchmark_catalog_domain_filter(client):
    with patch("catalog_router._harness_catalog", return_value=[]):
        resp = client.get("/catalog/benchmarks?domain=math")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0
    for b in data:
        assert "math" in b["domain"].lower()


def test_get_benchmark_catalog_frontier_only(client):
    with patch("catalog_router._harness_catalog", return_value=[]):
        resp = client.get("/catalog/benchmarks?frontier_only=true")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0
    for b in data:
        assert b["is_frontier"] is True


def test_get_benchmark_catalog_search_filter(client):
    with patch("catalog_router._harness_catalog", return_value=[]):
        resp = client.get("/catalog/benchmarks?search=MMLU")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0
    for b in data:
        assert "mmlu" in b["name"].lower() or "mmlu" in b["description"].lower()


def test_get_benchmark_catalog_source_inesia(client):
    with patch("catalog_router._harness_catalog", return_value=[]):
        resp = client.get("/catalog/benchmarks?source=inesia")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0
    # INESIA source benchmarks should not have "lm-eval" tag
    for b in data:
        assert "lm-eval" not in b.get("tags", [])


def test_get_benchmark_catalog_source_harness(client):
    mock_harness = [
        {
            "key": "harness_test",
            "name": "Harness Test Bench",
            "domain": "reasoning",
            "description": "A harness test benchmark",
            "metric": "accuracy",
            "lm_eval_task": "harness_test",
            "few_shot": 5,
            "is_frontier": False,
        }
    ]
    with patch("catalog_router._harness_catalog", return_value=mock_harness):
        resp = client.get("/catalog/benchmarks?source=harness")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    for b in data:
        assert "lm-eval" in b.get("tags", [])
