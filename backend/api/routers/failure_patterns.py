"""
Failure Patterns API — Clustering, Anomaly Detection & Human Validation (#114)
===============================================================================
Exposes three sets of endpoints:

  PR1 — Failure clustering
    POST /failure-patterns/cluster           — cluster a set of failure records
    GET  /failure-patterns/taxonomy          — list confirmed failure patterns

  PR2 — Anomaly detection
    POST /failure-patterns/anomalies         — run anomaly detection on scores
    POST /failure-patterns/performance-delta — compare current vs baseline scores

  PR3 — Human validation gate
    GET  /failure-patterns/pending           — list clusters awaiting human review
    POST /failure-patterns/{cluster_id}/confirm — confirm → enters taxonomy
    POST /failure-patterns/{cluster_id}/reject  — reject → discarded
    DELETE /failure-patterns/taxonomy/{pattern_id} — retire a confirmed pattern

Human validation gate:
  All auto-discovered failure clusters go into a "pending review" queue.
  A human reviewer must explicitly confirm or reject each cluster before it
  enters the canonical failure taxonomy.  Confirmed patterns can then be used
  to guide (but never auto-generate) new eval cases.
"""

import logging
import uuid
from datetime import datetime, UTC
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from eval_engine.failure_clustering import FailureClusteringEngine, FailureCluster, ClusteringReport
from eval_engine.anomaly_detection import AnomalyDetectionEngine

router = APIRouter(prefix="/failure-patterns", tags=["failure-patterns"])
logger = logging.getLogger(__name__)


# ── In-memory stores (production: replace with DB tables) ─────────────────────

# Pending clusters awaiting human validation
_pending_clusters: dict[str, dict] = {}

# Confirmed failure taxonomy entries
_confirmed_taxonomy: dict[str, dict] = {}

# Rejected cluster IDs (to avoid re-alerting)
_rejected_ids: set[str] = set()


# ── Schemas ────────────────────────────────────────────────────────────────────

class FailureRecord(BaseModel):
    prompt: str = ""
    response: str = ""
    model_name: str = "unknown"
    score: float = 0.0
    severity: str = "unknown"
    category: str = ""


class ClusterRequest(BaseModel):
    failures: list[FailureRecord]
    campaign_id: int = 0
    similarity_threshold: float = 0.3
    min_cluster_size: int = 2


class AnomalyRequest(BaseModel):
    scores: list[float]
    campaign_id: int = 0
    model_name: str = "unknown"


class PerformanceDeltaRequest(BaseModel):
    baseline_scores: dict[str, float]   # {benchmark_name: mean_score}
    current_scores: dict[str, float]
    model_name: str = "unknown"
    campaign_id: int = 0


class ConfirmPatternRequest(BaseModel):
    reviewer: str = "human"
    notes: str = ""
    suggested_name: Optional[str] = None


class RejectPatternRequest(BaseModel):
    reviewer: str = "human"
    reason: str = ""


def _cluster_to_dict(c: FailureCluster) -> dict:
    return {
        "cluster_id": c.cluster_id,
        "name": c.name,
        "failure_type": c.failure_type,
        "n_instances": c.n_instances,
        "reproducibility_score": c.reproducibility_score,
        "affected_models": c.affected_models,
        "representative_traces": c.representative_traces,
        "hypothesis": c.hypothesis,
        "is_novel": c.is_novel,
        "severity": c.severity,
        "common_keywords": c.common_keywords,
        "severity_distribution": c.severity_distribution,
        "recommended_benchmark": c.recommended_benchmark,
        "cross_model": c.cross_model,
    }


# ── PR1: Failure clustering ────────────────────────────────────────────────────

