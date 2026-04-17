"""Tests for core/utils.py lines 130-211 — generate_text() with various backends."""
import asyncio
import os
import secrets
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))


# ── helpers ──────────────────────────────────────────────────────────────────

def _fake_completion_response(content: str):
    """Build a minimal litellm-style response object."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ── generate_text — ollama_model path ────────────────────────────────────────

def test_generate_text_ollama_model_success():
    fake_resp = _fake_completion_response("  ollama reply  ")

    async def fake_acompletion(**kwargs):
        return fake_resp

    async def run():
        from core.utils import generate_text
        with patch("litellm.acompletion", side_effect=fake_acompletion):
            result = await generate_text(
                prompt="hello",
                ollama_model="llama3",
                max_tokens=50,
                timeout=5.0,
            )
        return result

    result = asyncio.run(run())
    assert result == "ollama reply"


def test_generate_text_ollama_model_failure():
    async def fake_acompletion(**kwargs):
        raise OSError("connection refused")

    async def run():
        from core.utils import generate_text
        with patch("litellm.acompletion", side_effect=fake_acompletion):
            with pytest.raises(RuntimeError, match="Ollama model.*failed"):
                await generate_text(
                    prompt="hello",
                    ollama_model="llama3",
                    max_tokens=50,
                    timeout=5.0,
                )

    asyncio.run(run())


def test_generate_text_ollama_model_timeout():
    async def fake_acompletion(**kwargs):
        await asyncio.sleep(10)
        return _fake_completion_response("never")

    async def run():
        from core.utils import generate_text
        with patch("litellm.acompletion", side_effect=fake_acompletion):
            with pytest.raises(RuntimeError, match="Ollama model.*failed"):
                await generate_text(
                    prompt="hello",
                    ollama_model="llama3",
                    max_tokens=50,
                    timeout=0.01,
                )

    asyncio.run(run())


# ── generate_text — model_override path ──────────────────────────────────────

def test_generate_text_model_override_success():
    fake_resp = _fake_completion_response("override reply")

    async def fake_acompletion(**kwargs):
        assert kwargs["model"] == "gpt-3.5-turbo"
        return fake_resp

    async def run():
        from core.utils import generate_text
        with patch("litellm.acompletion", side_effect=fake_acompletion):
            result = await generate_text(
                prompt="hello",
                model_override="gpt-3.5-turbo",
                max_tokens=50,
                timeout=5.0,
            )
        return result

    result = asyncio.run(run())
    assert result == "override reply"


def test_generate_text_model_override_with_system_prompt():
    fake_resp = _fake_completion_response("sys-override reply")

    async def fake_acompletion(**kwargs):
        return fake_resp

    async def run():
        from core.utils import generate_text
        with patch("litellm.acompletion", side_effect=fake_acompletion):
            result = await generate_text(
                prompt="hello",
                system_prompt="You are helpful",
                model_override="gpt-4",
                max_tokens=100,
                timeout=5.0,
            )
        return result

    result = asyncio.run(run())
    assert result == "sys-override reply"


# ── generate_text — Ollama auto-detect path ───────────────────────────────────

def test_generate_text_ollama_auto_detect_success():
    tags_response = MagicMock()
    tags_response.status_code = 200
    tags_response.json.return_value = {
        "models": [
            {"name": "small-model", "size": 100},
            {"name": "big-model", "size": 1000},
        ]
    }
    fake_resp = _fake_completion_response("auto ollama reply")

    async def fake_acompletion(**kwargs):
        assert "big-model" in kwargs["model"]
        return fake_resp

    async def run():
        from core.utils import generate_text

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=tags_response)

        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch("litellm.acompletion", side_effect=fake_acompletion):
            result = await generate_text(
                prompt="hello",
                max_tokens=50,
                timeout=5.0,
            )
        return result

    result = asyncio.run(run())
    assert result == "auto ollama reply"


def test_generate_text_ollama_auto_detect_no_models():
    """No Ollama models available — falls through to Anthropic path (which raises)."""
    tags_response = MagicMock()
    tags_response.status_code = 200
    tags_response.json.return_value = {"models": []}

    async def run():
        from core.utils import generate_text

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=tags_response)

        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch("core.config.get_settings") as mock_settings:
            mock_settings.return_value.ollama_base_url = "http://localhost:11434"
            mock_settings.return_value.anthropic_api_key = ""
            mock_settings.return_value.http_timeout_seconds = 5
            mock_settings.return_value.report_timeout_seconds = 10
            with pytest.raises(RuntimeError, match="No model available"):
                await generate_text(prompt="hello", max_tokens=50, timeout=5.0)

    asyncio.run(run())


def test_generate_text_ollama_auto_detect_os_error():
    """Ollama unavailable (OSError) — falls through to Anthropic path."""
    async def run():
        from core.utils import generate_text

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=OSError("connection refused"))

        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch("core.config.get_settings") as mock_settings:
            mock_settings.return_value.ollama_base_url = "http://localhost:11434"
            mock_settings.return_value.anthropic_api_key = ""
            mock_settings.return_value.http_timeout_seconds = 5
            mock_settings.return_value.report_timeout_seconds = 10
            with pytest.raises(RuntimeError, match="No model available"):
                await generate_text(prompt="hello", max_tokens=50, timeout=5.0)

    asyncio.run(run())


def test_generate_text_ollama_tags_non_200():
    """Ollama /api/tags returns non-200 — falls through to Anthropic."""
    tags_response = MagicMock()
    tags_response.status_code = 503

    async def run():
        from core.utils import generate_text

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=tags_response)

        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch("core.config.get_settings") as mock_settings:
            mock_settings.return_value.ollama_base_url = "http://localhost:11434"
            mock_settings.return_value.anthropic_api_key = ""
            mock_settings.return_value.http_timeout_seconds = 5
            mock_settings.return_value.report_timeout_seconds = 10
            with pytest.raises(RuntimeError, match="No model available"):
                await generate_text(prompt="hello", max_tokens=50, timeout=5.0)

    asyncio.run(run())


# ── generate_text — Anthropic path ───────────────────────────────────────────

def test_generate_text_anthropic_success():
    """Falls through to Anthropic when Ollama unavailable."""
    content_block = MagicMock()
    content_block.text = "  anthropic reply  "
    msg_response = MagicMock()
    msg_response.content = [content_block]

    async def run():
        from core.utils import generate_text

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=OSError("no ollama"))

        mock_anthropic_client = MagicMock()
        mock_anthropic_client.messages = MagicMock()
        mock_anthropic_client.messages.create = AsyncMock(return_value=msg_response)

        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch("anthropic.AsyncAnthropic", return_value=mock_anthropic_client), \
             patch("core.config.get_settings") as mock_settings:
            mock_settings.return_value.ollama_base_url = "http://localhost:11434"
            mock_settings.return_value.anthropic_api_key = "sk-test-key"
            mock_settings.return_value.report_model = "claude-3-haiku-20240307"
            mock_settings.return_value.http_timeout_seconds = 5
            mock_settings.return_value.report_timeout_seconds = 30
            result = await generate_text(prompt="hello", max_tokens=100, timeout=30.0)

        return result

    result = asyncio.run(run())
    assert result == "anthropic reply"


def test_generate_text_anthropic_with_system_prompt():
    content_block = MagicMock()
    content_block.text = "sys anthropic reply"
    msg_response = MagicMock()
    msg_response.content = [content_block]

    async def run():
        from core.utils import generate_text

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=OSError("no ollama"))

        mock_anthropic_client = MagicMock()
        mock_anthropic_client.messages = MagicMock()
        mock_anthropic_client.messages.create = AsyncMock(return_value=msg_response)

        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch("anthropic.AsyncAnthropic", return_value=mock_anthropic_client), \
             patch("core.config.get_settings") as mock_settings:
            mock_settings.return_value.ollama_base_url = "http://localhost:11434"
            mock_settings.return_value.anthropic_api_key = "sk-test-key"
            mock_settings.return_value.report_model = "claude-3-haiku-20240307"
            mock_settings.return_value.http_timeout_seconds = 5
            mock_settings.return_value.report_timeout_seconds = 30
            result = await generate_text(
                prompt="hello",
                system_prompt="Be concise",
                max_tokens=100,
                timeout=30.0,
            )

        return result

    result = asyncio.run(run())
    assert result == "sys anthropic reply"


# ── generate_text — no model available ───────────────────────────────────────

def test_generate_text_no_model_raises():
    async def run():
        from core.utils import generate_text

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=OSError("no ollama"))

        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch("core.config.get_settings") as mock_settings:
            mock_settings.return_value.ollama_base_url = "http://localhost:11434"
            mock_settings.return_value.anthropic_api_key = ""  # no key
            mock_settings.return_value.http_timeout_seconds = 5
            mock_settings.return_value.report_timeout_seconds = 10
            with pytest.raises(RuntimeError, match="No model available"):
                await generate_text(prompt="hello", max_tokens=100, timeout=5.0)

    asyncio.run(run())


# ── generate_text — uses settings timeout when not explicitly given ───────────

def test_generate_text_uses_settings_timeout():
    fake_resp = _fake_completion_response("timout default reply")

    async def fake_acompletion(**kwargs):
        return fake_resp

    async def run():
        from core.utils import generate_text
        with patch("litellm.acompletion", side_effect=fake_acompletion), \
             patch("core.config.get_settings") as mock_settings:
            mock_settings.return_value.report_timeout_seconds = 60
            mock_settings.return_value.ollama_base_url = "http://localhost:11434"
            result = await generate_text(
                prompt="hello",
                model_override="gpt-3.5-turbo",
                max_tokens=50,
                timeout=None,  # should use settings
            )
        return result

    result = asyncio.run(run())
    assert result == "timout default reply"
