"""
Research OS — Workspace, Experiment Manifest, Safety Incident Exchange.
The scientific infrastructure layer of Mercury Retrograde.
"""
import json
import hashlib
import logging
import platform
from datetime import datetime, UTC
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from core.database import get_session
from core.config import get_settings
from core.models import (
    Workspace, ExperimentManifest, SafetyIncident, TelemetryEvent,
    Campaign, EvalRun, LLMModel, Benchmark, JobStatus,
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
        slug = f"{slug}-{int(datetime.now(UTC).timestamp())}"

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
    ws.updated_at = datetime.now(UTC)
    session.add(ws)
    session.commit()
    return {"updated": True}


@router.post("/workspaces/{workspace_id}/fork")
def fork_workspace(workspace_id: int, new_name: str = "Fork", session: Session = Depends(get_session)):
    parent = session.get(Workspace, workspace_id)
    if not parent:
        raise HTTPException(404, detail="Workspace not found.")

    slug = f"{parent.slug}-fork-{int(datetime.now(UTC).timestamp())}"
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

    # Build config snapshots — fetch all models and benchmarks in one query each
    model_ids = list(set(r.model_id for r in runs))
    benchmark_ids = list(set(r.benchmark_id for r in runs))

    models = session.exec(select(LLMModel).where(LLMModel.id.in_(model_ids))).all()
    benchmarks = session.exec(select(Benchmark).where(Benchmark.id.in_(benchmark_ids))).all()

    model_configs = [
        {"model_id": m.id, "name": m.name, "provider": m.provider, "model_id_str": m.model_id}
        for m in models
    ]
    bench_configs = [
        {"bench_id": b.id, "name": b.name, "metric": b.metric,
         "dataset_path": b.dataset_path, "eval_dimension": getattr(b, "eval_dimension", "capability")}
        for b in benchmarks
    ]

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
    year = datetime.now(UTC).year
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
    from datetime import timedelta, UTC

    cutoff = datetime.now(UTC) - timedelta(hours=hours)
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


# ── #109 Benchmark fork & citation lineage ────────────────────────────────────

@router.get("/benchmarks/{benchmark_id}/forks")
def get_benchmark_forks(benchmark_id: int, session: Session = Depends(get_session)):
    """Return fork lineage for a benchmark."""
    from core.models import Benchmark
    bench = session.get(Benchmark, benchmark_id)
    if not bench:
        raise HTTPException(404)
    # Children: benchmarks forked FROM this one
    children = session.exec(
        select(Benchmark).where(Benchmark.forked_from == benchmark_id)
    ).all()
    # Parent
    parent = session.get(Benchmark, bench.forked_from) if getattr(bench, "forked_from", None) else None
    return {
        "benchmark_id": benchmark_id,
        "benchmark_name": bench.name,
        "parent": {"id": parent.id, "name": parent.name} if parent else None,
        "forks": [{"id": c.id, "name": c.name, "source": getattr(c, "source", "public")} for c in children],
        "fork_count": len(children),
        "lineage_depth": 1 if parent else 0,
    }


# ── #110 Multi-lab replication workflow ──────────────────────────────────────

class ReplicationRequest(BaseModel):
    workspace_id: int
    replicating_lab: str
    notes: str = ""


class ReplicationResult(BaseModel):
    workspace_id: int
    replicating_lab: str
    concordance_score: Optional[float] = None   # 0-1: how well results match
    successful: bool
    delta_capability: Optional[float] = None
    delta_propensity: Optional[float] = None
    notes: str = ""


class ScientificConfidence(BaseModel):
    workspace_id: int
    n_successful_replications: int
    n_failed_replications: int
    mean_concordance: float
    confidence_grade: str


def _compute_concordance(
    concordance_score: Optional[float],
    delta_capability: Optional[float],
    delta_propensity: Optional[float],
) -> float:
    """Compute normalized concordance (0..1), using explicit score when provided.

    If no concordance score is provided, use mean absolute delta distance from the
    original capability/propensity profile and invert it into a similarity score.
    """
    if concordance_score is not None:
        return max(0.0, min(1.0, concordance_score))
    if delta_capability is None or delta_propensity is None:
        return 0.0
    score = 1 - ((abs(delta_capability) + abs(delta_propensity)) / 2)
    return max(0.0, min(1.0, score))


def _get_completed_replications(replications: list[dict]) -> list[dict]:
    return [
        r
        for r in replications
        if r.get("type") == "replication_result"
        or (r.get("type") == "replication_request" and r.get("status") == "completed")
    ]


def _compute_scientific_confidence(workspace_id: int, replications: list[dict]) -> ScientificConfidence:
    completed = _get_completed_replications(replications)
    n_successful = sum(1 for r in completed if r.get("successful"))
    n_failed = sum(1 for r in completed if not r.get("successful"))
    concordance_values = [
        r.get("concordance_score")
        for r in completed
        if r.get("concordance_score") is not None
    ]
    mean_concordance = (
        sum(concordance_values) / len(concordance_values)
        if concordance_values
        else 0.0
    )
    # Scientific confidence rubric for independent replications:
    # - A: strong reproducibility (high concordance, >=3 successful, zero failures)
    # - B/C/D: progressively weaker confidence with lower replication support
    if not completed:
        grade = "insufficient"
    elif mean_concordance >= 0.9 and n_successful >= 3 and n_failed == 0:
        grade = "A"
    elif mean_concordance >= 0.75 and n_successful >= 2:
        grade = "B"
    elif n_successful >= 1:
        grade = "C"
    else:
        grade = "D"
    return ScientificConfidence(
        workspace_id=workspace_id,
        n_successful_replications=n_successful,
        n_failed_replications=n_failed,
        mean_concordance=round(mean_concordance, 3),
        confidence_grade=grade,
    )


@router.post("/workspaces/{workspace_id}/replications")
def request_replication(
    workspace_id: int,
    payload: ReplicationRequest,
    session: Session = Depends(get_session),
):
    """Request an independent replication of a workspace (#110)."""
    if payload.workspace_id != workspace_id:
        raise HTTPException(
            400,
            f"Workspace ID mismatch: expected {workspace_id}, got {payload.workspace_id}.",
        )
    ws = session.get(Workspace, workspace_id)
    if not ws:
        raise HTTPException(404, "Workspace not found.")
    # Store replication request in workspace tags/metadata
    import json as _json
    reps_raw = getattr(ws, "tags", "[]") or "[]"
    try:
        reps = _json.loads(reps_raw)
    except Exception:
        logger.debug("[research] failed to parse replication tags for workspace %s", workspace_id, exc_info=True)
        reps = []
    for rep in reps:
        if rep.get("type") == "replication_request" and rep.get("lab") == payload.replicating_lab and rep.get("status") == "pending":
            return {"workspace_id": workspace_id, "status": "replication_requested", "lab": payload.replicating_lab}
    reps.append({
        "type": "replication_request",
        "lab": payload.replicating_lab,
        "notes": payload.notes,
        "requested_at": datetime.now(UTC).isoformat(),
        "status": "pending",
    })
    ws.tags = _json.dumps(reps)
    session.add(ws)
    session.commit()
    return {"workspace_id": workspace_id, "status": "replication_requested", "lab": payload.replicating_lab}


@router.post("/workspaces/{workspace_id}/replications/submit")
def submit_replication_result(
    workspace_id: int,
    payload: ReplicationResult,
    session: Session = Depends(get_session),
):
    """Submit completed replication results (#110)."""
    if payload.workspace_id != workspace_id:
        raise HTTPException(
            400,
            f"Workspace ID mismatch: expected {workspace_id}, got {payload.workspace_id}.",
        )
    ws = session.get(Workspace, workspace_id)
    if not ws:
        raise HTTPException(404, "Workspace not found.")
    import json as _json
    reps_raw = getattr(ws, "tags", "[]") or "[]"
    try:
        reps = _json.loads(reps_raw)
    except Exception:
        logger.debug("[research] failed to parse replication tags for workspace %s", workspace_id, exc_info=True)
        reps = []
    concordance = _compute_concordance(
        payload.concordance_score,
        payload.delta_capability,
        payload.delta_propensity,
    )
    # Find and update matching pending request or add new
    found = False
    for rep in reps:
        if rep.get("type") == "replication_request" and rep.get("lab") == payload.replicating_lab and rep.get("status") == "pending":
            rep.update({
                "status": "completed",
                "concordance_score": concordance,
                "successful": payload.successful,
                "delta_capability": payload.delta_capability,
                "delta_propensity": payload.delta_propensity,
                "notes": payload.notes,
                "completed_at": datetime.now(UTC).isoformat(),
            })
            found = True
            break
    if not found:
        reps.append({
            "type": "replication_result",
            "lab": payload.replicating_lab,
            "concordance_score": concordance,
            "successful": payload.successful,
            "delta_capability": payload.delta_capability,
            "delta_propensity": payload.delta_propensity,
            "notes": payload.notes,
            "completed_at": datetime.now(UTC).isoformat(),
        })
    ws.tags = _json.dumps(reps)
    session.add(ws)
    session.commit()

    confidence = _compute_scientific_confidence(workspace_id, reps)
    completed = _get_completed_replications(reps)

    return {
        "workspace_id": workspace_id,
        "n_replications": len(completed),
        "n_successful": confidence.n_successful_replications,
        "n_failed": confidence.n_failed_replications,
        "avg_concordance": confidence.mean_concordance,
        "scientific_confidence_grade": confidence.confidence_grade,
        "scientific_confidence": confidence.model_dump(),
        "interpretation": (
            f"{confidence.n_successful_replications}/{len(completed)} successful replications. "
            f"Avg concordance: {confidence.mean_concordance:.0%}."
            if completed else "No independent replications yet."
        ),
    }


@router.get("/workspaces/{workspace_id}/replications")
def get_replications(workspace_id: int, session: Session = Depends(get_session)):
    """Get all replication requests and results for a workspace."""
    ws = session.get(Workspace, workspace_id)
    if not ws:
        raise HTTPException(404)
    import json as _json
    try:
        reps = _json.loads(getattr(ws, "tags", "[]") or "[]")
    except Exception:
        logger.debug("[research] failed to parse replication tags for workspace %s", workspace_id, exc_info=True)
        reps = []
    replications = [r for r in reps if r.get("type") in ("replication_request", "replication_result")]
    completed = _get_completed_replications(replications)
    confidence = _compute_scientific_confidence(workspace_id, replications)
    return {
        "workspace_id": workspace_id,
        "replications": replications,
        "summary": {
            "total": len(replications),
            "completed": len(completed),
            "successful": confidence.n_successful_replications,
            "failed": confidence.n_failed_replications,
            "mean_concordance": confidence.mean_concordance,
            "confidence_grade": confidence.confidence_grade,
        }
    }


# ── #111 Executable paper artifacts ──────────────────────────────────────────

@router.post("/workspaces/{workspace_id}/publish")
def publish_workspace(workspace_id: int, session: Session = Depends(get_session)):
    """
    Publish workspace as an executable paper artifact (#111).

    Generates a reproducibility package containing:
    - Metadata (hypothesis, protocol, risk domain)
    - All linked campaign manifests
    - Replication history and scientific confidence
    - Replication command
    - Permanent citation link (workspace slug)
    """
    ws = session.get(Workspace, workspace_id)
    if not ws:
        raise HTTPException(404, "Workspace not found.")

    import json as _json
    from core.models import ExperimentManifest

    # Get all linked manifests
    manifests = session.exec(
        select(ExperimentManifest).where(ExperimentManifest.workspace_id == workspace_id)
    ).all()

    # Get replication data from tags
    try:
        reps = _json.loads(getattr(ws, "tags", "[]") or "[]")
        replications = [r for r in reps if r.get("type") in ("replication_request", "replication_result")]
        confidence = _compute_scientific_confidence(workspace_id, replications)
    except Exception:
        logger.debug("[research] failed to load replication data for workspace %s", workspace_id, exc_info=True)
        replications = []
        confidence = ScientificConfidence(
            workspace_id=workspace_id,
            n_successful_replications=0,
            n_failed_replications=0,
            mean_concordance=0.0,
            confidence_grade="insufficient",
        )

    # Build the executable artifact
    artifact = {
        "mercury_paper": {
            "version": "1.0",
            "workspace_id": workspace_id,
            "workspace_slug": ws.slug,
            "title": ws.name,
            "description": ws.description,

            "science": {
                "hypothesis": ws.hypothesis,
                "protocol": ws.protocol,
                "risk_domain": ws.risk_domain,
            },

            "reproducibility": {
                "manifests": [
                    {
                        "manifest_id": m.id,
                        "campaign_id": m.campaign_id,
                        "seed": m.seed,
                        "temperature": getattr(m, "temperature", 0.0),
                        "judge_version": getattr(m, "judge_version", ""),
                        "benchmark_versions": _json.loads(getattr(m, "benchmark_versions_json", "{}") or "{}"),
                        "platform_version": getattr(m, "platform_version", "v0.6"),
                        "created_at": m.created_at.isoformat() if m.created_at else "",
                    }
                    for m in manifests
                ],
                "replication_command": (
                    f"mercury replicate --workspace {ws.slug} "
                    f"--seed {manifests[0].seed if manifests else 42} "
                    f"--verify"
                ),
            },

            "scientific_confidence": {
                "n_replications": len(replications),
                "n_successful": confidence.n_successful_replications,
                "n_failed": confidence.n_failed_replications,
                "mean_concordance": confidence.mean_concordance,
                "grade": confidence.confidence_grade,
                "interpretation": (
                    f"{confidence.n_successful_replications}/{len(replications)} successful replications. "
                    f"Avg concordance: {confidence.mean_concordance:.0%}."
                    if replications else "No independent replications yet."
                ),
            },

            "citation": {
                "mercury_url": f"mercury://workspace/{ws.slug}",
                "cite_as": (
                    f"Mercury Retrograde Research Workspace '{ws.name}' "
                    f"(INESIA, 2026). mercury://workspace/{ws.slug}"
                ),
            },

            "interactive": {
                "run_experiment": f"POST /api/research/workspaces/{workspace_id}/replications/submit",
                "view_results": f"GET /api/results/campaign/{{campaign_id}}",
                "generate_manifest": f"POST /api/research/manifests/generate/{{campaign_id}}",
            },

            "published_at": datetime.now(UTC).isoformat(),
            "visibility": "public",
        }
    }

    # Update workspace status to published
    ws.status = "published"
    ws.visibility = "public"
    session.add(ws)
    session.commit()

    return artifact
