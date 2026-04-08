"""
Research OS — Workspace, Experiment Manifest, Safety Incident Exchange.
The scientific infrastructure layer of Mercury Retrograde.
"""
import json
import hashlib
import logging
import platform
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from core.database import get_session
from core.config import get_settings
from core.models import (
    Workspace, ExperimentManifest, SafetyIncident, TelemetryEvent,
    Campaign, EvalRun, EvalResult, LLMModel, Benchmark, JobStatus,
)

router = APIRouter(prefix="/research", tags=["research"])
logger = logging.getLogger(__name__)
settings = get_settings()


# ── Workspace CRUD ─────────────────────────────────────────────────────────────

class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    description: str = Field(default="")
    hypothesis: str = Field(default="")
    protocol: str = Field(default="")
    risk_domain: str = Field(default="")
    visibility: str = Field(default="private")
    tags: list[str] = Field(default=[])

class WorkspaceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    hypothesis: Optional[str] = None
    protocol: Optional[str] = None
    status: Optional[str] = None
    benchmark_ids: Optional[list[int]] = None
    campaign_ids: Optional[list[int]] = None
    model_ids: Optional[list[int]] = None
    tags: Optional[list[str]] = None


@router.post("/workspaces")
def create_workspace(payload: WorkspaceCreate, session: Session = Depends(get_session)):
    slug = payload.name.lower().replace(" ", "-")[:50]
    slug = "".join(c for c in slug if c.isalnum() or c == "-")

    existing = session.exec(select(Workspace).where(Workspace.slug == slug)).first()
    if existing:
        slug = f"{slug}-{int(datetime.utcnow().timestamp())}"

    ws = Workspace(
        name=payload.name,
        slug=slug,
        description=payload.description,
        hypothesis=payload.hypothesis,
        protocol=payload.protocol,
        risk_domain=payload.risk_domain,
        visibility=payload.visibility,
        tags=json.dumps(payload.tags),
    )
    session.add(ws)
    session.commit()
    session.refresh(ws)
    return {"id": ws.id, "name": ws.name, "slug": ws.slug, "status": ws.status}


@router.get("/workspaces")
def list_workspaces(visibility: Optional[str] = None, session: Session = Depends(get_session)):
    query = select(Workspace)
    if visibility:
        query = query.where(Workspace.visibility == visibility)
    workspaces = session.exec(query.order_by(Workspace.updated_at.desc())).all()
    return {"workspaces": [{
        "id": w.id, "name": w.name, "slug": w.slug,
        "description": w.description[:200], "status": w.status,
        "risk_domain": w.risk_domain, "visibility": w.visibility,
        "fork_count": w.fork_count, "created_at": w.created_at.isoformat(),
    } for w in workspaces]}


@router.get("/workspaces/{workspace_id}")
def get_workspace(workspace_id: int, session: Session = Depends(get_session)):
    ws = session.get(Workspace, workspace_id)
    if not ws:
        raise HTTPException(404, detail="Workspace not found.")

    # Gather linked entities
    campaign_ids = json.loads(ws.campaign_ids) if ws.campaign_ids else []
    manifests = session.exec(
        select(ExperimentManifest).where(ExperimentManifest.workspace_id == workspace_id)
    ).all()

    return {
        "id": ws.id, "name": ws.name, "slug": ws.slug,
        "description": ws.description, "hypothesis": ws.hypothesis,
        "protocol": ws.protocol, "risk_domain": ws.risk_domain,
        "status": ws.status, "visibility": ws.visibility,
        "benchmark_ids": json.loads(ws.benchmark_ids),
        "campaign_ids": campaign_ids,
        "model_ids": json.loads(ws.model_ids),
        "manifests": [{"id": m.id, "campaign_id": m.campaign_id, "hash": m.experiment_hash[:12]} for m in manifests],
        "fork_count": ws.fork_count,
        "forked_from_id": ws.forked_from_id,
        "doi": ws.doi, "paper_url": ws.paper_url, "citation": ws.citation,
        "tags": json.loads(ws.tags),
        "created_at": ws.created_at.isoformat(),
        "updated_at": ws.updated_at.isoformat(),
    }


