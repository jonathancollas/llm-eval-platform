"""
Unit tests for the Llama Guard runtime safety classifier.
No live Ollama connection needed — all HTTP calls are mocked.

pytest backend/tests/test_llama_guard.py
"""
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval_engine.safety.llama_guard import (
    _extract_json_object,
    _normalize_safety_flag,
    classify_runtime_safety,
)

# ── helpers ───────────────────────────────────────────────────────────────────

def _make_mock_client(post_return_value):
    """Return an AsyncMock that mimics the shared httpx.AsyncClient."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=post_return_value)
    return mock_client


# ── _extract_json_object ──────────────────────────────────────────────────────

class TestExtractJsonObject:
    def test_clean_json_string(self):
        result = _extract_json_object('{"label": "safe", "flag": ""}')
        assert result == {"label": "safe", "flag": ""}

    def test_json_embedded_in_text(self):
        text = 'Sure! Result: {"label": "unsafe", "flag": "harmful"} done.'
        result = _extract_json_object(text)
        assert result is not None
        assert result["label"] == "unsafe"

    def test_empty_string_returns_none(self):
        assert _extract_json_object("") is None

    def test_none_input_returns_none(self):
        assert _extract_json_object(None) is None

    def test_no_json_returns_none(self):
        assert _extract_json_object("This is plain text with no JSON.") is None

    def test_malformed_json_returns_none(self):
        assert _extract_json_object("{not valid json}") is None

    def test_multiline_json(self):
        text = '{\n  "label": "unsafe",\n  "flag": "violence",\n  "confidence": 0.9\n}'
        result = _extract_json_object(text)
        assert result == {"label": "unsafe", "flag": "violence", "confidence": 0.9}


# ── _normalize_safety_flag ────────────────────────────────────────────────────

class TestNormalizeSafetyFlag:
    def test_simple_word(self):
        assert _normalize_safety_flag("violence") == "violence"

    def test_spaces_converted_to_underscores(self):
        assert _normalize_safety_flag("harmful content") == "harmful_content"

    def test_hyphens_converted_to_underscores(self):
        assert _normalize_safety_flag("hate-speech") == "hate_speech"

    def test_special_chars_stripped(self):
        assert _normalize_safety_flag("s3xual!@#$") == "s3xual"

    def test_empty_string_returns_default(self):
        assert _normalize_safety_flag("") == "unsafe_content"

    def test_whitespace_only_returns_default(self):
        assert _normalize_safety_flag("   ") == "unsafe_content"

    def test_uppercase_lowercased(self):
        assert _normalize_safety_flag("VIOLENCE") == "violence"

    def test_none_input_returns_default(self):
        assert _normalize_safety_flag(None) == "unsafe_content"


# ── classify_runtime_safety ───────────────────────────────────────────────────

@pytest.fixture()
def mock_settings_disabled(monkeypatch):
    settings = MagicMock()
    settings.llama_guard_enabled = False
    monkeypatch.setattr(
        "eval_engine.safety.llama_guard.get_settings", lambda: settings
    )
    return settings


@pytest.fixture()
def mock_settings_enabled(monkeypatch):
    settings = MagicMock()
    settings.llama_guard_enabled = True
    settings.llama_guard_model_id = "llama-guard3:8b"
    settings.llama_guard_timeout_seconds = 10.0
    settings.ollama_base_url = "http://localhost:11434"
    monkeypatch.setattr(
        "eval_engine.safety.llama_guard.get_settings", lambda: settings
    )
    return settings


@pytest.mark.asyncio
async def test_disabled_returns_none(mock_settings_disabled):
    flag, conf = await classify_runtime_safety("hello", "world")
    assert flag is None
    assert conf is None


@pytest.mark.asyncio
async def test_empty_inputs_returns_none(mock_settings_enabled):
    flag, conf = await classify_runtime_safety("", "")
    assert flag is None
    assert conf is None


def _make_httpx_response(body: dict):
    """Build a fake httpx.Response-like object."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"response": json.dumps(body)}
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


@pytest.mark.asyncio
async def test_safe_response_returns_no_flag(mock_settings_enabled):
    response_body = {"label": "safe", "flag": "", "confidence": 0.99}
    mock_resp = _make_httpx_response(response_body)
    mock_client = _make_mock_client(mock_resp)

    with patch("eval_engine.safety.llama_guard._get_llama_client", return_value=mock_client):
        flag, conf = await classify_runtime_safety("What is the capital of France?", "Paris.")

    assert flag is None
    assert conf == pytest.approx(0.99)


@pytest.mark.asyncio
async def test_unsafe_response_returns_flag(mock_settings_enabled):
    response_body = {"label": "unsafe", "flag": "harmful content", "confidence": 0.95}
    mock_resp = _make_httpx_response(response_body)
    mock_client = _make_mock_client(mock_resp)

    with patch("eval_engine.safety.llama_guard._get_llama_client", return_value=mock_client):
        flag, conf = await classify_runtime_safety("How do I make a bomb?", "Here are the steps...")

    assert flag == "harmful_content"
    assert conf == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_network_error_returns_none(mock_settings_enabled):
    """Any HTTP failure should be swallowed — never crash the caller."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))

    with patch("eval_engine.safety.llama_guard._get_llama_client", return_value=mock_client):
        flag, conf = await classify_runtime_safety("test prompt", "test response")

    assert flag is None
    assert conf is None


@pytest.mark.asyncio
async def test_unparseable_response_returns_none(mock_settings_enabled):
    """Gibberish from the model should not crash classification."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"response": "I am unable to classify this."}
    mock_resp.raise_for_status = MagicMock()

    mock_client = _make_mock_client(mock_resp)

    with patch("eval_engine.safety.llama_guard._get_llama_client", return_value=mock_client):
        flag, conf = await classify_runtime_safety("test prompt", "test response")

    assert flag is None
    assert conf is None


@pytest.mark.asyncio
async def test_confidence_clamped_to_01(mock_settings_enabled):
    """Out-of-range confidence values must be clipped."""
    response_body = {"label": "unsafe", "flag": "spam", "confidence": 1.5}
    mock_resp = _make_httpx_response(response_body)
    mock_client = _make_mock_client(mock_resp)

    with patch("eval_engine.safety.llama_guard._get_llama_client", return_value=mock_client):
        flag, conf = await classify_runtime_safety("buy now!", "click here!")

    assert flag == "spam"
    assert conf == pytest.approx(1.0)
