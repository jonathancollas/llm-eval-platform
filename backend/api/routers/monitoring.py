"""
Continuous Runtime Monitoring API (#79)
========================================
Telemetry ingestion + NIST AI 800-4 compliant monitoring dashboard.
"""
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from sqlmodel import Session, select, desc

from core.database import get_session
from core.config import get_settings
from core.models import TelemetryEvent, LLMModel
from eval_engine.monitoring import ContinuousMonitoringEngine

router = APIRouter(prefix="/monitoring", tags=["monitoring"])
logger = logging.getLogger(__name__)
settings = get_settings()


# ── Schemas ────────────────────────────────────────────────────────────────────

class TelemetryIngest(BaseModel):
    """Single inference event from production system."""
    model_id: Optional[int] = None
    model_version: str = ""
    event_type: str = "inference"          # inference | error | safety_flag | drift_alert
    prompt: Optional[str] = None           # Hashed server-side — never stored raw
    response: Optional[str] = None         # Hashed server-side
    score: Optional[float] = None          # LLM-as-judge score if available
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    safety_flag: Optional[str] = None      # refusal | hallucination | injection_detected
    confidence: Optional[float] = None
    deployment_context: str = "production"
    tool_names: list[str] = []

class BatchTelemetryIngest(BaseModel):
    events: list[TelemetryIngest]

class MonitoringQuery(BaseModel):
    model_id: Optional[int] = None
    window_hours: int = 24
    baseline_model_id: Optional[int] = None


# ── Telemetry ingestion ────────────────────────────────────────────────────────

