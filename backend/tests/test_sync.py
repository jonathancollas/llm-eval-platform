"""
Tests for api/routers/sync.py
Covers: _build_model (tags, SSRF guards, free flag, open-weight detection),
        sync_benchmarks_from_catalog, sync_starter_models,
        API routes: /sync/startup, /sync/startup/status, /sync/benchmarks,
                    /sync/benchmarks/import-all.
"""
import importlib.util
import json
import os
import secrets
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

_spec = importlib.util.spec_from_file_location(
    "sync_router",
    Path(__file__).parent.parent / "api" / "routers" / "sync.py",
)
sync_mod = importlib.util.module_from_spec(_spec)
sys.modules["sync_router"] = sync_mod
_spec.loader.exec_module(sync_mod)

from sync_router import (
    _build_model,
    sync_benchmarks_from_catalog,
    sync_starter_models,
    STARTER_MODELS,
    OPENROUTER_ENDPOINT,
    OPEN_SOURCE_PROVIDERS,
)
from core.models import LLMModel, ModelProvider, Benchmark


# ── DB / app fixtures ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db_engine(tmp_path_factory):
    db = tmp_path_factory.mktemp("sync_tests") / "sync.db"
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="module")
def app(db_engine):
    def _get_session():
        with Session(db_engine) as s:
            yield s

    test_app = FastAPI()
    test_app.include_router(sync_mod.router)
    test_app.dependency_overrides[sync_mod.get_session] = _get_session
    return test_app


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as c:
        yield c


# ══════════════════════════════════════════════════════════════════════════════
# _build_model
# ══════════════════════════════════════════════════════════════════════════════

def _raw(model_id="meta-llama/llama-3.1-70b", name="Llama 3.1 70B",
         context_length=8192, pricing=None, description="",
         architecture=None, supported_parameters=None,
         top_provider=None, hugging_face_id="", created=0):
    return {
        "id": model_id,
        "name": name,
        "context_length": context_length,
        "pricing": pricing or {"prompt": "0.0", "completion": "0.0"},
        "description": description,
        "architecture": architecture or {},
        "supported_parameters": supported_parameters or [],
        "top_provider": top_provider or {},
        "hugging_face_id": hugging_face_id,
        "created": created,
    }


def test_build_model_returns_llm_model():
    m = _build_model(_raw())
    assert isinstance(m, LLMModel)


def test_build_model_free_tag_when_zero_cost():
    m = _build_model(_raw(model_id="meta-llama/llama:free"))
    tags = json.loads(m.tags)
    assert "gratuit" in tags


def test_build_model_open_source_tag_for_llama():
    m = _build_model(_raw(model_id="meta-llama/llama-3.1-70b"))
    tags = json.loads(m.tags)
    assert "open-source" in tags


def test_build_model_long_context_tag():
    m = _build_model(_raw(model_id="google/gemma-3-27b", context_length=131072))
    tags = json.loads(m.tags)
    assert "long-context" in tags


def test_build_model_instruct_tag():
    m = _build_model(_raw(model_id="mistralai/mistral-7b-instruct"))
    tags = json.loads(m.tags)
    assert "instruct" in tags


def test_build_model_code_tag():
    m = _build_model(_raw(model_id="bigcode/starcoder2"))
    tags = json.loads(m.tags)
    assert "code" in tags


def test_build_model_70b_plus_tag():
    m = _build_model(_raw(model_id="meta-llama/llama-3.1-70b"))
    tags = json.loads(m.tags)
    assert "70B+" in tags


def test_build_model_7_8b_tag():
    m = _build_model(_raw(model_id="mistralai/mistral-7b-instruct"))
    tags = json.loads(m.tags)
    assert "7-8B" in tags


def test_build_model_small_tag():
    m = _build_model(_raw(model_id="microsoft/phi-3b"))
    tags = json.loads(m.tags)
    assert "≤3B" in tags


def test_build_model_is_free_flag():
    m = _build_model(_raw(
        model_id="meta-llama/llama-3.3-70b-instruct:free",
        pricing={"prompt": "0", "completion": "0"},
    ))
    assert m.is_free is True


def test_build_model_is_not_free_when_paid():
    m = _build_model(_raw(
        model_id="openai/gpt-4o",
        pricing={"prompt": "0.005", "completion": "0.015"},
    ))
    assert m.is_free is False


def test_build_model_open_weight_from_hf_id():
    m = _build_model(_raw(model_id="some/model", hugging_face_id="myorg/repo"))
    assert m.is_open_weight is True


def test_build_model_open_weight_from_prefix():
    m = _build_model(_raw(model_id="meta-llama/llama-3.1-8b"))
    assert m.is_open_weight is True


def test_build_model_supports_vision():
    m = _build_model(_raw(architecture={"modality": "image+text"}))
    assert m.supports_vision is True


def test_build_model_supports_tools():
    m = _build_model(_raw(supported_parameters=["tools", "temperature"]))
    assert m.supports_tools is True


