"""
Search router — the intent surface of Mercury Retrograde.

Three endpoints:

  GET  /api/search/typeahead?q=...    — suggestion list for the dropdown
  POST /api/search/intent             — classify a query, return IntentResponse
  POST /api/search/execute            — classify + build submit body for
                                         LAUNCH / ATTACK (ready to POST)

Security:
  * All endpoints respect the platform-wide API-key middleware.
  * /search/execute honours the user's role when building ATTACK bodies;
    a viewer cannot produce an executable attack body.
  * None of these endpoints mutate state. They are purely advisory.

Rate-limiting:
  * Typeahead is called on every keystroke (debounced 120ms client-side).
    The global rate limiter (120 rpm per IP by default) is sufficient.
  * Intent classification is potentially LLM-backed; the engine caches
    nothing but the underlying LLM providers have their own budgets.
"""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlmodel import Session

from core.auth import get_request_role
from core.database import get_session
from eval_engine.search.engine import SearchEngine
from eval_engine.search.schema import (
    ExecuteRequest, ExecuteResponse, IntentResponse, SearchIntent,
    TypeaheadResponse,
)

router = APIRouter(prefix="/search", tags=["search"])
logger = logging.getLogger(__name__)

MAX_QUERY_LEN = 400


class IntentRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=MAX_QUERY_LEN)


# ── Typeahead ──────────────────────────────────────────────────────────────

@router.get("/typeahead", response_model=TypeaheadResponse)
def typeahead(
    q: str = Query("", max_length=MAX_QUERY_LEN),
    limit: int = Query(5, ge=1, le=10),
    session: Session = Depends(get_session),
) -> TypeaheadResponse:
    engine = SearchEngine(session)
    return engine.typeahead(q, limit_per_group=limit)


# ── Intent classification ──────────────────────────────────────────────────

@router.post("/intent", response_model=IntentResponse)
async def intent(
    body: IntentRequest,
    session: Session = Depends(get_session),
) -> IntentResponse:
    engine = SearchEngine(session)
    return await engine.classify(body.query)


# ── Execute ────────────────────────────────────────────────────────────────

class ExecuteBody(BaseModel):
    query: str = Field(..., min_length=1, max_length=MAX_QUERY_LEN)
    forced_intent: Literal["navigate", "ask", "launch", "attack"] | None = None


@router.post("/execute", response_model=ExecuteResponse)
async def execute(
    body: ExecuteBody,
    request: Request,
    session: Session = Depends(get_session),
) -> ExecuteResponse:
    role_str = get_request_role(request)
    # Normalise to the ExecuteRequest role union; default to 'viewer' for
    # anything we don't recognise.
    role: Literal["viewer", "evaluator", "admin"] = "viewer"
    if role_str in ("viewer", "evaluator", "admin"):
        role = role_str  # type: ignore[assignment]
    req = ExecuteRequest(
        query=body.query,
        forced_intent=SearchIntent(body.forced_intent) if body.forced_intent else None,
        role=role,
    )
    engine = SearchEngine(session)
    return await engine.execute(req)
