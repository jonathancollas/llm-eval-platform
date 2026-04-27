"""
SearchEngine — orchestrator.

Pipeline:
  classify_deterministic()
    ├─ confidence >= 0.85 → use as-is
    ├─ confidence <  0.85 and LLM backend available → classify_with_llm()
    └─ no LLM available → return unknown

  route by intent →
    navigate  → resolve route label
    ask       → try deterministic answer first, fall back to clarification
    launch    → build_launch_preview()
    attack    → build_attack_preview()
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from sqlmodel import Session

from eval_engine.search.ask_engine import answer_deterministic
from eval_engine.search.attack_builder import build_attack_preview
from eval_engine.search.campaign_builder import build_launch_preview
from eval_engine.search.classifier import classify_deterministic
from eval_engine.search.llm_classifier import (
    IntentClassifierUnavailable, classify_with_llm,
)
from eval_engine.search.schema import (
    AskPayload, AskSource, AttackPayload, IntentResponse, LaunchPayload,
    NavigatePayload, SearchIntent, ExecuteRequest, ExecuteResponse,
)
from eval_engine.search.typeahead import build_typeahead_response

logger = logging.getLogger(__name__)

# If deterministic classifier's confidence is at/above this, skip the LLM.
_DETERMINISTIC_THRESHOLD = 0.85
# Below this, auto-execute is disabled and the UI prompts the user to confirm.
_AUTO_EXECUTE_THRESHOLD = 0.80


class SearchEngine:
    """Stateless orchestrator. Create one per request or cache globally."""

    def __init__(self, session: Session):
        self.session = session

    # ── Typeahead ──────────────────────────────────────────────────

    def typeahead(self, query: str, limit_per_group: int = 5):
        return build_typeahead_response(self.session, query, limit_per_group)

    # ── Intent classification ──────────────────────────────────────

    async def classify(self, query: str) -> IntentResponse:
        t0 = time.time()
        det = classify_deterministic(query)
        if det.confidence >= _DETERMINISTIC_THRESHOLD:
            payload = await self._build_payload(det.intent, det.slots, det.route, det.route_label, query=query)
            return IntentResponse(
                query=query,
                intent=SearchIntent(det.intent) if det.intent != "unknown" else SearchIntent.UNKNOWN,
                confidence=det.confidence,
                payload=payload,
                can_auto_execute=det.confidence >= _AUTO_EXECUTE_THRESHOLD,
                latency_ms=int((time.time() - t0) * 1000),
            )

        # Deterministic was not confident enough: escalate to LLM.
        try:
            llm = await classify_with_llm(query)
            payload = await self._build_payload(llm.intent, llm.slots, query=query)
            intent_enum = SearchIntent(llm.intent) if llm.intent in {
                "navigate", "ask", "launch", "attack"
            } else SearchIntent.UNKNOWN
            return IntentResponse(
                query=query,
                intent=intent_enum,
                confidence=llm.confidence,
                payload=payload,
                can_auto_execute=llm.confidence >= _AUTO_EXECUTE_THRESHOLD,
                latency_ms=int((time.time() - t0) * 1000),
            )
        except IntentClassifierUnavailable:
            # Graceful degradation: treat as an ASK with a hint.
            logger.debug("LLM classifier unavailable, falling back to ASK-unknown.")
            payload = AskPayload(
                answer=(
                    "I'm not sure what you meant. Try: "
                    "'evaluate <model> on <benchmark>', "
                    "'red-team <model> goal=\"...\"', "
                    "or type a section name like 'leaderboard' or 'genome'."
                ),
                deterministic=True,
            )
            return IntentResponse(
                query=query,
                intent=SearchIntent.UNKNOWN,
                confidence=0.0,
                payload=payload,
                can_auto_execute=False,
                latency_ms=int((time.time() - t0) * 1000),
            )

    # ── Execute ────────────────────────────────────────────────────

    async def execute(self, req: ExecuteRequest) -> ExecuteResponse:
        intent_resp = await self.classify(req.query)
        submit_body = None
        submit_endpoint = None

        if isinstance(intent_resp.payload, LaunchPayload) and intent_resp.payload.preview:
            p = intent_resp.payload.preview
            submit_body = {
                "name": p.name,
                "description": p.description,
                "model_ids": p.model_ids,
                "benchmark_ids": p.benchmark_ids,
                "seed": 42,
                "max_samples": p.max_samples,
                "temperature": p.temperature,
                "run_context_json": p.run_context_json,
            }
            submit_endpoint = "/api/campaigns/"

        elif isinstance(intent_resp.payload, AttackPayload):
            a = intent_resp.payload
            if a.target_model_id and a.goal and not a.clarification:
                # Role gate — we only prepare the body; the router rejects if
                # role is insufficient.
                if req.role == "viewer" and a.requires_role in {"evaluator", "admin"}:
                    intent_resp.payload.clarification = (
                        f"This attack requires the '{a.requires_role}' role. "
                        f"Your current role is 'viewer'."
                    )
                else:
                    submit_body = {
                        "model_id": a.target_model_id,
                        "goal": a.goal,
                        "aggressiveness": a.aggressiveness,
                        "max_attacks": 20,
                    }
                    submit_endpoint = "/api/redbox/attack"

        return ExecuteResponse(
            intent_response=intent_resp,
            submit_body=submit_body,
            submit_endpoint=submit_endpoint,
        )

    # ── Internals ──────────────────────────────────────────────────

    async def _build_payload(
        self,
        intent: str,
        slots: dict,
        route: Optional[str] = None,
        route_label: str = "",
        query: str = "",
    ):
        if intent == "navigate":
            final_route = route or str(slots.get("route") or "/")
            label = route_label or final_route.strip("/") or "Home"
            return NavigatePayload(route=final_route, label=label)

        if intent == "ask":
            question = str(slots.get("question") or "")
            ans = answer_deterministic(self.session, question)
            if ans:
                return ans
            return AskPayload(
                answer="I don't have a deterministic answer for this question yet.",
                sources=[AskSource(
                    id="doc:methodology",
                    label="Methodology Center",
                    href="/methodology",
                )],
                deterministic=True,
            )

        if intent == "launch":
            return build_launch_preview(self.session, slots, query=query)

        if intent == "attack":
            return build_attack_preview(self.session, slots, query=query)

        # Unknown intent → AskPayload "I don't know"
        return AskPayload(
            answer="I couldn't interpret this query. Try typing a section name "
                   "or an action like 'evaluate' or 'red-team'.",
            deterministic=True,
        )
