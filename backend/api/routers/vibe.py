"""
Vibe Check — quick, parallel, multi-model prompt evaluation.

Sends a free-form prompt to 1–3 selected models simultaneously and returns
each response along with latency, token usage, and cost metadata.
No campaign is created; the interaction is entirely ephemeral.
"""
from __future__ import annotations

import asyncio
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from core.database import get_session
from core.models import LLMModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vibe", tags=["vibe"])

MAX_MODELS = 3
MAX_PROMPT_LENGTH = 4000
DEFAULT_MAX_TOKENS = 1024


# ── Schemas ───────────────────────────────────────────────────────────────────

class VibeRequest(BaseModel):
    model_ids: List[int] = Field(..., min_length=1, max_length=MAX_MODELS)
    prompt: str = Field(..., min_length=1, max_length=MAX_PROMPT_LENGTH)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=DEFAULT_MAX_TOKENS, ge=1, le=4096)


class VibeModelResult(BaseModel):
    model_id: int
    model_name: str
    text: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    error: str | None = None


class VibeResponse(BaseModel):
    results: List[VibeModelResult]


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/prompt", response_model=VibeResponse)
async def vibe_prompt(
    body: VibeRequest,
    session: Session = Depends(get_session),
) -> VibeResponse:
    """
    Send *body.prompt* to each model in *body.model_ids* in parallel.
    Returns responses as soon as all tasks complete (or fail gracefully).
    """
    if not body.model_ids:
        raise HTTPException(status_code=422, detail="At least one model_id is required.")
    if len(body.model_ids) > MAX_MODELS:
        raise HTTPException(status_code=422, detail=f"Maximum {MAX_MODELS} models per vibe check.")

    # Fetch all requested models in one query
    models = session.exec(
        select(LLMModel).where(LLMModel.id.in_(body.model_ids))  # type: ignore[attr-defined]
    ).all()

    found_ids = {m.id for m in models}
    missing = [mid for mid in body.model_ids if mid not in found_ids]
    if missing:
        raise HTTPException(status_code=404, detail=f"Model(s) not found: {missing}")

    # Run all completions in parallel
    async def _call(model: LLMModel) -> VibeModelResult:
        from eval_engine.litellm_client import complete
        try:
            result = await complete(
                model=model,
                prompt=body.prompt,
                temperature=body.temperature,
                max_tokens=body.max_tokens,
            )
            return VibeModelResult(
                model_id=model.id,
                model_name=model.name,
                text=result.text,
                latency_ms=result.latency_ms,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=result.cost_usd,
            )
        except Exception as exc:
            logger.warning("Vibe check call failed for model %s (%s): %s", model.id, model.name, exc)
            return VibeModelResult(
                model_id=model.id,
                model_name=model.name,
                text="",
                latency_ms=0,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                error=str(exc)[:300],
            )

    tasks = [_call(m) for m in models]
    results: list[VibeModelResult] = await asyncio.gather(*tasks)

    # Preserve the order requested by the caller
    order = {mid: i for i, mid in enumerate(body.model_ids)}
    results.sort(key=lambda r: order.get(r.model_id, 999))

    return VibeResponse(results=results)
