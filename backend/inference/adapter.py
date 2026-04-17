"""
Unified Inference Adapter Layer
================================
Single abstract interface over all model providers.

Scientific grounding: INESIA doctrine — the evaluation engine must be
provider-agnostic to enable reproducible, comparable evaluations across
model classes (API-only, open-weight, local).

Usage:
    from inference import get_adapter
    adapter = get_adapter(model)
    result = await adapter.complete("What is 2+2?")
    print(result.text, result.latency_ms, result.cost_usd)
"""
from __future__ import annotations

import asyncio
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

from core.lakera_guard import screen_prompt_with_lakera

logger = logging.getLogger(__name__)


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class AdapterResult:
    """Unified result from any inference provider."""
    text: str
    latency_ms: int
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    model_used: str = ""
    provider: str = ""
    finish_reason: str = "stop"
    error: Optional[str] = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


# ── Abstract base ─────────────────────────────────────────────────────────────

class InferenceAdapter(ABC):
    """
    Abstract base for all inference providers.

    All evaluation runners must use this interface — never call
    provider APIs directly. This ensures:
    - Consistent error handling across providers
    - Reproducible benchmark results
    - Easy provider switching without eval code changes
    """

    def __init__(self, model_id: str, **kwargs):
        self.model_id = model_id
        self.kwargs = kwargs

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> AdapterResult:
        """Generate a completion. Returns AdapterResult with text + metadata."""
        ...

    async def health_check(self) -> bool:
        """Returns True if this adapter is reachable."""
        try:
            result = await asyncio.wait_for(
                self.complete("ping", max_tokens=5),
                timeout=5.0,
            )
            return result.error is None
        except Exception:
            logger.debug("[adapter] health_check failed for %r", self, exc_info=True)
            return False

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model_id={self.model_id!r})"

    async def _screen_prompt(self, prompt: str, system_prompt: Optional[str] = None) -> None:
        await screen_prompt_with_lakera(prompt=prompt, system_prompt=system_prompt)


# ── LiteLLM adapter (OpenAI-compatible: OpenRouter, Groq, Mistral…) ──────────

