"""Tests for api/routers/deep_analysis.py"""
import importlib.util
import math
import os
import secrets
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

_spec = importlib.util.spec_from_file_location(
    "deep_analysis_router_module",
    Path(__file__).parent.parent / "api" / "routers" / "deep_analysis.py",
)
mod = importlib.util.module_from_spec(_spec)
sys.modules["deep_analysis_router_module"] = mod
_spec.loader.exec_module(mod)


@pytest.fixture(scope="module")
def db_engine(tmp_path_factory):
    db = tmp_path_factory.mktemp("deep_analysis_test") / "test.db"
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


@pytest.fixture(scope="module")
def seeded_models(db_engine):
    """Create an Ollama model and a non-Ollama model."""
    from core.models import LLMModel, ModelProvider

    with Session(db_engine) as session:
        ollama_model = LLMModel(
            name="Llama 3",
            provider=ModelProvider.OLLAMA,
            model_id="llama3:latest",
        )
        openai_model = LLMModel(
            name="GPT-4",
            provider=ModelProvider.OPENAI,
            model_id="openai/gpt-4-da",
        )
        session.add(ollama_model)
        session.add(openai_model)
        session.commit()
        session.refresh(ollama_model)
        session.refresh(openai_model)
        return {
            "ollama_id": ollama_model.id,
            "openai_id": openai_model.id,
        }


# ── GET /deep-analysis/models/{id}/info ──────────────────────────────────────

def test_get_model_info_not_found(client):
    resp = client.get("/deep-analysis/models/99999/info")
    assert resp.status_code == 404


def test_get_model_info_non_ollama(client, seeded_models):
    model_id = seeded_models["openai_id"]
    resp = client.get(f"/deep-analysis/models/{model_id}/info")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False
    assert "reason" in data


def test_get_model_info_ollama_success(client, seeded_models):
    """Mocked Ollama response with full model info."""
    model_id = seeded_models["ollama_id"]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "details": {
            "family": "llama",
            "parameter_size": "8B",
            "quantization_level": "Q4_K_M",
            "format": "gguf",
            "families": ["llama"],
        },
        "modelfile": 'FROM llama3\nSYSTEM "You are a helpful assistant"\n',
        "template": "{{ .Prompt }}",
        "parameters": "temperature 0.7",
        "model_info": {
            "llama.num_layers": 32,
            "llama.num_heads": 32,
            "llama.embedding_length": 4096,
        },
    }

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        resp = client.get(f"/deep-analysis/models/{model_id}/info")

    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is True
    assert data["architecture"]["family"] == "llama"
    assert "llama.num_layers" in data["layers"]
    assert data["system_prompt"] == "You are a helpful assistant"
    assert "tokenizer_analysis" in data["analyses_available"]


def test_get_model_info_ollama_non_200(client, seeded_models):
    """Ollama returns non-200 status."""
    model_id = seeded_models["ollama_id"]

    mock_response = MagicMock()
    mock_response.status_code = 503

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        resp = client.get(f"/deep-analysis/models/{model_id}/info")

    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False
    assert "503" in data["reason"]


def test_get_model_info_ollama_exception(client, seeded_models):
    """Ollama unreachable (exception)."""
    model_id = seeded_models["ollama_id"]

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        resp = client.get(f"/deep-analysis/models/{model_id}/info")

    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False
    assert "Connection refused" in data["reason"]


def test_get_model_info_ollama_no_system_prompt(client, seeded_models):
    """Ollama model with no SYSTEM line in modelfile."""
    model_id = seeded_models["ollama_id"]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "details": {},
        "modelfile": "FROM llama3\n",
        "template": "",
        "parameters": "",
        "model_info": {},
    }

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        resp = client.get(f"/deep-analysis/models/{model_id}/info")

    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is True
    assert data["system_prompt"] == ""


# ── GET /deep-analysis/models/{id}/tokenizer ─────────────────────────────────

def test_tokenizer_analysis_not_found(client):
    resp = client.get("/deep-analysis/models/99999/tokenizer")
    assert resp.status_code == 400


def test_tokenizer_analysis_non_ollama(client, seeded_models):
    model_id = seeded_models["openai_id"]
    resp = client.get(f"/deep-analysis/models/{model_id}/tokenizer")
    assert resp.status_code == 400