@router.patch("/workspaces/{workspace_id}")
def update_workspace(workspace_id: int, payload: WorkspaceUpdate, session: Session = Depends(get_session)):
    ws = session.get(Workspace, workspace_id)
    if not ws:
        raise HTTPException(404, detail="Workspace not found.")

    for field, value in payload.dict(exclude_unset=True).items():
        if field in ("benchmark_ids", "campaign_ids", "model_ids", "tags"):
            setattr(ws, field, json.dumps(value))
        else:
            setattr(ws, field, value)
    ws.updated_at = datetime.utcnow()
    session.add(ws)
    session.commit()
    return {"updated": True}


@router.post("/workspaces/{workspace_id}/fork")
def fork_workspace(workspace_id: int, new_name: str = "Fork", session: Session = Depends(get_session)):
    parent = session.get(Workspace, workspace_id)
    if not parent:
        raise HTTPException(404, detail="Workspace not found.")

    slug = f"{parent.slug}-fork-{int(datetime.utcnow().timestamp())}"
    fork = Workspace(
        name=f"{new_name} (fork of {parent.name})",
        slug=slug,
        description=parent.description,
        hypothesis=parent.hypothesis,
        protocol=parent.protocol,
        risk_domain=parent.risk_domain,
        benchmark_ids=parent.benchmark_ids,
        model_ids=parent.model_ids,
        forked_from_id=parent.id,
        tags=parent.tags,
    )
    session.add(fork)
    parent.fork_count += 1
    session.add(parent)
    session.commit()
    session.refresh(fork)
    return {"id": fork.id, "slug": fork.slug, "forked_from": parent.id}


# ── Experiment Manifest ────────────────────────────────────────────────────────

@router.post("/manifests/generate/{campaign_id}")
def generate_manifest(campaign_id: int, workspace_id: Optional[int] = None, session: Session = Depends(get_session)):
    """Auto-generate a reproducibility manifest from a completed campaign."""
    campaign = session.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(404, detail="Campaign not found.")

    runs = session.exec(select(EvalRun).where(EvalRun.campaign_id == campaign_id)).all()

    # Build config snapshots
    model_configs = []
    for mid in set(r.model_id for r in runs):
        m = session.get(LLMModel, mid)
        if m:
            model_configs.append({"model_id": m.id, "name": m.name, "provider": m.provider, "model_id_str": m.model_id})

    bench_configs = []
    for bid in set(r.benchmark_id for r in runs):
        b = session.get(Benchmark, bid)
        if b:
            bench_configs.append({"bench_id": b.id, "name": b.name, "metric": b.metric,
                                  "dataset_path": b.dataset_path, "eval_dimension": getattr(b, "eval_dimension", "capability")})

    completed = [r for r in runs if r.status == JobStatus.COMPLETED]
    total_items = sum(r.num_items for r in completed)
    scores = [r.score for r in completed if r.score is not None]
    cap_scores = [r.capability_score for r in completed if getattr(r, "capability_score", None) is not None]
    prop_scores = [r.propensity_score for r in completed if getattr(r, "propensity_score", None) is not None]

    # Build hash
    config_str = json.dumps({
        "models": sorted([m["model_id_str"] for m in model_configs]),
        "benchmarks": sorted([b["name"] for b in bench_configs]),
        "seed": campaign.seed, "temperature": campaign.temperature,
    }, sort_keys=True)
    experiment_hash = hashlib.sha256(config_str.encode()).hexdigest()

    manifest = ExperimentManifest(
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        experiment_hash=experiment_hash,
        model_configs_json=json.dumps(model_configs),
        benchmark_configs_json=json.dumps(bench_configs),
        seed=campaign.seed,
        temperature=campaign.temperature,
        platform_version=settings.app_version,
        python_version=platform.python_version(),
        total_runs=len(runs),
        total_items=total_items,
        avg_score=round(sum(scores) / len(scores), 4) if scores else None,
        avg_capability_score=round(sum(cap_scores) / len(cap_scores), 4) if cap_scores else None,
        avg_propensity_score=round(sum(prop_scores) / len(prop_scores), 4) if prop_scores else None,
    )
    session.add(manifest)
    session.commit()
    session.refresh(manifest)

    return {
        "manifest_id": manifest.id,
        "experiment_hash": experiment_hash[:16],
        "total_runs": len(runs),
        "total_items": total_items,
        "models": len(model_configs),
        "benchmarks": len(bench_configs),
    }


