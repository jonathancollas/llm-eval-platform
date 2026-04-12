import logging
from typing import Optional

import httpx

from core.config import get_settings

logger = logging.getLogger(__name__)


class PromptInjectionDetectedError(RuntimeError):
    """Raised when Lakera Guard flags prompt injection."""


async def screen_prompt_with_lakera(prompt: str, system_prompt: Optional[str] = None) -> None:
    """
    Screen prompt content with Lakera Guard when configured.
    Fail-open by default to avoid runtime outages when guard service is unavailable.
    """
    settings = get_settings()
    if not settings.lakera_guard_api_key:
        return

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        async with httpx.AsyncClient(timeout=settings.lakera_guard_timeout_seconds) as client:
            response = await client.post(
                settings.lakera_guard_url,
                json={"messages": messages, "breakdown": True},
                headers={"Authorization": f"Bearer {settings.lakera_guard_api_key}"},
            )
            response.raise_for_status()
            payload = response.json() or {}
    except Exception as exc:
        if settings.lakera_guard_fail_closed:
            raise RuntimeError("Lakera Guard request failed in fail-closed mode.") from exc
        logger.warning("Lakera Guard request failed; continuing in fail-open mode.")
        return

    flagged = bool(payload.get("flagged"))
    breakdown = payload.get("breakdown")
    prompt_injection = isinstance(breakdown, dict) and bool(breakdown.get("prompt_injection"))
    should_block = flagged and (prompt_injection or breakdown is None)

    if should_block:
        request_uuid = ""
        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            request_uuid = str(metadata.get("request_uuid") or "")
        suffix = f" Request ID: {request_uuid}" if request_uuid else ""
        raise PromptInjectionDetectedError(
            f"Prompt blocked by Lakera Guard (prompt injection detected).{suffix}"
        )