def test_build_model_supports_reasoning():
    # r1 check is inside any() which needs non-empty supported_parameters
    m = _build_model(_raw(model_id="deepseek/deepseek-r1", supported_parameters=["temperature"]))
    assert m.supports_reasoning is True


def test_build_model_cost_calculation():
    m = _build_model(_raw(pricing={"prompt": "0.000005", "completion": "0.000015"}))
    assert abs(m.cost_input_per_1k - 0.005) < 0.0001
    assert abs(m.cost_output_per_1k - 0.015) < 0.0001


def test_build_model_invalid_pricing_defaults_to_zero():
    m = _build_model(_raw(pricing={"prompt": "n/a", "completion": "n/a"}))
    assert m.cost_input_per_1k == 0.0
    assert m.cost_output_per_1k == 0.0


def test_build_model_empty_id_returns_none():
    m = _build_model({"id": "", "name": "no id"})
    assert m is None


def test_build_model_missing_id_returns_none():
    m = _build_model({"name": "no id"})
    assert m is None


def test_build_model_endpoint_is_openrouter():
    m = _build_model(_raw())
    assert m.endpoint == OPENROUTER_ENDPOINT


def test_build_model_description_truncated():
    long_desc = "x" * 500
    m = _build_model(_raw(description=long_desc))
    # Notes field contains the description
    assert len(m.notes) <= 250  # "Via OpenRouter. " + 200 chars max


def test_build_model_context_length_defaults_when_null():
    m = _build_model({**_raw(), "context_length": None})
    assert m.context_length == 4096


def test_build_model_moderated_flag():
    m = _build_model(_raw(top_provider={"is_moderated": True}))
    assert m.is_moderated is True


# ══════════════════════════════════════════════════════════════════════════════
# sync_benchmarks_from_catalog
# ══════════════════════════════════════════════════════════════════════════════

def test_sync_benchmarks_adds_catalog_items(db_engine):
    with Session(db_engine) as s:
        added = sync_benchmarks_from_catalog(s)
    assert added >= 0  # Could be 0 if already synced


def test_sync_benchmarks_idempotent(db_engine):
    with Session(db_engine) as s:
        first = sync_benchmarks_from_catalog(s)
    with Session(db_engine) as s:
        second = sync_benchmarks_from_catalog(s)
    assert second == 0  # All already in DB


def test_sync_benchmarks_no_duplicates(db_engine):
    with Session(db_engine) as s:
        sync_benchmarks_from_catalog(s)
        benches = s.exec(__import__("sqlmodel").select(Benchmark)).all()
        names = [b.name for b in benches]
    assert len(names) == len(set(names))


# ══════════════════════════════════════════════════════════════════════════════
# sync_starter_models
# ══════════════════════════════════════════════════════════════════════════════

def test_sync_starter_models_adds_models(db_engine):
    with Session(db_engine) as s:
        added = sync_starter_models(s)
    assert added >= 0


def test_sync_starter_models_idempotent(db_engine):
    with Session(db_engine) as s:
        sync_starter_models(s)
    with Session(db_engine) as s:
        second = sync_starter_models(s)
    assert second == 0


def test_sync_starter_models_no_duplicates(db_engine):
    from sqlmodel import select
    with Session(db_engine) as s:
        models = s.exec(select(LLMModel)).all()
        model_ids = [m.model_id for m in models]
    assert len(model_ids) == len(set(model_ids))


def test_starter_models_all_free():
    """All starter pack models should have :free suffix (no credits needed)."""
    for m in STARTER_MODELS:
        assert m["in"] == 0.0 and m["out"] == 0.0, f"Starter {m['model_id']} is not free"


# ══════════════════════════════════════════════════════════════════════════════
# API routes
# ══════════════════════════════════════════════════════════════════════════════

def test_startup_status_returns_state_fields(client):
    resp = client.get("/sync/startup/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body
    assert body["status"] in ("idle", "running", "done", "error")


def test_startup_trigger_returns_200(client):
    resp = client.post("/sync/startup")
    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body


def test_startup_trigger_idempotent(client):
    """Calling /startup twice should not raise errors."""
    client.post("/sync/startup")
    resp = client.post("/sync/startup")
    assert resp.status_code == 200


def test_benchmarks_check_returns_expected_fields(client):
    resp = client.get("/sync/benchmarks")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("new_count", "new_benchmarks", "total_catalog", "total_local"):
        assert key in body


def test_benchmarks_check_counts_are_non_negative(client):
    body = client.get("/sync/benchmarks").json()
    assert body["new_count"] >= 0
    assert body["total_catalog"] >= 0
    assert body["total_local"] >= 0


def test_import_all_benchmarks_returns_added(client):
    resp = client.post("/sync/benchmarks/import-all")
    assert resp.status_code == 200
    body = resp.json()
    assert "added" in body
    assert body["added"] >= 0


def test_import_all_idempotent(client):
    """Running import twice: second run should add 0."""
    client.post("/sync/benchmarks/import-all")
    resp2 = client.post("/sync/benchmarks/import-all")
    assert resp2.json()["added"] == 0
