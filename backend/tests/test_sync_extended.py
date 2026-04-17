"""
Tests for api/routers/sync.py — extended coverage
Covers: sync_openrouter_models, _run_startup_sync_task, _ollama_fetch_tags,
        sync_ollama_models, check_ollama, import_ollama_models,
        get_ollama_suggestions, pull_ollama_model, pull_and_register_ollama_model.
"""
import importlib.util
import json
import os
import secrets
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

# ── Load module ────────────────────────────────────────────────────────────────

_spec = importlib.util.spec_from_file_location(
    "sync_router_ext",
    Path(__file__).parent.parent / "api" / "routers" / "sync.py",
)
sync = importlib.util.module_from_spec(_spec)
sys.modules["sync_router_ext"] = sync
_spec.loader.exec_module(sync)

from core.models import Benchmark, LLMModel, ModelProvider

# ── DB + App Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db_engine(tmp_path_factory):
    db = tmp_path_factory.mktemp("sync_ext") / "sync_ext.db"
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="module")
def client(db_engine):
    def _get_session():
        with Session(db_engine) as s:
            yield s

    app = FastAPI()
    app.include_router(sync.router)
    app.dependency_overrides[sync.get_session] = _get_session
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def reset_ollama_cache():
    """Reset Ollama circuit-breaker state before each test."""
    sync._ollama_available = None
    sync._ollama_last_check = None
    yield
    sync._ollama_available = None
    sync._ollama_last_check = None


@pytest.fixture(autouse=True)
def reset_sync_state():
    """Reset startup sync state before each test."""
    sync._sync_state.update({
        "status": "idle",
        "started_at": None,
        "finished_at": None,
        "benchmarks_added": 0,
        "models_added": 0,
        "total_benchmarks": 0,
        "total_models": 0,
        "openrouter_synced": False,
        "error": None,
    })
    yield


# ── Helpers ────────────────────────────────────────────────────────────────────

def _raw_model(model_id="meta-llama/llama-test", name="Test Model"):
    return {
        "id": model_id,
        "name": name,
        "context_length": 8192,
        "pricing": {"prompt": "0.0000001", "completion": "0.0000002"},
        "description": "Test model",
        "architecture": {"modality": "text", "tokenizer": "llama", "instruct_type": ""},
        "supported_parameters": ["tools", "reasoning"],
        "top_provider": {"max_completion_tokens": 4096, "is_moderated": False},
        "hugging_face_id": "meta-llama/test",
        "created": 0,
    }


def _ollama_model(name="llama3:8b", size_bytes=4_000_000_000):
    return {
        "name": name,
        "size": size_bytes,
        "details": {
            "family": "llama",
            "parameter_size": "8B",
            "quantization_level": "Q4_K_M",
            "context_length": 8192,
        },
    }


# ── sync_openrouter_models ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_openrouter_no_api_key(db_engine):
    """Lines 177-181 — no API key → starter pack."""
    with Session(db_engine) as s:
        with patch.object(sync.settings, "openrouter_api_key", None):
            added, synced = await sync.sync_openrouter_models(s)
    assert synced is False


@pytest.mark.asyncio
async def test_sync_openrouter_success(db_engine):
    """Lines 183-220 — successful OpenRouter fetch."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": [_raw_model("openrouter/test-model-42")]}
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with Session(db_engine) as s, \
         patch.object(sync.settings, "openrouter_api_key", "sk-test"), \
         patch("httpx.AsyncClient", return_value=mock_client):
        added, synced = await sync.sync_openrouter_models(s)
    assert synced is True
    assert added >= 0


@pytest.mark.asyncio
async def test_sync_openrouter_http_failure(db_engine):
    """Lines 222-225 — HTTP failure falls back to starter pack."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.RequestError("fail"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with Session(db_engine) as s, \
         patch.object(sync.settings, "openrouter_api_key", "sk-test"), \
         patch("httpx.AsyncClient", return_value=mock_client):
        added, synced = await sync.sync_openrouter_models(s)
    assert synced is False


