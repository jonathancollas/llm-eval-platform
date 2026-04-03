"""
LiteLLM wrapper that provides a unified interface to all model providers.
Handles Ollama (local) and cloud APIs transparently.
"""
import asyncio
import time
import logging
from dataclasses import dataclass
from typing import Optional

import litellm
from litellm import acompletion

from core.models import LLMModel, ModelProvider
from core.security import decrypt_api_key
from core.config import get_settings

logger = logging.getLogger(__name__)
litellm.set_verbose = False


@dataclass
class CompletionResult:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_usd: float
    model_id: str


def _build_litellm_model_str(model: LLMModel) -> str:
    """Map our model record to the LiteLLM model string format."""
    match model.provider:
        case ModelProvider.OLLAMA:
            return f"ollama/{model.model_id}"
        case ModelProvider.OPENAI:
            return model.model_id  # e.g. "gpt-4o-mini"
        case ModelProvider.ANTHROPIC:
            return f"anthropic/{model.model_id}"
        case ModelProvider.MISTRAL:
            return f"mistral/{model.model_id}"
        case ModelProvider.GROQ:
            return f"groq/{model.model_id}"
        case ModelProvider.CUSTOM:
            return f"openai/{model.model_id}"  # assume OpenAI-compatible
        case _:
            return model.model_id


def _build_kwargs(model: LLMModel, temperature: float, max_tokens: int) -> dict:
    """Build extra kwargs for LiteLLM call."""
    kwargs: dict = {}
    settings = get_settings()

    if model.provider == ModelProvider.OLLAMA:
        kwargs["api_base"] = model.endpoint or settings.ollama_base_url

    elif model.provider == ModelProvider.CUSTOM and model.endpoint:
        kwargs["api_base"] = model.endpoint

    # API key
    if model.api_key_encrypted:
        api_key = decrypt_api_key(model.api_key_encrypted)
    else:
        # Fall back to env vars
        api_key = {
            ModelProvider.OPENAI: settings.openai_api_key,
            ModelProvider.ANTHROPIC: settings.anthropic_api_key,
            ModelProvider.MISTRAL: settings.mistral_api_key,
            ModelProvider.GROQ: settings.groq_api_key,
        }.get(model.provider, "")

    if api_key:
        kwargs["api_key"] = api_key

    return kwargs


async def complete(
    model: LLMModel,
    prompt: str,
    temperature: float = 0.0,
    max_tokens: int = 256,
    system_prompt: Optional[str] = None,
) -> CompletionResult:
    """Single completion call via LiteLLM."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    model_str = _build_litellm_model_str(model)
    kwargs = _build_kwargs(model, temperature, max_tokens)

    t0 = time.monotonic()
    try:
        response = await acompletion(
            model=model_str,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
    except Exception as e:
        logger.error(f"LiteLLM call failed for {model_str}: {e}")
        raise

    latency_ms = int((time.monotonic() - t0) * 1000)
    choice = response.choices[0]
    text = choice.message.content or ""

    usage = response.usage or {}
    input_tokens = getattr(usage, "prompt_tokens", 0) or 0
    output_tokens = getattr(usage, "completion_tokens", 0) or 0

    # Cost estimation (USD)
    cost = (
        input_tokens / 1000 * model.cost_input_per_1k
        + output_tokens / 1000 * model.cost_output_per_1k
    )

    return CompletionResult(
        text=text.strip(),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        cost_usd=cost,
        model_id=model_str,
    )


async def test_connection(model: LLMModel) -> dict:
    """
    Quick connection test — send a minimal prompt and check for a valid response.
    Returns {"ok": bool, "latency_ms": int, "error": str | None}
    """
    try:
        result = await complete(
            model=model,
            prompt='Reply with exactly one word: "OK"',
            temperature=0.0,
            max_tokens=10,
        )
        return {
            "ok": True,
            "latency_ms": result.latency_ms,
            "response": result.text,
            "error": None,
        }
    except Exception as e:
        return {"ok": False, "latency_ms": 0, "response": "", "error": str(e)}
