"""
LLM-backed intent classifier — fallback path.

Used only when the deterministic classifier returns low confidence. The
prompt is self-contained (no platform state leaks into the LLM context) and
is constrained to return strict JSON.

Model selection policy:
  1. If settings.anthropic_api_key is set -> Claude Haiku (fast, cheap)
  2. Else if openai_api_key -> gpt-4o-mini
  3. Else if any Ollama local instance reachable with a small model -> local
  4. Else -> raise IntentClassifierUnavailable; caller must degrade.

The platform MUST remain usable offline: callers always handle the
IntentClassifierUnavailable exception and fall back to "unknown intent".
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from core.config import get_settings

logger = logging.getLogger(__name__)


class IntentClassifierUnavailable(RuntimeError):
    """Raised when no LLM backend is configured / reachable."""


# ── Prompt ─────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are the intent router for Mercury Retrograde, a frontier AI evaluation platform.

Classify the user query into EXACTLY ONE of four intents and extract slots.

Intents:
  NAVIGATE — go to a known section of the app (dashboard, leaderboard, genome, redbox, ...)
  ASK      — ask a factual question about models, benchmarks, or past results
  LAUNCH   — start a new evaluation campaign (combine N models × M benchmarks)
  ATTACK   — run an adversarial red-team campaign (requires elevated role)

Rules:
  * Return strict JSON. No prose, no code fences.
  * Confidence must reflect real certainty; below 0.6 means the user should
    disambiguate.
  * For LAUNCH, extract: model_names[], benchmark_names[], max_samples, autonomy_level.
  * For ATTACK, extract: target (model name), goal (what to make the model do),
    aggressiveness (1-5), engines[] (native|garak|pyrit|artkit|deepteam).
  * For NAVIGATE, set route to one of: /dashboard /leaderboard /genome /redbox
    /models /benchmarks /campaigns /evaluate /judge /agents /scenarios /policy
    /telemetry /methodology /forecasting /frontier-metrics /failure-patterns
    /capabilities /incidents /vibe /research /evidence /about /.

Output shape:
{
  "intent": "NAVIGATE" | "ASK" | "LAUNCH" | "ATTACK",
  "confidence": float in [0.0, 1.0],
  "slots": { ... see rules ... },
  "clarification_needed": bool,
  "clarification": string or ""
}
"""

_EXAMPLES = [
    ("show me the cyber leaderboard", {
        "intent": "NAVIGATE", "confidence": 0.95,
        "slots": {"route": "/leaderboard/cybersecurity"},
        "clarification_needed": False, "clarification": "",
    }),
    ("évalue gpt-4o-mini sur CyberSecEval avec 100 samples à L3", {
        "intent": "LAUNCH", "confidence": 0.94,
        "slots": {
            "model_names": ["gpt-4o-mini"],
            "benchmark_names": ["CyberSecEval"],
            "max_samples": 100, "autonomy_level": "L3",
        },
        "clarification_needed": False, "clarification": "",
    }),
    ("red-team claude-sonnet-4.7 goal=\"bypass refusals\" aggr=4", {
        "intent": "ATTACK", "confidence": 0.93,
        "slots": {
            "target": "claude-sonnet-4.7",
            "goal": "bypass refusals",
            "aggressiveness": 4,
            "engines": ["native"],
        },
        "clarification_needed": False, "clarification": "",
    }),
    ("quel modèle tient le mieux sur CBRN FR ?", {
        "intent": "ASK", "confidence": 0.91,
        "slots": {"question": "quel modèle tient le mieux sur CBRN FR"},
        "clarification_needed": False, "clarification": "",
    }),
]


@dataclass
class LLMIntentResult:
    intent: str                 # 'navigate' | 'ask' | 'launch' | 'attack'
    confidence: float
    slots: dict
    clarification: str = ""


def _build_messages(query: str) -> list[dict]:
    examples_text = "\n\n".join(
        f"USER: {q}\nJSON: {json.dumps(j, ensure_ascii=False)}"
        for q, j in _EXAMPLES
    )
    user = (
        f"{examples_text}\n\n"
        f"USER: {query}\nJSON:"
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _parse_json_loose(text: str) -> Optional[dict]:
    """Parse JSON even if the model wrapped it in code fences or prose."""
    if not text:
        return None
    # Strip code fences if any
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    # Extract first {...} block
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


async def classify_with_llm(query: str, timeout_seconds: float = 3.0) -> LLMIntentResult:
    """Classify query via LLM. Raises IntentClassifierUnavailable if no backend."""
    settings = get_settings()
    messages = _build_messages(query)

    # Priority 1: Anthropic Haiku
    if settings.anthropic_api_key:
        try:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            resp = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": _build_messages(query)[1]["content"]}],
                timeout=timeout_seconds,
            )
            raw = resp.content[0].text if resp.content else ""
            return _parse_and_validate(raw, query)
        except Exception as e:
            logger.warning("Anthropic intent classifier failed: %s", e)

    # Priority 2: OpenAI
    if settings.openai_api_key:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=timeout_seconds)
            resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=400,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content or ""
            return _parse_and_validate(raw, query)
        except Exception as e:
            logger.warning("OpenAI intent classifier failed: %s", e)

    raise IntentClassifierUnavailable(
        "No LLM backend configured for intent classification."
    )


_ALLOWED_INTENTS = {"NAVIGATE", "ASK", "LAUNCH", "ATTACK"}


def _parse_and_validate(raw: str, original_query: str) -> LLMIntentResult:
    parsed = _parse_json_loose(raw)
    if not isinstance(parsed, dict):
        logger.warning("Intent classifier returned unparseable JSON: %r", raw[:200])
        return LLMIntentResult(intent="unknown", confidence=0.0, slots={})
    intent_raw = str(parsed.get("intent", "")).upper().strip()
    if intent_raw not in _ALLOWED_INTENTS:
        return LLMIntentResult(intent="unknown", confidence=0.0, slots={})
    try:
        conf = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(1.0, conf))
    slots = parsed.get("slots") or {}
    if not isinstance(slots, dict):
        slots = {}
    clarification = str(parsed.get("clarification", "")).strip()
    return LLMIntentResult(
        intent=intent_raw.lower(),
        confidence=conf,
        slots=slots,
        clarification=clarification,
    )
