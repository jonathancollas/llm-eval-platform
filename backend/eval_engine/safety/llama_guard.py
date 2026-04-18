"""
Runtime safety classification using Llama Guard via Ollama.
"""
from __future__ import annotations

import functools
import json
import logging
import re
from typing import Optional, Tuple

import httpx

from core.config import get_settings

logger = logging.getLogger(__name__)

# Shared client — reused across calls to avoid per-request TCP connection overhead.
# lru_cache(maxsize=1) ensures a single instance is created even under concurrent
# coroutine scheduling, while keeping the initialisation lazy (settings available).


@functools.lru_cache(maxsize=1)
def _get_llama_client() -> httpx.AsyncClient:
    settings = get_settings()
    return httpx.AsyncClient(timeout=settings.llama_guard_timeout_seconds)


def _extract_json_object(text: str) -> Optional[dict]:
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        logger.debug("[llama-guard] direct JSON parse failed, trying regex extraction", exc_info=True)

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        logger.debug("[llama-guard] failed to parse regex-extracted JSON object", exc_info=True)
        return None


def _normalize_safety_flag(raw_flag: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_ -]", "", raw_flag or "").strip().lower()
    cleaned = cleaned.replace(" ", "_").replace("-", "_")
    return cleaned or "unsafe_content"


async def classify_runtime_safety(prompt: str, response: str) -> Tuple[Optional[str], Optional[float]]:
    """
    Returns (safety_flag, confidence) using Llama Guard.
    - safety_flag is None when judged safe or on any non-fatal failure.
    """
    settings = get_settings()
    if not settings.llama_guard_enabled:
        return None, None
    if not (prompt or response):
        return None, None

    classifier_prompt = (
        "You are a safety classifier. Analyze the conversation and return JSON only.\n"
        "Schema: {\"label\":\"safe|unsafe\",\"flag\":\"short_snake_case_reason\",\"confidence\":0.0_to_1.0}\n"
        "If safe, set label=\"safe\" and flag=\"\".\n\n"
        f"User prompt:\n{prompt[:3000]}\n\n"
        f"Assistant response:\n{response[:3000]}"
    )

    payload = {
        "model": settings.llama_guard_model_id,
        "prompt": classifier_prompt,
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 80},
    }

    try:
        client = _get_llama_client()
        resp = await client.post(f"{settings.ollama_base_url}/api/generate", json=payload)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.debug(f"[llama-guard] classification failed: {exc}")
        return None, None

    parsed = _extract_json_object((data.get("response") or ""))
    if not parsed:
        return None, None

    raw_conf = parsed.get("confidence")
    confidence: Optional[float] = None
    try:
        if raw_conf is not None:
            confidence = max(0.0, min(1.0, float(raw_conf)))
    except Exception:
        logger.debug("[llama-guard] failed to parse confidence value %r", raw_conf, exc_info=True)
        confidence = None

    label = str(parsed.get("label", "")).strip().lower()
    if label != "unsafe":
        return None, confidence

    raw_flag = str(parsed.get("flag", "")).strip()
    return _normalize_safety_flag(raw_flag), confidence