@router.get("/manifests/{manifest_id}")
def get_manifest(manifest_id: int, session: Session = Depends(get_session)):
    m = session.get(ExperimentManifest, manifest_id)
    if not m:
        raise HTTPException(404, detail="Manifest not found.")
    return {
        "id": m.id, "workspace_id": m.workspace_id, "campaign_id": m.campaign_id,
        "experiment_hash": m.experiment_hash,
        "models": json.loads(m.model_configs_json),
        "benchmarks": json.loads(m.benchmark_configs_json),
        "seed": m.seed, "temperature": m.temperature,
        "platform_version": m.platform_version, "python_version": m.python_version,
        "total_runs": m.total_runs, "total_items": m.total_items,
        "avg_score": m.avg_score, "avg_capability_score": m.avg_capability_score,
        "avg_propensity_score": m.avg_propensity_score,
        "contamination_score": m.contamination_score,
        "judge_agreement_kappa": m.judge_agreement_kappa,
        "created_at": m.created_at.isoformat(),
    }


# ── Safety Incident Exchange (SIX) ────────────────────────────────────────────

class IncidentCreate(BaseModel):
    title: str
    category: str
    severity: str = "medium"
    description: str = ""
    model_id: Optional[int] = None
    trajectory_id: Optional[int] = None
    exploit_id: Optional[int] = None
    reproducibility: float = 0.0
    affected_models: list[str] = []
    mitigation: str = ""
    atlas_technique: Optional[str] = None
    tags: list[str] = []


@router.post("/incidents")
def create_incident(payload: IncidentCreate, session: Session = Depends(get_session)):
    # Generate incident ID: MRX-YYYY-NNN
    year = datetime.utcnow().year
    existing = session.exec(
        select(SafetyIncident).where(SafetyIncident.incident_id.like(f"MRX-{year}-%"))
    ).all()
    seq = len(existing) + 1
    incident_id = f"MRX-{year}-{seq:03d}"

    incident = SafetyIncident(
        incident_id=incident_id,
        title=payload.title,
        category=payload.category,
        severity=payload.severity,
        description=payload.description,
        model_id=payload.model_id,
        trajectory_id=payload.trajectory_id,
        exploit_id=payload.exploit_id,
        reproducibility=payload.reproducibility,
        affected_models=json.dumps(payload.affected_models),
        mitigation=payload.mitigation,
        atlas_technique=payload.atlas_technique,
        tags=json.dumps(payload.tags),
    )
    session.add(incident)
    session.commit()
    session.refresh(incident)
    return {"incident_id": incident.incident_id, "id": incident.id, "severity": incident.severity}


@router.get("/incidents")
def list_incidents(
    category: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    session: Session = Depends(get_session),
):
    query = select(SafetyIncident)
    if category:
        query = query.where(SafetyIncident.category == category)
    if severity:
        query = query.where(SafetyIncident.severity == severity)
    if status:
        query = query.where(SafetyIncident.status == status)

    incidents = session.exec(query.order_by(SafetyIncident.created_at.desc()).limit(limit)).all()
    return {"incidents": [{
        "incident_id": i.incident_id, "title": i.title,
        "category": i.category, "severity": i.severity,
        "status": i.status, "reproducibility": i.reproducibility,
        "affected_models": json.loads(i.affected_models),
        "atlas_technique": i.atlas_technique,
        "created_at": i.created_at.isoformat(),
    } for i in incidents], "total": len(incidents)}


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: str, session: Session = Depends(get_session)):
    incident = session.exec(
        select(SafetyIncident).where(SafetyIncident.incident_id == incident_id)
    ).first()
    if not incident:
        raise HTTPException(404, detail="Incident not found.")
    return {
        "incident_id": incident.incident_id, "title": incident.title,
        "category": incident.category, "severity": incident.severity,
        "description": incident.description, "status": incident.status,
        "model_id": incident.model_id,
        "reproducibility": incident.reproducibility,
        "affected_models": json.loads(incident.affected_models),
        "mitigation": incident.mitigation, "mitigation_status": incident.mitigation_status,
        "atlas_technique": incident.atlas_technique, "cve_id": incident.cve_id,
        "trace_json": json.loads(incident.trace_json) if incident.trace_json != "{}" else None,
        "tags": json.loads(incident.tags),
        "created_at": incident.created_at.isoformat(),
    }