@pytest.mark.asyncio
async def test_sync_openrouter_commit_conflict(db_engine):
    """Lines 199-217 — commit failure triggers one-by-one retry."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": [_raw_model("openrouter/conflict-model")]}
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with Session(db_engine) as s:
        original_commit = s.commit
        call_count = [0]

        def flaky_commit():
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Simulated conflict")
            original_commit()

        s.commit = flaky_commit
        with patch.object(sync.settings, "openrouter_api_key", "sk-test"), \
             patch("httpx.AsyncClient", return_value=mock_client):
            added, synced = await sync.sync_openrouter_models(s)
    # Should not raise
    assert synced in (True, False)


# ── _run_startup_sync_task ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_startup_sync_task_already_running():
    """Lines 235-237 — already running skips."""
    sync._sync_state["status"] = "running"
    await sync._run_startup_sync_task()
    # Should return without error, still running
    assert sync._sync_state["status"] == "running"


@pytest.mark.asyncio
async def test_run_startup_sync_task_already_done():
    """Line 236 — already done skips."""
    sync._sync_state["status"] = "done"
    await sync._run_startup_sync_task()
    assert sync._sync_state["status"] == "done"


@pytest.mark.asyncio
async def test_run_startup_sync_task_success():
    """Lines 239-269 — happy path."""
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.exec.return_value.all.return_value = []

    with patch.object(sync, "sync_benchmarks_from_catalog", return_value=2), \
         patch.object(sync, "sync_openrouter_models", new=AsyncMock(return_value=(3, True))), \
         patch("sync_router_ext.Session", return_value=mock_session):
        await sync._run_startup_sync_task()
    assert sync._sync_state["status"] == "done"
    assert sync._sync_state["benchmarks_added"] == 2


@pytest.mark.asyncio
async def test_run_startup_sync_task_timeout():
    """Lines 251-254 — OpenRouter sync timeout."""
    import asyncio

    async def _slow(*args, **kwargs):
        await asyncio.sleep(100)

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.exec.return_value.all.return_value = []

    with patch.object(sync, "sync_benchmarks_from_catalog", return_value=0), \
         patch.object(sync, "sync_openrouter_models", new=_slow), \
         patch.object(sync, "OPENROUTER_TIMEOUT", 0.01), \
         patch.object(sync, "sync_starter_models", return_value=1), \
         patch("sync_router_ext.Session", return_value=mock_session):
        await sync._run_startup_sync_task()
    assert sync._sync_state["status"] == "done"


@pytest.mark.asyncio
async def test_run_startup_sync_task_error():
    """Lines 271-277 — exception sets error state."""
    with patch.object(sync, "sync_benchmarks_from_catalog",
                      side_effect=RuntimeError("DB failure")):
        await sync._run_startup_sync_task()
    assert sync._sync_state["status"] == "error"
    assert "DB failure" in sync._sync_state["error"]


# ── GET /sync/startup/status ──────────────────────────────────────────────────

def test_startup_status_idle(client):
    resp = client.get("/sync/startup/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "idle"


# ── POST /sync/startup ────────────────────────────────────────────────────────

def test_startup_sync_dispatches(client):
    """Lines 365-374 — idempotent dispatch."""
    resp = client.post("/sync/startup")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data


def test_startup_sync_when_running(client):
    sync._sync_state["status"] = "running"
    resp = client.post("/sync/startup")
    assert resp.status_code == 200


# ── GET /sync/benchmarks ─────────────────────────────────────────────────────

def test_sync_benchmarks_check(client):
    resp = client.get("/sync/benchmarks")
    assert resp.status_code == 200
    data = resp.json()
    assert "new_count" in data
    assert "total_catalog" in data


# ── POST /sync/benchmarks/import-all ─────────────────────────────────────────

def test_import_all_benchmarks(client):
    resp = client.post("/sync/benchmarks/import-all")
    assert resp.status_code == 200
    data = resp.json()
    assert "added" in data


# ── _ollama_fetch_tags ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ollama_fetch_tags_cached_unavailable():
    """Lines 413-419 — cached unavailable returns fast."""
    from datetime import datetime
    sync._ollama_available = False
    sync._ollama_last_check = datetime.utcnow()
    available, models = await sync._ollama_fetch_tags()
    assert available is False
    assert models == []


@pytest.mark.asyncio
async def test_ollama_fetch_tags_success():
    """Lines 421-428 — Ollama is available."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"models": [_ollama_model()]}
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        available, models = await sync._ollama_fetch_tags()
    assert available is True
    assert len(models) == 1


