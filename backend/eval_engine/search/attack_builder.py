"""
Attack builder — turns extracted NL slots into a Red Room attack preview.

Policy:
  * ATTACK intent always requires explicit role check. The router enforces
    the role; the builder only flags that the role is required.
  * Goal MUST be present. If missing, we return a clarification.
  * Aggressiveness defaults to 3 (moderate). Range 1-5, validated.
  * We NEVER execute the attack from the builder. The user confirms and
    the frontend submits to /redbox/attack (existing endpoint).
"""
from __future__ import annotations

from typing import Optional

from sqlmodel import Session

from core.models import LLMModel
from eval_engine.search.resolvers import resolve_model
from eval_engine.search.schema import AttackPayload


_ALLOWED_ENGINES = {"native", "garak", "pyrit", "artkit", "deepteam", "openrt", "promptfoo"}
_DEFAULT_ENGINES = ["native"]


_ATTACK_VERBS_STRIP = (
    "red-team", "redteam", "red team", "attack", "attaque", "pentest",
    "jailbreak", "exploit",
)


def _scan_query_for_target(session: Session, query: str) -> Optional[str]:
    """Best-effort scan of the raw query for a model name when slots are empty.

    Drops the leading attack verb, then probes the resolver with the leading
    head of the query (3..1 tokens). Returns the candidate string for the
    first match with score >= 0.85, or None.
    """
    if not query:
        return None
    text = query.strip()
    lower = text.lower()
    for verb in _ATTACK_VERBS_STRIP:
        if lower.startswith(verb):
            text = text[len(verb):].strip(" \t:,")
            break
    # Stop at the first parameter-like marker.
    for marker in (" goal=", " goal ", " aggr=", " aggressiveness=", " engines="):
        idx = text.lower().find(marker)
        if idx >= 0:
            text = text[:idx]
    head_tokens = text.split()[:3]
    while head_tokens:
        cand = " ".join(head_tokens)
        results = resolve_model(session, cand, limit=1)
        if results and results[0].score >= 0.85:
            return cand
        head_tokens.pop()
    return None


def build_attack_preview(session: Session, slots: dict, query: str = "") -> AttackPayload:
    clarifications: list[str] = []

    # ── Resolve target model ─────────────────────────────────────────
    target_raw: Optional[str] = None
    if "target" in slots and slots["target"]:
        target_raw = str(slots["target"])
    elif "model_names" in slots and isinstance(slots["model_names"], list) and slots["model_names"]:
        target_raw = str(slots["model_names"][0])
    elif "model_name" in slots and slots["model_name"]:
        target_raw = str(slots["model_name"])
    elif query:
        target_raw = _scan_query_for_target(session, query)

    target_id: Optional[int] = None
    target_name: Optional[str] = None
    if target_raw:
        matches = resolve_model(session, target_raw, limit=3)
        if not matches:
            clarifications.append(f"No model matched '{target_raw}'.")
        else:
            top = matches[0]
            if top.score < 0.75 or (
                len(matches) > 1 and matches[1].score >= top.score - 0.05
            ):
                options = ", ".join(m.name for m in matches[:3])
                clarifications.append(f"Ambiguous target '{target_raw}'. Candidates: {options}.")
            else:
                full = session.get(LLMModel, top.id)
                if full:
                    target_id = full.id
                    target_name = full.name

    # ── Goal ─────────────────────────────────────────────────────────
    goal = str(slots.get("goal") or "").strip()
    if not goal or len(goal) < 3:
        clarifications.append("Specify an attack goal (e.g. goal=\"bypass refusals\").")

    # ── Aggressiveness ──────────────────────────────────────────────
    try:
        aggressiveness = int(slots.get("aggressiveness", 3))
    except (TypeError, ValueError):
        aggressiveness = 3
    aggressiveness = max(1, min(5, aggressiveness))

    # ── Engines ─────────────────────────────────────────────────────
    raw_engines = slots.get("engines") or []
    if not isinstance(raw_engines, list) or not raw_engines:
        engines = list(_DEFAULT_ENGINES)
    else:
        engines = [str(e).lower() for e in raw_engines if str(e).lower() in _ALLOWED_ENGINES]
        if not engines:
            engines = list(_DEFAULT_ENGINES)

    # ── Autonomy ────────────────────────────────────────────────────
    autonomy_raw = str(slots.get("autonomy_level") or "L3").upper()
    if autonomy_raw not in {"L1", "L2", "L3", "L4", "L5"}:
        autonomy_raw = "L3"

    # Aggressiveness 5 is admin-only; 1..4 require evaluator.
    requires_role = "admin" if aggressiveness >= 5 else "evaluator"

    return AttackPayload(
        target_model_id=target_id,
        target_model_name=target_name,
        goal=goal,
        aggressiveness=aggressiveness,
        engines=engines,
        autonomy_level=autonomy_raw,
        requires_role=requires_role,
        clarification="; ".join(clarifications) or None,
    )