# ── Telemetry Ingestion ────────────────────────────────────────────────────────

class TelemetryBatch(BaseModel):
    events: list[dict]


@router.post("/telemetry/ingest")
def ingest_telemetry(payload: TelemetryBatch, session: Session = Depends(get_session)):
    """Ingest runtime telemetry events for continuous monitoring."""
    created = 0
    for evt in payload.events[:1000]:  # Max 1000 per batch
        te = TelemetryEvent(
            model_id=evt.get("model_id"),
            event_type=evt.get("event_type", "inference"),
            prompt_hash=evt.get("prompt_hash", ""),
            response_hash=evt.get("response_hash", ""),
            score=evt.get("score"),
            latency_ms=evt.get("latency_ms", 0),
            input_tokens=evt.get("input_tokens", 0),
            output_tokens=evt.get("output_tokens", 0),
            cost_usd=evt.get("cost_usd", 0.0),
            safety_flag=evt.get("safety_flag"),
            confidence=evt.get("confidence"),
            deployment_context=evt.get("deployment_context", ""),
            model_version=evt.get("model_version", ""),
            tool_names=json.dumps(evt.get("tool_names", [])),
        )
        session.add(te)
        created += 1

    session.commit()
    return {"ingested": created}


@router.get("/telemetry/dashboard")
def telemetry_dashboard(
    model_id: Optional[int] = None,
    hours: int = 24,
    session: Session = Depends(get_session),
):
    """Drift detection dashboard — aggregated telemetry signals."""
    from datetime import timedelta

    cutoff = datetime.utcnow() - timedelta(hours=hours)
    query = select(TelemetryEvent).where(TelemetryEvent.timestamp >= cutoff)
    if model_id:
        query = query.where(TelemetryEvent.model_id == model_id)

    events = session.exec(query).all()
    if not events:
        return {"period_hours": hours, "total_events": 0, "drift_signals": []}

    # Aggregate metrics
    total = len(events)
    avg_latency = sum(e.latency_ms for e in events) / total
    safety_flags = [e for e in events if e.safety_flag]
    errors = [e for e in events if e.event_type == "error"]
    scores = [e.score for e in events if e.score is not None]

    # Drift signals
    drift_signals = []
    if len(safety_flags) / total > 0.05:
        drift_signals.append({"type": "safety_drift", "severity": "high",
                              "detail": f"{len(safety_flags)}/{total} events flagged ({len(safety_flags)/total:.1%})"})
    if len(errors) / total > 0.10:
        drift_signals.append({"type": "error_rate", "severity": "high",
                              "detail": f"Error rate: {len(errors)/total:.1%}"})
    if avg_latency > 10000:
        drift_signals.append({"type": "latency_drift", "severity": "medium",
                              "detail": f"Avg latency: {avg_latency:.0f}ms"})

    return {
        "period_hours": hours,
        "total_events": total,
        "avg_latency_ms": round(avg_latency),
        "safety_flag_rate": round(len(safety_flags) / total, 3),
        "error_rate": round(len(errors) / total, 3),
        "avg_score": round(sum(scores) / len(scores), 3) if scores else None,
        "drift_signals": drift_signals,
        "safety_flags_by_type": _count_by(safety_flags, "safety_flag"),
    }


def _count_by(events: list, field: str) -> dict:
    counts = {}
    for e in events:
        val = getattr(e, field, "unknown") or "unknown"
        counts[val] = counts.get(val, 0) + 1
    return counts