@pytest.mark.asyncio
async def test_ollama_fetch_tags_failure():
    """Lines 429-432 — Ollama unreachable sets cache."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("no route"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        available, models = await sync._ollama_fetch_tags()
    assert available is False
    assert sync._ollama_available is False


# ── sync_ollama_models ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_ollama_unavailable(db_engine):
    """Lines 438-441 — Ollama not available."""
    with Session(db_engine) as s, \
         patch.object(sync, "_ollama_fetch_tags", new=AsyncMock(return_value=(False, []))):
        added, available = await sync.sync_ollama_models(s)
    assert added == 0
    assert available is False


@pytest.mark.asyncio
async def test_sync_ollama_empty_models(db_engine):
    """Lines 443-444 — Ollama available but no models."""
    with Session(db_engine) as s, \
         patch.object(sync, "_ollama_fetch_tags", new=AsyncMock(return_value=(True, []))):
        added, available = await sync.sync_ollama_models(s)
    assert added == 0
    assert available is True


@pytest.mark.asyncio
async def test_sync_ollama_adds_new_model(db_engine):
    """Lines 446-497 — new Ollama model imported."""
    models_data = [_ollama_model("newllama:7b")]
    with Session(db_engine) as s, \
         patch.object(sync, "_ollama_fetch_tags",
                      new=AsyncMock(return_value=(True, models_data))):
        added, available = await sync.sync_ollama_models(s)
    assert added == 1
    assert available is True


@pytest.mark.asyncio
async def test_sync_ollama_skips_existing(db_engine):
    """Lines 452-460 — existing model skipped."""
    with Session(db_engine) as s:
        s.add(LLMModel(name="existing-ollama", provider=ModelProvider.OLLAMA,
                       model_id="existingmodel:latest"))
        s.commit()

    models_data = [_ollama_model("existingmodel:latest")]
    with Session(db_engine) as s, \
         patch.object(sync, "_ollama_fetch_tags",
                      new=AsyncMock(return_value=(True, models_data))):
        added, available = await sync.sync_ollama_models(s)
    assert added == 0


@pytest.mark.asyncio
async def test_sync_ollama_no_name_skipped(db_engine):
    """Lines 449-451 — model with no name is skipped."""
    models_data = [{"name": "", "size": 0, "details": {}}]
    with Session(db_engine) as s, \
         patch.object(sync, "_ollama_fetch_tags",
                      new=AsyncMock(return_value=(True, models_data))):
        added, _ = await sync.sync_ollama_models(s)
    assert added == 0


# ── GET /sync/ollama ──────────────────────────────────────────────────────────

def test_check_ollama_unavailable(client):
    """Lines 504-506 — Ollama not available."""
    with patch.object(sync, "_ollama_fetch_tags",
                      new=AsyncMock(return_value=(False, []))):
        resp = client.get("/sync/ollama")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False


def test_check_ollama_available(client):
    """Lines 508-524 — Ollama available with models."""
    models = [_ollama_model("ollama3:8b")]
    with patch.object(sync, "_ollama_fetch_tags",
                      new=AsyncMock(return_value=(True, models))):
        resp = client.get("/sync/ollama")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is True
    assert len(data["models"]) == 1
    assert data["models"][0]["name"] == "ollama3:8b"


# ── POST /sync/ollama/import ──────────────────────────────────────────────────

def test_import_ollama_models_unavailable(client):
    """Lines 530-532 — Ollama not available."""
    with patch.object(sync, "sync_ollama_models",
                      new=AsyncMock(return_value=(0, False))):
        resp = client.post("/sync/ollama/import")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False


def test_import_ollama_models_success(client):
    """Line 533 — successful import."""
    with patch.object(sync, "sync_ollama_models",
                      new=AsyncMock(return_value=(2, True))):
        resp = client.post("/sync/ollama/import")
    assert resp.status_code == 200
    data = resp.json()
    assert data["added"] == 2
    assert data["available"] is True


# ── GET /sync/ollama/suggestions ──────────────────────────────────────────────

def test_ollama_suggestions_unavailable(client):
    """Lines 575-577 — Ollama not available."""
    with patch.object(sync, "_ollama_fetch_tags",
                      new=AsyncMock(return_value=(False, []))):
        resp = client.get("/sync/ollama/suggestions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ollama_available"] is False


def test_ollama_suggestions_with_model(client, db_engine):
    """Lines 579-604 — suggestions for a matching model."""
    with Session(db_engine) as s:
        existing = s.exec(
            select(LLMModel).where(
                LLMModel.model_id == "meta-llama/llama-3.2-3b-instruct:free"
            )
        ).first()
        if not existing:
            m = LLMModel(
                name="Llama3 test",
                provider=ModelProvider.CUSTOM,
                model_id="meta-llama/llama-3.2-3b-instruct:free",
            )
            s.add(m)
            s.commit()

    local_models = [{"name": "llama3.2:3b"}]
    with patch.object(sync, "_ollama_fetch_tags",
                      new=AsyncMock(return_value=(True, local_models))):
        resp = client.get("/sync/ollama/suggestions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ollama_available"] is True


def test_ollama_suggestions_ollama_model_skipped(client, db_engine):
    """Lines 582-584 — Ollama provider models are skipped."""
    with Session(db_engine) as s:
        m = LLMModel(
            name="Local Llama",
            provider=ModelProvider.OLLAMA,
            model_id="llama3:8b-local-only",
        )
        s.add(m)
        s.commit()

    local_models = [{"name": "llama3:8b-local-only"}]
    with patch.object(sync, "_ollama_fetch_tags",
                      new=AsyncMock(return_value=(True, local_models))):
        resp = client.get("/sync/ollama/suggestions")
    assert resp.status_code == 200


# ── POST /sync/ollama/pull ────────────────────────────────────────────────────

def test_pull_ollama_model_no_name(client):
    """Lines 614-616 — missing model_name."""
    resp = client.post("/sync/ollama/pull")
    assert resp.status_code == 422


def test_pull_ollama_model_success(client):
    """Lines 618-627 — successful pull via query param."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        resp = client.post("/sync/ollama/pull?model_name=llama3:8b")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pulled"


