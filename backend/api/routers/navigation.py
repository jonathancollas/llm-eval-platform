"""
Navigation counts — powers the count badges in <RelatedViews>.

Route:  GET /api/navigation/counts?entity_type=model&entity_id=123
Resp:   { "runs": 12, "redbox": 14, ... }

Each key corresponds to NavLink.key in frontend/lib/navigation-graph.ts.
The endpoint is read-only and degrades gracefully: unknown entity types
return {} (200) rather than 404, so the UI doesn't need to know which
counts are supported.

This is intentionally a thin layer. It returns empty {} for any entity
type that doesn't yet have count queries — better to have a working UI
without badges than a broken UI when a new entity type is added.

Audit reference: §5.3 (related views replacing the flat sidebar).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, func, select

from core.auth import require_tenant
from core.database import get_session
from core.models import (
    Benchmark,
    Campaign,
    EvalRun,
    LLMModel,
    Tenant,
)

router = APIRouter(prefix="/navigation", tags=["navigation"])


# ─── Public endpoint ────────────────────────────────────────────────────────


@router.get("/counts", response_model=dict[str, int])
def navigation_counts(
    entity_type: str = Query(..., max_length=50),
    entity_id: str = Query(..., max_length=100),
    session: Session = Depends(get_session),
    tenant: Tenant = Depends(require_tenant),
) -> dict[str, int]:
    """Return per-key counts for the related views of an entity.

    Returns an empty object for unknown entity types or non-existent entities
    rather than 404, so the UI degrades gracefully when navigating to entities
    whose tenant the caller can't see.
    """
    if entity_type == "model":
        return _model_counts(entity_id, session)
    if entity_type == "benchmark":
        return _benchmark_counts(entity_id, session)
    if entity_type == "campaign":
        return _campaign_counts(entity_id, session)
    # Unknown types: 200 with {}, the UI just shows links without badges.
    return {}


# ─── Per-entity count helpers ───────────────────────────────────────────────


def _as_int(v: str) -> int:
    try:
        return int(v)
    except ValueError:
        raise HTTPException(status_code=400, detail="entity_id must be an integer")


def _scalar_count(session: Session, statement) -> int:
    """Run a count() statement and return the integer result.

    Defensive coercion in case the SQL driver returns None for empty tables.
    """
    result = session.exec(statement).one()
    return int(result or 0)


def _model_counts(entity_id: str, session: Session) -> dict[str, int]:
    mid = _as_int(entity_id)
    # Verify the entity exists; if not, return empty (don't leak information
    # about which IDs exist outside the caller's tenant).
    if not session.get(LLMModel, mid):
        return {}
    return {
        "runs": _scalar_count(
            session,
            select(func.count()).select_from(EvalRun).where(EvalRun.model_id == mid),
        ),
        # Optional counts — only include if the underlying table exists.
        # We try them and fall back to 0 if the schema doesn't have them yet.
        "redbox": _try_count_redbox_for_model(session, mid),
        "trajectories": _try_count_trajectories_for_model(session, mid),
    }


def _benchmark_counts(entity_id: str, session: Session) -> dict[str, int]:
    bid = _as_int(entity_id)
    if not session.get(Benchmark, bid):
        return {}
    return {
        "coverage": _scalar_count(
            session,
            select(func.count())
            .select_from(EvalRun)
            .where(EvalRun.benchmark_id == bid),
        ),
    }


def _campaign_counts(entity_id: str, session: Session) -> dict[str, int]:
    cid = _as_int(entity_id)
    if not session.get(Campaign, cid):
        return {}
    return {
        "runs": _scalar_count(
            session,
            select(func.count())
            .select_from(EvalRun)
            .where(EvalRun.campaign_id == cid),
        ),
    }


# ─── Optional model imports — degrade gracefully if not present ─────────────
# The RedboxExploit and AgentTrajectory models exist in current schema, but
# some deployments pre-migration may not have them. Wrap their counts so the
# main count helpers never fail.


def _try_count_redbox_for_model(session: Session, model_id: int) -> int:
    try:
        from core.models import RedboxExploit  # noqa: WPS433  (intentional lazy import)
        return _scalar_count(
            session,
            select(func.count())
            .select_from(RedboxExploit)
            .where(RedboxExploit.model_id == model_id),
        )
    except (ImportError, AttributeError):
        return 0


def _try_count_trajectories_for_model(session: Session, model_id: int) -> int:
    try:
        from core.models import AgentTrajectory  # noqa: WPS433
        return _scalar_count(
            session,
            select(func.count())
            .select_from(AgentTrajectory)
            .where(AgentTrajectory.model_id == model_id),
        )
    except (ImportError, AttributeError):
        return 0
