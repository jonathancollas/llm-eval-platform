"""Shared utility functions."""
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def safe_json_load(value: Any, fallback: Any = None) -> Any:
    """Parse JSON safely — returns fallback on None, empty string, or malformed JSON."""
    if not value:
        return fallback if fallback is not None else {}
    if isinstance(value, (list, dict)):
        return value  # already parsed
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.warning(f"Failed to parse JSON: {repr(value)[:100]}")
        return fallback if fallback is not None else {}


def safe_extract_text(message) -> str:
    """Safely extract text from an Anthropic API message response.
    Handles None message, empty content, or missing text attribute.
    """
    if message is None:
        return ""
    content = getattr(message, "content", None)
    if not content or not isinstance(content, list) or len(content) == 0:
        return ""
    block = content[0]
    text = getattr(block, "text", None)
    return text.strip() if text else ""


async def generate_text(
    prompt: str,
    system_prompt: str = "",
    max_tokens: int = 2048,
    timeout: float = None,
    model_override: str | None = None,
    ollama_model: str | None = None,
) -> str:
    """Generate text using the best available model.
    Priority: ollama_model (explicit local) → model_override → Ollama auto → Anthropic API.
    Returns generated text or raises.
    """
    import asyncio
    from core.config import get_settings
    settings = get_settings()

    # Use configured timeout if not explicitly overridden
    if timeout is None:
        timeout = settings.report_timeout_seconds

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    # Option 0: explicit local Ollama model chosen by user
    if ollama_model:
        try:
            from litellm import acompletion
            resp = await asyncio.wait_for(
                acompletion(
                    model=f"ollama/{ollama_model}",
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=0.3,
                    api_base=settings.ollama_base_url,
                ),
                timeout=timeout,
            )
            return (resp.choices[0].message.content or "").strip()
        except (OSError, TimeoutError, asyncio.TimeoutError, ImportError, RuntimeError) as e:
            raise RuntimeError(f"Ollama model '{ollama_model}' failed: {e}") from e

    # Option 1: explicit model override (litellm format)
    if model_override:
        from litellm import acompletion
        resp = await asyncio.wait_for(
            acompletion(model=model_override, messages=messages, max_tokens=max_tokens, temperature=0.3),
            timeout=timeout,
        )
        return (resp.choices[0].message.content or "").strip()

    # Option 2: try Ollama local first (free, fast, no dependency)
    try:
        import httpx
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            tags = await client.get(f"{settings.ollama_base_url}/api/tags")
            if tags.status_code == 200:
                models = tags.json().get("models", [])
                if models:
                    # Pick the largest available model
                    best = sorted(models, key=lambda m: m.get("size", 0), reverse=True)[0]
                    model_name = best["name"]
                    from litellm import acompletion
                    resp = await asyncio.wait_for(
                        acompletion(
                            model=f"ollama/{model_name}",
                            messages=messages,
                            max_tokens=max_tokens,
                            temperature=0.3,
                            api_base=settings.ollama_base_url,
                        ),
                        timeout=timeout,
                    )
                    return (resp.choices[0].message.content or "").strip()
    except (OSError, TimeoutError, ImportError, KeyError, IndexError, RuntimeError) as _ollama_err:
        logger.debug(f"Ollama auto-detect unavailable: {_ollama_err}")  # Expected — not an error

    # Option 3: Anthropic API
    if settings.anthropic_api_key:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        msg = await asyncio.wait_for(
            client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                system=system_prompt if system_prompt else "You are a helpful AI evaluation expert.",
                messages=[{"role": "user", "content": prompt}],
            ),
            timeout=timeout,
        )
        return safe_extract_text(msg)

    raise RuntimeError("No model available for text generation. Configure Ollama or ANTHROPIC_API_KEY.")