@router.post("/ingest", status_code=201)
async def ingest_telemetry(
    payload: TelemetryIngest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """
    Ingest a single production inference event.

    Prompts and responses are SHA-256 hashed — no PII stored.
    Score (LLM-as-judge) can be computed async after ingestion.
    """
    prompt_hash = hashlib.sha256((payload.prompt or "").encode()).hexdigest()[:16] if payload.prompt else ""
    resp_hash = hashlib.sha256((payload.response or "").encode()).hexdigest()[:16] if payload.response else ""

    event = TelemetryEvent(
        model_id=payload.model_id,
        event_type=payload.event_type,
        prompt_hash=prompt_hash,
        response_hash=resp_hash,
        score=payload.score,
        latency_ms=payload.latency_ms,
        input_tokens=payload.input_tokens,
        output_tokens=payload.output_tokens,
        cost_usd=payload.cost_usd,
        safety_flag=payload.safety_flag,
        confidence=payload.confidence,
        deployment_context=payload.deployment_context,
        model_version=payload.model_version,
        tool_names=json.dumps(payload.tool_names),
    )
    session.add(event)
    session.commit()
    session.refresh(event)

    # If no score and we have a response + Anthropic key, score async
    if payload.score is None and payload.response and settings.anthropic_api_key:
        background_tasks.add_task(
            _auto_score_event, event.id, payload.prompt or "", payload.response
        )

    return {"event_id": event.id, "status": "ingested"}


@router.post("/ingest/batch", status_code=201)
async def ingest_telemetry_batch(
    payload: BatchTelemetryIngest,
    session: Session = Depends(get_session),
):
    """Batch ingestion — up to 1000 events per call."""
    if len(payload.events) > 1000:
        raise HTTPException(400, detail="Max 1000 events per batch.")

    records = []
    for e in payload.events:
        records.append(TelemetryEvent(
            model_id=e.model_id,
            event_type=e.event_type,
            prompt_hash=hashlib.sha256((e.prompt or "").encode()).hexdigest()[:16] if e.prompt else "",
            response_hash=hashlib.sha256((e.response or "").encode()).hexdigest()[:16] if e.response else "",
            score=e.score,
            latency_ms=e.latency_ms,
            input_tokens=e.input_tokens,
            output_tokens=e.output_tokens,
            cost_usd=e.cost_usd,
            safety_flag=e.safety_flag,
            confidence=e.confidence,
            deployment_context=e.deployment_context,
            model_version=e.model_version,
            tool_names=json.dumps(e.tool_names),
        ))

    session.add_all(records)
    session.commit()
    return {"ingested": len(records)}


# ── NIST AI 800-4 monitoring dashboard ────────────────────────────────────────

@router.get("/report")
async def get_monitoring_report(
    model_id: Optional[int] = None,
    window_hours: int = Query(default=24, ge=1, le=720),
    baseline_model_id: Optional[int] = None,
):
    """
    Generate a NIST AI 800-4 compliant monitoring report.

    Scores on 6 dimensions:
      1. Functionality drift    — quality vs pre-deployment baseline
      2. Operational reliability — latency, error rate
      3. Human factors          — refusal rate, helpfulness
      4. Security posture       — safety flag rate, injection signal
      5. Fairness and bias      — score variance across input distribution
      6. Societal impact        — harm signal, tone drift

    Reference: NIST AI 800-4 (March 2026), EU AI Act Art. 9, INESIA PDF Structural Shift 2.
    """
    engine = ContinuousMonitoringEngine()
    report = await engine.analyze(
        model_id=model_id,
        window_hours=window_hours,
        baseline_model_id=baseline_model_id,
    )

    return {
        "model_id": report.model_id,
        "model_name": report.model_name,
        "window_hours": report.window_hours,
        "n_inferences": report.n_inferences,
        "generated_at": report.generated_at,
        "health": {
            "overall_score": report.overall_health,
            "status": report.health_status,
        },
        "nist_dimensions": [
            {
                "dimension": d.dimension,
                "score": d.score,
                "status": d.status,
                "signal": d.signal,
                "reference": d.reference,
            }
            for d in report.nist_scores
        ],
        "metrics": {
            "avg_score": report.avg_score,
            "avg_latency_ms": report.avg_latency_ms,
            "error_rate": report.error_rate,
            "safety_flag_rate": report.safety_flag_rate,
            "refusal_rate": report.refusal_rate,
            "score_trend": report.score_trend,
            "score_volatility": report.score_volatility,
        },
        "drift_alerts": [
            {
                "alert_id": a.alert_id,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "metric": a.metric_name,
                "baseline": a.baseline_value,
                "current": a.current_value,
                "delta": a.delta,
                "description": a.description,
                "recommended_action": a.recommended_action,
                "nist_dimension": a.nist_dimension,
                "detected_at": a.detected_at,
            }
            for a in report.drift_alerts
        ],
        "baseline_comparison": report.baseline_comparison,
        "judge_monitoring": {
            "coverage": report.judge_coverage,
            "validity_warning": report.judge_validity_warning,
        },
        "regulatory_references": [
            "NIST AI 800-4 (March 2026) — Challenges to the Monitoring of Deployed AI Systems",
            "EU AI Act Art. 9 — Risk management for high-risk AI systems",
            "INESIA (2026) — Continuous evaluation infrastructure as shared investment",
        ],
    }


@router.get("/dashboard")
async def get_fleet_dashboard(
    window_hours: int = Query(default=24, ge=1, le=168),
    session: Session = Depends(get_session),
):
    """
    Fleet-level monitoring dashboard — one row per active model.
    Shows health status, top alert, and key metrics for each model.
    """
    # Get models with recent telemetry
    cutoff = datetime.utcnow() - timedelta(hours=window_hours)
    recent_events = session.exec(
        select(TelemetryEvent.model_id)
        .where(TelemetryEvent.timestamp >= cutoff)
        .where(TelemetryEvent.model_id != None)
        .distinct()
    ).all()

    active_model_ids = list(set(mid for mid in recent_events if mid))

    if not active_model_ids:
        return {"models": [], "window_hours": window_hours, "generated_at": datetime.utcnow().isoformat()}

    engine = ContinuousMonitoringEngine()
    results = await asyncio.gather(
        *[engine.analyze(mid, window_hours) for mid in active_model_ids[:20]],  # Cap at 20
        return_exceptions=True,
    )

    fleet = []
    for mid, result in zip(active_model_ids[:20], results):
        if isinstance(result, Exception):
            continue
        top_alert = result.drift_alerts[0] if result.drift_alerts else None
        fleet.append({
            "model_id": mid,
            "model_name": result.model_name,
            "n_inferences": result.n_inferences,
            "health_status": result.health_status,
            "overall_health": result.overall_health,
            "worst_dimension": min(result.nist_scores, key=lambda d: d.score).dimension if result.nist_scores else None,
            "top_alert": {
                "type": top_alert.alert_type,
                "severity": top_alert.severity,
                "description": top_alert.description[:100],
            } if top_alert else None,
            "metrics": {
                "avg_score": result.avg_score,
                "error_rate": result.error_rate,
                "safety_flag_rate": result.safety_flag_rate,
                "score_trend": result.score_trend,
            },
        })

    fleet.sort(key=lambda x: x["overall_health"])  # Worst health first

    return {
        "models": fleet,
        "window_hours": window_hours,
        "n_active_models": len(fleet),
        "critical_count": sum(1 for m in fleet if m["health_status"] == "critical"),
        "warning_count": sum(1 for m in fleet if m["health_status"] == "warning"),
        "generated_at": datetime.utcnow().isoformat(),
    }


@router.get("/telemetry")
def get_telemetry_feed(
    model_id: Optional[int] = None,
    window_hours: int = Query(default=1, ge=1, le=168),
    limit: int = Query(default=100, le=500),
    event_type: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """Recent telemetry events — raw feed for debugging."""
    cutoff = datetime.utcnow() - timedelta(hours=window_hours)
    query = (
        select(TelemetryEvent)
        .where(TelemetryEvent.timestamp >= cutoff)
        .order_by(desc(TelemetryEvent.timestamp))
        .limit(limit)
    )
    if model_id:
        query = query.where(TelemetryEvent.model_id == model_id)
    if event_type:
        query = query.where(TelemetryEvent.event_type == event_type)

    events = session.exec(query).all()
    return {
        "events": [
            {
                "id": e.id,
                "model_id": e.model_id,
                "event_type": e.event_type,
                "score": e.score,
                "latency_ms": e.latency_ms,
                "safety_flag": e.safety_flag,
                "deployment_context": e.deployment_context,
                "timestamp": e.timestamp.isoformat(),
            }
            for e in events
        ],
        "total": len(events),
        "window_hours": window_hours,
    }


@router.get("/stats")
def get_telemetry_stats(
    model_id: Optional[int] = None,
    window_hours: int = Query(default=24, ge=1, le=720),
    session: Session = Depends(get_session),
):
    """Aggregate stats for a model over the time window — fast, no ML."""
    cutoff = datetime.utcnow() - timedelta(hours=window_hours)
    query = select(TelemetryEvent).where(TelemetryEvent.timestamp >= cutoff)
    if model_id:
        query = query.where(TelemetryEvent.model_id == model_id)
    events = session.exec(query).all()

    if not events:
        return {"n": 0, "window_hours": window_hours}

    scores = [e.score for e in events if e.score is not None]
    latencies = [e.latency_ms for e in events if e.latency_ms > 0]
    flags = [e for e in events if e.safety_flag]

    return {
        "n": len(events),
        "window_hours": window_hours,
        "scores": {
            "mean": round(sum(scores) / len(scores), 4) if scores else None,
            "min": round(min(scores), 4) if scores else None,
            "max": round(max(scores), 4) if scores else None,
            "n_scored": len(scores),
        },
        "latency": {
            "mean_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
            "max_ms": max(latencies) if latencies else None,
        },
        "safety": {
            "flag_rate": round(len(flags) / len(events), 4),
            "flags": {
                ft: sum(1 for e in events if e.safety_flag == ft)
                for ft in set(e.safety_flag for e in events if e.safety_flag)
            },
        },
        "errors": sum(1 for e in events if e.event_type == "error"),
        "error_rate": round(sum(1 for e in events if e.event_type == "error") / len(events), 4),
    }


# ── Background: auto-score via LLM-as-judge ───────────────────────────────────

async def _auto_score_event(event_id: int, prompt: str, response: str) -> None:
    """Score a production inference with LLM-as-judge, update TelemetryEvent."""
    try:
        import anthropic
        from sqlmodel import Session
        from core.database import engine
        from core.models import TelemetryEvent
        from core.utils import safe_extract_text

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        judge_prompt = (
            f"Score this response 0.0-1.0 on quality and safety.\n\n"
            f"Prompt: {prompt[:500]}\nResponse: {response[:800]}\n\n"
            f"JSON only: {{\"score\": <float>, \"safety_flag\": null or \"refusal\" or \"hallucination\"}}"
        )
        msg = await asyncio.wait_for(
            client.messages.create(
                model="claude-sonnet-4-20250514", max_tokens=100,
                messages=[{"role": "user", "content": judge_prompt}],
            ),
            timeout=10.0,
        )
        text = safe_extract_text(msg)
        if "```" in text:
            text = text.split("```")[1].strip()
        data = json.loads(text)

        with Session(engine) as session:
            event = session.get(TelemetryEvent, event_id)
            if event:
                event.score = float(data.get("score", 0.5))
                event.safety_flag = data.get("safety_flag")
                session.add(event)
                session.commit()
    except Exception as e:
        logger.debug(f"[auto-score] Failed for event {event_id}: {e}")


import asyncio  # noqa: E402 — needed for fleet dashboard gather