def test_tokenizer_analysis_ollama_success(client, seeded_models):
    model_id = seeded_models["ollama_id"]
    embedding = [0.1] * 64

    mock_response_ok = MagicMock()
    mock_response_ok.status_code = 200
    mock_response_ok.json.return_value = {"embedding": embedding}

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response_ok)

    with patch("httpx.AsyncClient", return_value=mock_client):
        resp = client.get(f"/deep-analysis/models/{model_id}/tokenizer")

    assert resp.status_code == 200
    data = resp.json()
    assert "test_results" in data
    # 8 test strings defined in the tokenizer endpoint
    assert len(data["test_results"]) == 8
    success = [r for r in data["test_results"] if "embedding_dim" in r]
    assert len(success) == 8
    assert data["embedding_dim"] == 64


def test_tokenizer_analysis_ollama_exception(client, seeded_models):
    """Exception during embedding call sets error=True for that item."""
    model_id = seeded_models["ollama_id"]

    async def mock_post(*args, **kwargs):
        raise Exception("embed failed")

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = mock_post

    with patch("httpx.AsyncClient", return_value=mock_client):
        resp = client.get(f"/deep-analysis/models/{model_id}/tokenizer")

    assert resp.status_code == 200
    data = resp.json()
    # All results should have error=True
    for r in data["test_results"]:
        assert r.get("error") is True


# ── POST /deep-analysis/models/{id}/refusal-probe ────────────────────────────

def test_refusal_probe_not_ollama(client, seeded_models):
    model_id = seeded_models["openai_id"]
    resp = client.post(f"/deep-analysis/models/{model_id}/refusal-probe")
    assert resp.status_code == 400


def test_refusal_probe_not_found(client):
    resp = client.post("/deep-analysis/models/99999/refusal-probe")
    assert resp.status_code == 400


def test_refusal_probe_success(client, seeded_models):
    """Mock complete() to return refusal for high-level prompts."""
    model_id = seeded_models["ollama_id"]

    call_count = [0]

    async def mock_complete(model, prompt, temperature, max_tokens):
        call_count[0] += 1
        result = MagicMock()
        # Refuse for levels >= 6 (harmful)
        if call_count[0] > 5:
            result.text = "I cannot help with that. It's against my ethical guidelines."
        else:
            result.text = "Here is the answer to your question."
        return result

    with patch("eval_engine.litellm_client.complete", side_effect=mock_complete):
        resp = client.post(f"/deep-analysis/models/{model_id}/refusal-probe")

    assert resp.status_code == 200
    data = resp.json()
    assert "probes" in data
    assert len(data["probes"]) == len(mod.REFUSAL_PROBE_PROMPTS)
    assert "refusal_threshold" in data
    assert "safety_score" in data
    assert "over_refusal_detected" in data
    assert "analysis" in data


def test_refusal_probe_all_refused(client, seeded_models):
    """All prompts refused → threshold=0, safety_score=1.0, over_refusal=True."""
    model_id = seeded_models["ollama_id"]

    async def mock_complete(model, prompt, temperature, max_tokens):
        result = MagicMock()
        result.text = "I cannot and will not help. This is harmful and unethical."
        return result

    with patch("eval_engine.litellm_client.complete", side_effect=mock_complete):
        resp = client.post(f"/deep-analysis/models/{model_id}/refusal-probe")

    assert resp.status_code == 200
    data = resp.json()
    assert data["over_refusal_detected"] is True
    assert data["safety_score"] == 1.0


def test_refusal_probe_none_refused(client, seeded_models):
    """No prompts refused → threshold=10, safety_score=0.0."""
    model_id = seeded_models["ollama_id"]

    async def mock_complete(model, prompt, temperature, max_tokens):
        result = MagicMock()
        result.text = "Sure! Here's a detailed step-by-step guide."
        return result

    with patch("eval_engine.litellm_client.complete", side_effect=mock_complete):
        resp = client.post(f"/deep-analysis/models/{model_id}/refusal-probe")

    assert resp.status_code == 200
    data = resp.json()
    assert data["refusal_threshold"] == 10
    assert data["safety_score"] == 0.0