class LiteLLMAdapter(InferenceAdapter):
    """
    OpenAI-compatible adapter via LiteLLM.
    Covers: OpenRouter, OpenAI, Groq, Mistral, and any openai-compatible endpoint.
    """

    async def complete(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> AdapterResult:
        from litellm import acompletion

        await self._screen_prompt(prompt, system_prompt)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        t0 = time.time()
        try:
            kwargs = {
                "model": self.model_id,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if self.kwargs.get("api_base"):
                kwargs["api_base"] = self.kwargs["api_base"]
            if self.kwargs.get("api_key"):
                kwargs["api_key"] = self.kwargs["api_key"]

            resp = await acompletion(**kwargs)
            latency = int((time.time() - t0) * 1000)
            choice = resp.choices[0]
            usage = resp.usage or {}

            return AdapterResult(
                text=(choice.message.content or "").strip(),
                latency_ms=latency,
                input_tokens=getattr(usage, "prompt_tokens", 0),
                output_tokens=getattr(usage, "completion_tokens", 0),
                cost_usd=getattr(resp, "_hidden_params", {}).get("response_cost", 0.0) or 0.0,
                model_used=resp.model or self.model_id,
                provider="litellm",
                finish_reason=choice.finish_reason or "stop",
            )
        except Exception as e:
            return AdapterResult(
                text="",
                latency_ms=int((time.time() - t0) * 1000),
                provider="litellm",
                error=str(e)[:300],
            )


# ── Anthropic adapter ─────────────────────────────────────────────────────────

class AnthropicAdapter(InferenceAdapter):
    """
    Direct Anthropic API adapter.
    Use for Claude models when precise token counting and billing are required.
    """

    async def complete(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> AdapterResult:
        import anthropic
        from core.config import get_settings

        await self._screen_prompt(prompt, system_prompt)
        settings = get_settings()
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        t0 = time.time()
        try:
            msg = await client.messages.create(
                model=self.model_id,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt or "You are a helpful AI assistant.",
                messages=[{"role": "user", "content": prompt}],
            )
            latency = int((time.time() - t0) * 1000)
            text = "".join(b.text for b in msg.content if hasattr(b, "text"))

            return AdapterResult(
                text=text.strip(),
                latency_ms=latency,
                input_tokens=msg.usage.input_tokens,
                output_tokens=msg.usage.output_tokens,
                model_used=msg.model,
                provider="anthropic",
                finish_reason=msg.stop_reason or "stop",
            )
        except Exception as e:
            return AdapterResult(
                text="",
                latency_ms=int((time.time() - t0) * 1000),
                provider="anthropic",
                error=str(e)[:300],
            )


# ── Ollama adapter (local) ────────────────────────────────────────────────────

class OllamaAdapter(InferenceAdapter):
    """
    Local Ollama inference adapter.
    Supports open-weight models running on localhost:11434.
    Free, fast, no data leaves the machine — preferred for sensitive evaluations.
    """

    def __init__(self, model_id: str, base_url: str = "http://localhost:11434", **kwargs):
        super().__init__(model_id, **kwargs)
        self.base_url = base_url

    async def complete(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> AdapterResult:
        import httpx

        await self._screen_prompt(prompt, system_prompt)
        payload = {
            "model": self.model_id,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if system_prompt:
            payload["system"] = system_prompt

        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(f"{self.base_url}/api/generate", json=payload)
                resp.raise_for_status()
                data = resp.json()
                latency = int((time.time() - t0) * 1000)

                return AdapterResult(
                    text=(data.get("response") or "").strip(),
                    latency_ms=latency,
                    input_tokens=data.get("prompt_eval_count", 0),
                    output_tokens=data.get("eval_count", 0),
                    model_used=data.get("model", self.model_id),
                    provider="ollama",
                    finish_reason="stop" if data.get("done") else "length",
                )
        except Exception as e:
            return AdapterResult(
                text="",
                latency_ms=int((time.time() - t0) * 1000),
                provider="ollama",
                error=str(e)[:300],
            )

    async def health_check(self) -> bool:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                return r.status_code == 200
        except Exception:
            logger.debug("[adapter] Ollama health_check failed for %r", self, exc_info=True)
            return False

    async def list_models(self) -> list[str]:
        """Returns names of locally installed Ollama models."""
        import httpx
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                if r.status_code == 200:
                    return [m["name"] for m in r.json().get("models", [])]
        except Exception as e:
            logger.debug(f"Ollama list_models failed: {e}")
        return []


# ── HuggingFace Inference API adapter ────────────────────────────────────────

class HuggingFaceAdapter(InferenceAdapter):
    """
    HuggingFace Inference API adapter.
    Covers gated models accessible via HF token.
    """

    def __init__(self, model_id: str, hf_token: str = "", **kwargs):
        super().__init__(model_id, **kwargs)
        self.hf_token = hf_token

    async def complete(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> AdapterResult:
        import httpx

        # Use LiteLLM for HF models — it handles the API format
        from inference.adapter import LiteLLMAdapter
        wrapped = LiteLLMAdapter(
            f"huggingface/{self.model_id}",
            api_key=self.hf_token,
        )
        return await wrapped.complete(prompt, system_prompt, temperature, max_tokens)


# ── Factory ───────────────────────────────────────────────────────────────────

def get_adapter(model) -> InferenceAdapter:
    """
    Factory — returns the correct adapter for a given LLMModel.

    Priority logic:
    1. Ollama provider → OllamaAdapter
    2. Anthropic provider → AnthropicAdapter (direct, better billing)
    3. Everything else → LiteLLMAdapter (OpenRouter, OpenAI, Groq, Mistral, custom)
    """
    from core.config import get_settings
    settings = get_settings()

    provider = str(getattr(model, "provider", "custom")).lower()
    model_id = getattr(model, "model_id", "")
    endpoint = getattr(model, "endpoint", "") or ""

    if provider == "ollama":
        return OllamaAdapter(
            model_id=model_id,
            base_url=settings.ollama_base_url or "http://localhost:11434",
        )

    if provider == "anthropic":
        return AnthropicAdapter(model_id=model_id)

    # OpenRouter / OpenAI / Groq / Mistral / custom via LiteLLM
    kwargs = {}
    if endpoint:
        kwargs["api_base"] = endpoint
    # Decrypt API key if stored
    try:
        from core.security import decrypt_api_key
        encrypted = getattr(model, "api_key_encrypted", None)
        if encrypted:
            kwargs["api_key"] = decrypt_api_key(encrypted)
    except Exception as e:
        logger.warning(f"Failed to decrypt API key for model {getattr(model, 'model_id', '?')}: {e}")

    return LiteLLMAdapter(model_id=model_id, **kwargs)


async def adapter_health_dashboard() -> list[dict]:
    """Returns health status of all configured inference providers."""
    from core.config import get_settings
    settings = get_settings()

    results = []

    # Ollama
    ollama = OllamaAdapter("test", base_url=settings.ollama_base_url or "http://localhost:11434")
    ollama_ok = await ollama.health_check()
    models = await ollama.list_models() if ollama_ok else []
    results.append({
        "provider": "Ollama (local)",
        "status": "online" if ollama_ok else "offline",
        "models": models,
        "cost": "free",
    })

    # Anthropic
    anthropic_configured = bool(settings.anthropic_api_key)
    results.append({
        "provider": "Anthropic",
        "status": "configured" if anthropic_configured else "not configured",
        "models": ["claude-sonnet-4-20250514", "claude-opus-4-20250514"] if anthropic_configured else [],
        "cost": "per-token",
    })

    # OpenRouter
    results.append({
        "provider": "OpenRouter",
        "status": "via litellm",
        "models": ["350+ models"],
        "cost": "per-token",
    })

    return results