@router.post("/cluster")
def cluster_failures(req: ClusterRequest):
    """
    Cluster failure traces by semantic similarity.

    Novel clusters are automatically queued for human validation.
    No cluster enters the canonical taxonomy without human confirmation.
    """
    engine = FailureClusteringEngine(
        similarity_threshold=req.similarity_threshold,
        min_cluster_size=req.min_cluster_size,
    )
    failures = [f.model_dump() for f in req.failures]
    report: ClusteringReport = engine.discover(failures, campaign_id=req.campaign_id)

    # Queue novel clusters for human validation (if not already seen/rejected)
    newly_queued: list[str] = []
    for cluster in report.novel_clusters:
        cid = cluster.cluster_id
        if cid not in _pending_clusters and cid not in _rejected_ids and cid not in _confirmed_taxonomy:
            _pending_clusters[cid] = {
                **_cluster_to_dict(cluster),
                "queued_at": datetime.now(UTC).isoformat(),
                "campaign_id": req.campaign_id,
                "status": "pending_review",
            }
            newly_queued.append(cid)
            logger.info("Novel cluster queued for human validation: %s", cid)

    return {
        "campaign_id": report.campaign_id,
        "n_failures": report.n_failures,
        "n_clusters": report.n_clusters,
        "novel_clusters": [_cluster_to_dict(c) for c in report.novel_clusters],
        "known_clusters": [_cluster_to_dict(c) for c in report.known_clusters],
        "all_clusters": [_cluster_to_dict(c) for c in report.all_clusters],
        "cross_model_patterns": report.cross_model_patterns,
        "top_emerging_risk": report.top_emerging_risk,
        "summary": report.summary,
        "alerts": report.alerts,
        "failure_genome_version": report.failure_genome_version,
        "newly_queued_for_review": newly_queued,
        "validation_gate": {
            "message": (
                "Novel clusters have been queued for human review. "
                "No failure pattern enters the canonical taxonomy without human confirmation."
            ) if newly_queued else "No new patterns to review.",
            "pending_count": len(_pending_clusters),
        },
    }


# ── PR1: Taxonomy listing ─────────────────────────────────────────────────────

@router.get("/taxonomy")
def list_taxonomy():
    """
    List all confirmed failure patterns in the canonical taxonomy.

    These are patterns that have been explicitly confirmed by a human reviewer.
    """
    return {
        "taxonomy": list(_confirmed_taxonomy.values()),
        "count": len(_confirmed_taxonomy),
        "note": (
            "All entries in this taxonomy have been confirmed by a human reviewer. "
            "Automated analysis discovers pattern candidates; humans decide what enters here."
        ),
    }


# ── PR2: Anomaly detection ─────────────────────────────────────────────────────

@router.post("/anomalies")
def detect_anomalies(req: AnomalyRequest):
    """
    Detect statistical anomalies in an evaluation score distribution.

    Flags: uniform scores (possible judge anchoring), impossible scores,
    bimodal collapse (loss of discrimination).
    """
    engine = AnomalyDetectionEngine()
    alerts = engine.analyse_score_distribution(
        req.scores,
        campaign_id=req.campaign_id,
        model_name=req.model_name,
    )
    return {
        "campaign_id": req.campaign_id,
        "model_name": req.model_name,
        "n_scores": len(req.scores),
        "alerts": [
            {
                "alert_id": a.alert_id,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "description": a.description,
                "metric_value": a.metric_value,
                "threshold": a.threshold,
                "affected_count": a.affected_count,
                "recommendation": a.recommendation,
            }
            for a in alerts
        ],
        "is_clean": len(alerts) == 0,
        "summary": f"Found {len(alerts)} alert(s)." if alerts else "Score distribution looks clean.",
    }


@router.post("/performance-delta")
def detect_performance_delta(req: PerformanceDeltaRequest):
    """
    Compare current benchmark scores against a baseline.

    Returns alerts for significant regressions (>15pp drop) or unexpected
    improvements (possible contamination).
    """
    engine = AnomalyDetectionEngine()
    alerts = engine.detect_performance_changes(
        baseline_scores=req.baseline_scores,
        current_scores=req.current_scores,
        model_name=req.model_name,
        campaign_id=req.campaign_id,
    )
    return {
        "campaign_id": req.campaign_id,
        "model_name": req.model_name,
        "alerts": [
            {
                "alert_id": a.alert_id,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "description": a.description,
                "benchmark": a.benchmark,
                "baseline_score": a.baseline_score,
                "current_score": a.current_score,
                "delta": a.delta,
                "recommendation": a.recommendation,
            }
            for a in alerts
        ],
        "is_clean": len(alerts) == 0,
        "summary": f"Found {len(alerts)} performance alert(s)." if alerts else "No significant performance changes.",
    }


# ── PR3: Human validation gate ─────────────────────────────────────────────────