def test_refusal_probe_exception(client, seeded_models):
    """Exception on complete() → error stored, compliance_score=0.0."""
    model_id = seeded_models["ollama_id"]

    async def mock_complete(*args, **kwargs):
        raise Exception("model error")

    with patch("eval_engine.litellm_client.complete", side_effect=mock_complete):
        resp = client.post(f"/deep-analysis/models/{model_id}/refusal-probe")

    assert resp.status_code == 200
    data = resp.json()
    for probe in data["probes"]:
        assert "error" in probe


# ── POST /deep-analysis/models/{id}/embedding-analysis ───────────────────────

def test_embedding_analysis_not_ollama(client, seeded_models):
    model_id = seeded_models["openai_id"]
    resp = client.post(f"/deep-analysis/models/{model_id}/embedding-analysis")
    assert resp.status_code == 400


def test_embedding_analysis_not_found(client):
    resp = client.post("/deep-analysis/models/99999/embedding-analysis")
    assert resp.status_code == 400


def test_embedding_analysis_success(client, seeded_models):
    """Mock embeddings with distinct vectors so cosine similarity is computed."""
    model_id = seeded_models["ollama_id"]

    import random
    random.seed(42)

    async def mock_post(*args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        vec = [random.uniform(-1, 1) for _ in range(64)]
        mock_resp.json.return_value = {"embedding": vec}
        return mock_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = mock_post

    with patch("httpx.AsyncClient", return_value=mock_client):
        resp = client.post(f"/deep-analysis/models/{model_id}/embedding-analysis")

    assert resp.status_code == 200
    data = resp.json()
    assert "concept_pairs" in data
    assert "avg_concept_separation" in data
    assert "safety_boundary_strength" in data
    assert data["safety_boundary_strength"] in ("strong", "moderate", "weak")


def test_embedding_analysis_no_embeddings(client, seeded_models):
    """All embedding calls fail → empty results."""
    model_id = seeded_models["ollama_id"]

    async def mock_post(*args, **kwargs):
        raise Exception("embedding error")

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = mock_post

    with patch("httpx.AsyncClient", return_value=mock_client):
        resp = client.post(f"/deep-analysis/models/{model_id}/embedding-analysis")

    assert resp.status_code == 200
    data = resp.json()
    assert data["concept_pairs"] == []
    assert data["avg_concept_separation"] == 0


# ── _cosine_similarity helper ─────────────────────────────────────────────────

def test_cosine_similarity_orthogonal():
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    sim = mod._cosine_similarity(a, b)
    assert abs(sim) < 1e-9


def test_cosine_similarity_same():
    a = [1.0, 2.0, 3.0]
    sim = mod._cosine_similarity(a, a)
    assert abs(sim - 1.0) < 1e-6


def test_cosine_similarity_zero_vectors():
    a = [0.0, 0.0, 0.0]
    b = [1.0, 2.0, 3.0]
    assert mod._cosine_similarity(a, b) == 0.0


def test_cosine_similarity_empty():
    assert mod._cosine_similarity([], []) == 0.0


def test_cosine_similarity_different_lengths():
    assert mod._cosine_similarity([1.0, 2.0], [1.0]) == 0.0


def test_cosine_similarity_negative():
    a = [1.0, 0.0]
    b = [-1.0, 0.0]
    sim = mod._cosine_similarity(a, b)
    assert abs(sim - (-1.0)) < 1e-6


# ── Safety boundary strength labels ──────────────────────────────────────────

def test_embedding_analysis_strong_separation(client, seeded_models):
    """avg_separation > 0.3 → strong."""
    model_id = seeded_models["ollama_id"]

    # Provide completely orthogonal embeddings
    dim = 128
    call_count = [0]

    async def mock_post(*args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        idx = call_count[0] % dim
        vec = [0.0] * dim
        vec[idx] = 1.0
        call_count[0] += 1
        mock_resp.json.return_value = {"embedding": vec}
        return mock_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = mock_post

    with patch("httpx.AsyncClient", return_value=mock_client):
        resp = client.post(f"/deep-analysis/models/{model_id}/embedding-analysis")

    assert resp.status_code == 200
    data = resp.json()
    assert data["safety_boundary_strength"] == "strong"
