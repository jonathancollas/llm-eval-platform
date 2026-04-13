"""
LiteLLM wrapper — unified interface to cloud LLM providers.
Supports OpenRouter (300+ models), OpenAI, Anthropic, Mistral, Groq.
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
from core.lakera_guard import screen_prompt_with_lakera

logger = logging.getLogger(__name__)
litellm.set_verbose = False
litellm.drop_params = True
litellm.suppress_debug_info = True  # Suppress stdout spam

# Silence ALL LiteLLM loggers
import logging as _logging
for _name in list(_logging.Logger.manager.loggerDict.keys()):
    if "litellm" in _name.lower() or "LiteLLM" in _name:
        _logging.getLogger(_name).setLevel(_logging.ERROR)
for _noisy in ["LiteLLM", "LiteLLM Router", "LiteLLM Proxy", "litellm"]:
    _logging.getLogger(_noisy).setLevel(_logging.ERROR)     # Ignore unsupported params silently

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass
class CompletionResult:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_usd: float
    model_id: str
    guardrails: dict | None = None


def _is_openrouter(model: LLMModel) -> bool:
    return (model.endpoint or "").rstrip("/") == OPENROUTER_BASE_URL.rstrip("/")


def _build_litellm_model_str(model: LLMModel) -> str:
    if _is_openrouter(model):
        raw_id = model.model_id.removeprefix("openrouter/")
        return f"openrouter/{raw_id}"
    match model.provider:
        case ModelProvider.OPENAI:    return model.model_id
        case ModelProvider.ANTHROPIC: return f"anthropic/{model.model_id}"
        case ModelProvider.MISTRAL:   return f"mistral/{model.model_id}"
        case ModelProvider.GROQ:      return f"groq/{model.model_id}"
        case ModelProvider.OLLAMA:    return f"ollama/{model.model_id}"
        case ModelProvider.CUSTOM:
            return f"openai/{model.model_id}"
        case _:
            return model.model_id


def _build_kwargs(model: LLMModel, temperature: float, max_tokens: int) -> dict:
    kwargs: dict = {}
    settings = get_settings()

    # Endpoint
    if _is_openrouter(model):
        kwargs["api_base"] = OPENROUTER_BASE_URL
    elif model.provider == ModelProvider.OLLAMA:
        kwargs["api_base"] = model.endpoint or settings.ollama_base_url
    elif model.provider == ModelProvider.CUSTOM and model.endpoint:
        kwargs["api_base"] = model.endpoint

    # API key — encrypted stored key takes priority, then env vars
    if model.api_key_encrypted:
        api_key = decrypt_api_key(model.api_key_encrypted)
    elif _is_openrouter(model):
        api_key = settings.openrouter_api_key
    else:
        api_key = {
            ModelProvider.OPENAI:    settings.openai_api_key,
            ModelProvider.ANTHROPIC: settings.anthropic_api_key,
            ModelProvider.MISTRAL:   settings.mistral_api_key,
            ModelProvider.GROQ:      settings.groq_api_key,
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
    output_schema: Optional[dict] = None,
    safety_constraints: Optional[dict] = None,
) -> CompletionResult:
    settings = get_settings()
    await screen_prompt_with_lakera(prompt=prompt, system_prompt=system_prompt)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    model_str = _build_litellm_model_str(model)
    kwargs = _build_kwargs(model, temperature, max_tokens)

    t0 = time.monotonic()
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = await asyncio.wait_for(
                acompletion(
                    model=model_str,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                ),
                timeout=settings.llm_timeout_seconds,
            )
            break  # Success
        except asyncio.TimeoutError:
            raise TimeoutError(f"LLM call timed out after {settings.llm_timeout_seconds}s ({model_str})")
        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = "ratelimit" in err_str or "rate limit" in err_str or "429" in err_str
            is_server_error = "500" in err_str or "502" in err_str or "503" in err_str or "server error" in err_str
            if is_rate_limit and attempt < max_retries - 1:
                wait = 10 * (attempt + 1)  # 10s, 20s
                logger.warning(f"Rate limited on {model_str} (attempt {attempt+1}/{max_retries}), waiting {wait}s...")
                await asyncio.sleep(wait)
                continue
            if is_server_error and attempt < max_retries - 1:
                wait = 5 * (attempt + 1)  # 5s, 10s
                logger.warning(f"Server error on {model_str} (attempt {attempt+1}/{max_retries}), retrying in {wait}s...")
                await asyncio.sleep(wait)
                continue
            logger.error(f"LiteLLM call failed for {model_str}: {type(e).__name__}: {_sanitize_error(str(e)[:200])}")
            raise

    # Success path — extract response
    latency_ms = int((time.monotonic() - t0) * 1000)
    text = response.choices[0].message.content or ""
    guardrails_meta = None

    if output_schema or safety_constraints:
        from eval_engine.guardrails_runtime import apply_guardrails

        validation = apply_guardrails(
            text=text,
            output_schema=output_schema,
            safety_constraints=safety_constraints,
        )
        guardrails_meta = {
            "passed": validation.passed,
            "schema_valid": validation.schema_valid,
            "safety_valid": validation.safety_valid,
            "violations": validation.violations,
            "validator": validation.validator,
        }

        fail_closed = bool((safety_constraints or {}).get("fail_closed"))
        if output_schema and validation.parsed_output is not None:
            import json
            text = json.dumps(validation.parsed_output, ensure_ascii=False)
        if fail_closed and not validation.passed:
            raise ValueError(f"Guardrails validation failed: {', '.join(validation.violations[:3])}")

    usage = response.usage or {}
    input_tokens = getattr(usage, "prompt_tokens", 0) or 0
    output_tokens = getattr(usage, "completion_tokens", 0) or 0

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
        guardrails=guardrails_meta,
    )


def _sanitize_error(msg: str) -> str:
    """Strip potential API keys from error messages."""
    import re
    return re.sub(r'(sk-|key-|Bearer )[a-zA-Z0-9\-_]{10,}', r'\1***REDACTED***', msg)


async def test_connection(model: LLMModel) -> dict:
    try:
        result = await complete(
            model=model,
            prompt='Reply with exactly one word: "OK"',
            temperature=0.0,
            max_tokens=10,
        )
        return {"ok": True, "latency_ms": result.latency_ms, "response": result.text, "error": None}
    except Exception as e:
        return {"ok": False, "latency_ms": 0, "response": "", "error": str(e)}