@router.get("/pending")
def list_pending():
    """
    List all failure clusters awaiting human validation.

    These are novel patterns discovered by automated clustering that have
    NOT yet been confirmed or rejected by a human reviewer.
    """
    return {
        "pending": list(_pending_clusters.values()),
        "count": len(_pending_clusters),
        "gate_policy": (
            "All automatically discovered failure patterns require human confirmation "
            "before entering the canonical failure taxonomy. "
            "Failure *analysis* is automated; eval *creation* is human-only."
        ),
    }


@router.post("/{cluster_id}/confirm")
def confirm_pattern(cluster_id: str, req: ConfirmPatternRequest):
    """
    Confirm a pending failure cluster as a canonical failure pattern.

    Moves the cluster from the pending queue to the confirmed taxonomy.
    This is the human validation gate — no automated path bypasses this step.
    """
    if cluster_id not in _pending_clusters:
        if cluster_id in _confirmed_taxonomy:
            raise HTTPException(400, detail="Pattern already confirmed.")
        if cluster_id in _rejected_ids:
            raise HTTPException(400, detail="Pattern was previously rejected. Cannot confirm a rejected pattern.")
        raise HTTPException(404, detail="Cluster not found in pending queue.")

    cluster = _pending_clusters.pop(cluster_id)

    pattern_id = str(uuid.uuid4())
    taxonomy_entry = {
        **cluster,
        "pattern_id": pattern_id,
        "status": "confirmed",
        "confirmed_at": datetime.now(UTC).isoformat(),
        "confirmed_by": req.reviewer,
        "reviewer_notes": req.notes,
        "name": req.suggested_name or cluster.get("name", cluster_id),
        "eval_creation_required": True,
        "eval_creation_note": (
            "A human evaluator should create benchmark cases for this pattern. "
            "Do NOT auto-generate eval cases from failure traces — this causes eval contamination."
        ),
    }
    _confirmed_taxonomy[pattern_id] = taxonomy_entry
    logger.info("Failure pattern confirmed by %s: %s → %s", req.reviewer, cluster_id, pattern_id)

    return {
        "status": "confirmed",
        "pattern_id": pattern_id,
        "message": (
            f"Pattern '{taxonomy_entry['name']}' confirmed by {req.reviewer} "
            f"and added to the failure taxonomy."
        ),
        "next_steps": (
            "A human evaluator should now design benchmark cases for this failure pattern. "
            "Automated eval generation is explicitly excluded to prevent circular evaluation."
        ),
    }


@router.post("/{cluster_id}/reject")
def reject_pattern(cluster_id: str, req: RejectPatternRequest):
    """
    Reject a pending failure cluster.

    The cluster is discarded and will not be re-alerted in future runs.
    """
    if cluster_id not in _pending_clusters:
        if cluster_id in _confirmed_taxonomy:
            raise HTTPException(400, detail="Cannot reject an already confirmed pattern.")
        if cluster_id in _rejected_ids:
            return {"status": "already_rejected", "cluster_id": cluster_id}
        raise HTTPException(404, detail="Cluster not found in pending queue.")

    cluster = _pending_clusters.pop(cluster_id)
    _rejected_ids.add(cluster_id)
    logger.info("Failure pattern rejected by %s: %s (reason: %s)", req.reviewer, cluster_id, req.reason)

    return {
        "status": "rejected",
        "cluster_id": cluster_id,
        "rejected_by": req.reviewer,
        "reason": req.reason,
        "message": (
            f"Cluster '{cluster.get('name', cluster_id)}' rejected. "
            "It will not re-enter the review queue for future matching runs."
        ),
    }


@router.delete("/taxonomy/{pattern_id}")
def retire_pattern(pattern_id: str):
    """
    Retire a confirmed failure pattern from the taxonomy.

    Use when a pattern is no longer relevant or has been superseded.
    """
    if pattern_id not in _confirmed_taxonomy:
        raise HTTPException(404, detail="Pattern not found in taxonomy.")

    entry = _confirmed_taxonomy.pop(pattern_id)
    logger.info("Failure taxonomy pattern retired: %s", pattern_id)

    return {
        "status": "retired",
        "pattern_id": pattern_id,
        "name": entry.get("name", pattern_id),
        "message": "Pattern retired from canonical taxonomy.",
    }
