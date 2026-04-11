"""
Events API (#45 — event-sourced pipeline)
=========================================
Query the event log and replay campaign state at any point in time.
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, desc

from core.database import get_session
from core.models import EvalEventRecord
from eval_engine.event_pipeline import get_replay_engine, EventType

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/campaign/{campaign_id}")
def get_campaign_events(
    campaign_id: int,
    event_type: Optional[str] = None,
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
    session: Session = Depends(get_session),
):
    """
    Stream the full event log for a campaign.

    Useful for:
    - Debugging evaluation runs step by step
    - Auditing safety-critical evaluations
    - Powering real-time observability dashboards
    """
    query = (
        select(EvalEventRecord)
        .where(EvalEventRecord.campaign_id == campaign_id)
        .order_by(EvalEventRecord.sequence)
        .offset(offset)
        .limit(limit)
    )
    if event_type:
        query = query.where(EvalEventRecord.event_type == event_type)

    records = session.exec(query).all()
    total = session.exec(
        select(EvalEventRecord).where(EvalEventRecord.campaign_id == campaign_id)
    ).all()

    return {
        "campaign_id": campaign_id,
        "total_events": len(total),
        "events": [
            {
                "event_id": r.event_id,
                "event_type": r.event_type,
                "sequence": r.sequence,
                "timestamp": r.timestamp.isoformat(),
                "run_id": r.run_id,
                "model_id": r.model_id,
                "benchmark_id": r.benchmark_id,
                "payload": json.loads(r.payload_json),
            }
            for r in records
        ],
    }


@router.get("/campaign/{campaign_id}/state")
async def get_campaign_state(
    campaign_id: int,
    at_sequence: Optional[int] = None,
):
    """
    Replay all events and return reconstructed campaign state.

    Pass at_sequence to reconstruct state at any historical checkpoint.
    Without it, returns current state (all events applied).

    This is the foundation of deterministic replay (#46).
    """
    engine = get_replay_engine()
    state = await engine.replay(campaign_id, up_to_sequence=at_sequence)
    return state.summary


@router.get("/campaign/{campaign_id}/diff")
async def get_campaign_diff(
    campaign_id: int,
    from_sequence: int = Query(..., description="Start sequence (inclusive)"),
    to_sequence: int = Query(..., description="End sequence (inclusive)"),
):
    """
    Show what changed between two points in the event log.

    Useful for understanding regressions or unexpected state transitions.
    Example: diff between before and after a sandbagging signal was emitted.
    """
    engine = get_replay_engine()
    diff = await engine.diff(campaign_id, from_sequence, to_sequence)
    return {
        "campaign_id": campaign_id,
        "from_sequence": from_sequence,
        "to_sequence": to_sequence,
        "changes": diff,
    }


@router.get("/campaign/{campaign_id}/timeline")
def get_campaign_timeline(
    campaign_id: int,
    session: Session = Depends(get_session),
):
    """
    Condensed timeline of key milestones for a campaign.
    Returns one entry per meaningful state transition (skips ITEM events).
    """
    milestone_types = {
        "campaign.started", "campaign.completed", "campaign.failed",
        "run.started", "run.completed", "run.failed",
        "genome.computed", "judge.completed", "sandbagging.signal",
        "injection.detected", "goal_drift.detected",
    }

    records = session.exec(
        select(EvalEventRecord)
        .where(EvalEventRecord.campaign_id == campaign_id)
        .where(EvalEventRecord.event_type.in_(milestone_types))
        .order_by(EvalEventRecord.sequence)
    ).all()

    return {
        "campaign_id": campaign_id,
        "milestones": [
            {
                "sequence": r.sequence,
                "event_type": r.event_type,
                "timestamp": r.timestamp.isoformat(),
                "run_id": r.run_id,
                "summary": _milestone_summary(r.event_type, json.loads(r.payload_json)),
            }
            for r in records
        ],
    }


@router.get("/types")
def list_event_types():
    """List all available event types with descriptions."""
    return {
        "event_types": [
            {"value": e.value, "name": e.name}
            for e in EventType
        ]
    }


def _milestone_summary(event_type: str, payload: dict) -> str:
    summaries = {
        "campaign.started": "Campaign started",
        "campaign.completed": "Campaign completed",
        "campaign.failed": f"Campaign failed: {payload.get('error', '')[:80]}",
        "run.started": f"Run started (model={payload.get('model_name', '?')}, bench={payload.get('benchmark_name', '?')})",
        "run.completed": f"Run completed — score={payload.get('score', '?')}",
        "run.failed": f"Run failed: {payload.get('error', '')[:80]}",
        "genome.computed": "Failure genome computed",
        "judge.completed": f"Judge evaluation completed ({payload.get('n_evaluated', 0)} items)",
        "sandbagging.signal": f"Sandbagging signal — risk={payload.get('risk_level', '?')}",
        "injection.detected": f"Injection detected — agent={payload.get('agent_name', '?')}",
        "goal_drift.detected": f"Goal drift detected at step {payload.get('step', '?')}",
    }
    return summaries.get(event_type, event_type)