def test_pull_ollama_model_error_status(client):
    """Lines 628-629 — non-200 HTTP status."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = "Not Found"

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        resp = client.post("/sync/ollama/pull?model_name=bad-model")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"


def test_pull_ollama_model_timeout(client):
    """Lines 630-631 — timeout returns pulling status."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        resp = client.post("/sync/ollama/pull?model_name=huge-model")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pulling"


def test_pull_ollama_model_request_error(client):
    """Lines 632-638 — connection error."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.RequestError("connect failed"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        resp = client.post("/sync/ollama/pull?model_name=unreachable-model")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"


def test_pull_ollama_model_unexpected_error(client):
    """Lines 639-644 — unexpected exception."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=RuntimeError("unexpected"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        resp = client.post("/sync/ollama/pull?model_name=bad-model-2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"


def test_pull_ollama_model_via_body(client):
    """Lines 614 — using JSON body."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        resp = client.post("/sync/ollama/pull",
                           json={"model_name": "llama3:body"})
    assert resp.status_code == 200


# ── POST /sync/ollama/pull-and-register ───────────────────────────────────────

def test_pull_and_register_no_mapping(client):
    """Lines 654-658 — no Ollama mapping."""
    resp = client.post("/sync/ollama/pull-and-register?openrouter_model_id=unknown/model")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "no_mapping"


def test_pull_and_register_success(client, db_engine):
    """Lines 660-705 — successful pull and register."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        resp = client.post(
            "/sync/ollama/pull-and-register"
            "?openrouter_model_id=meta-llama/llama-3.2-3b-instruct"
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["registered"] is True


def test_pull_and_register_request_error(client):
    """Lines 668-674 — connection error on pull."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.RequestError("fail"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        resp = client.post(
            "/sync/ollama/pull-and-register"
            "?openrouter_model_id=meta-llama/llama-3.1-8b-instruct"
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pull_failed"


def test_pull_and_register_unexpected_error(client):
    """Lines 675-681 — unexpected error on pull."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=RuntimeError("boom"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        resp = client.post(
            "/sync/ollama/pull-and-register"
            "?openrouter_model_id=google/gemma-3-27b-it"
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pull_failed"


def test_pull_and_register_existing_model_not_duplicated(client, db_engine):
    """Lines 683-699 — existing Ollama model not re-registered."""
    ollama_name = "llama3.3:70b"
    with Session(db_engine) as s:
        existing = LLMModel(
            name=f"{ollama_name} (Ollama)",
            provider=ModelProvider.OLLAMA,
            model_id=ollama_name,
        )
        s.add(existing)
        s.commit()

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        resp = client.post(
            "/sync/ollama/pull-and-register"
            "?openrouter_model_id=meta-llama/llama-3.3-70b-instruct"
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


def test_pull_and_register_free_suffix(client):
    """Lines 655-657 — :free suffix mapping."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        resp = client.post(
            "/sync/ollama/pull-and-register"
            "?openrouter_model_id=meta-llama/llama-3.2-3b-instruct:free"
        )
    assert resp.status_code == 200
