"""
Evidence-Based Evaluation — RCT / RWD / RWE module.
Brings clinical trial rigor to AI safety evaluation.

RCT = Randomized Control Trial (controlled evaluation experiments)
RWD = Real World Data (production telemetry aggregation)
RWE = Real World Evidence (synthesis: does lab predict production?)
"""
import json
import math
import logging
import random
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from core.database import get_session
from core.config import get_settings
from core.models import (
    EvalTrial, RealWorldDataset, RealWorldEvidence,
    EvalRun, LLMModel, TelemetryEvent, JobStatus,
)

router = APIRouter(prefix="/evidence", tags=["evidence"])
logger = logging.getLogger(__name__)
settings = get_settings()


# ── Trial Design ───────────────────────────────────────────────────────────────

class TrialArm(BaseModel):
    name: str
    model_ids: list[int]
    benchmark_ids: list[int]
    conditions: dict = {}  # temperature, max_tokens, etc.

class TrialCreate(BaseModel):
    name: str = Field(..., min_length=2)
    hypothesis: str = Field(default="")
    primary_endpoint: str = Field(default="score")
    secondary_endpoints: list[str] = Field(default=[])
    arms: list[TrialArm] = Field(..., min_length=2)
    trial_type: str = Field(default="rct")
    randomization_method: str = Field(default="stratified")
    sample_size_per_arm: int = Field(default=100, ge=10, le=5000)
    blinding: str = Field(default="single")
    statistical_test: str = Field(default="mann_whitney")
    confidence_level: float = Field(default=0.95)
    workspace_id: Optional[int] = None


@router.post("/trials")
def create_trial(payload: TrialCreate, session: Session = Depends(get_session)):
    """Design a Randomized Control Trial for AI evaluation."""

    # Power analysis (simplified)
    alpha = 1 - payload.confidence_level
    # Cohen's d = 0.5 (medium effect) → required n per arm
    # Approximate: n = (z_alpha + z_beta)^2 * 2 / d^2
    z_alpha = 1.96 if payload.confidence_level == 0.95 else 2.576
    z_beta = 0.84  # 80% power
    min_n = int(math.ceil((z_alpha + z_beta) ** 2 * 2 / 0.25))  # d=0.5
    recommended_n = max(min_n, payload.sample_size_per_arm)

    power_analysis = {
        "alpha": alpha,
        "beta": 0.20,
        "power": 0.80,
        "effect_size": 0.5,
        "minimum_n_per_arm": min_n,
        "recommended_n_per_arm": recommended_n,
    }

    trial = EvalTrial(
        name=payload.name,
        workspace_id=payload.workspace_id,
        hypothesis=payload.hypothesis,
        trial_type=payload.trial_type,
        primary_endpoint=payload.primary_endpoint,
        secondary_endpoints=json.dumps(payload.secondary_endpoints),
        arms_json=json.dumps([a.dict() for a in payload.arms]),
        randomization_method=payload.randomization_method,
        randomization_seed=random.randint(1, 999999),
        sample_size_per_arm=recommended_n,
        blinding=payload.blinding,
        statistical_test=payload.statistical_test,
        confidence_level=payload.confidence_level,
        power_analysis_json=json.dumps(power_analysis),
    )
    session.add(trial)
    session.commit()
    session.refresh(trial)

    return {
        "trial_id": trial.id,
        "name": trial.name,
        "arms": len(payload.arms),
        "sample_size_per_arm": recommended_n,
        "power_analysis": power_analysis,
        "status": "draft",
        "next_step": "Link campaigns to each arm, then run them.",
    }


@router.get("/trials")
def list_trials(session: Session = Depends(get_session)):
    trials = session.exec(select(EvalTrial).order_by(EvalTrial.created_at.desc())).all()
    return {"trials": [{
        "id": t.id, "name": t.name, "status": t.status,
        "trial_type": t.trial_type, "hypothesis": t.hypothesis[:200],
        "arms": len(json.loads(t.arms_json)),
        "p_value": t.p_value, "conclusion": t.conclusion,
        "created_at": t.created_at.isoformat(),
    } for t in trials]}


@router.get("/trials/{trial_id}")
def get_trial(trial_id: int, session: Session = Depends(get_session)):
    t = session.get(EvalTrial, trial_id)
    if not t:
        raise HTTPException(404, detail="Trial not found.")
    return {
        "id": t.id, "name": t.name, "status": t.status,
        "trial_type": t.trial_type, "hypothesis": t.hypothesis,
        "primary_endpoint": t.primary_endpoint,
        "secondary_endpoints": json.loads(t.secondary_endpoints),
        "arms": json.loads(t.arms_json),
        "randomization": {"method": t.randomization_method, "seed": t.randomization_seed},
        "sample_size_per_arm": t.sample_size_per_arm,
        "blinding": t.blinding,
        "statistical_test": t.statistical_test,
        "confidence_level": t.confidence_level,
        "power_analysis": json.loads(t.power_analysis_json),
        "campaign_ids": json.loads(t.campaign_ids),
        "results": json.loads(t.results_json) if t.results_json != "{}" else None,
        "p_value": t.p_value, "effect_size": t.effect_size,
        "ci": [t.ci_lower, t.ci_upper] if t.ci_lower is not None else None,
        "conclusion": t.conclusion,
        "created_at": t.created_at.isoformat(),
    }


@router.post("/trials/{trial_id}/analyze")
def analyze_trial(trial_id: int, session: Session = Depends(get_session)):
    """Compute statistical analysis for a completed trial."""
    trial = session.get(EvalTrial, trial_id)
    if not trial:
        raise HTTPException(404, detail="Trial not found.")

    campaign_ids = json.loads(trial.campaign_ids)
    if not campaign_ids:
        raise HTTPException(400, detail="No campaigns linked to this trial.")

    arms = json.loads(trial.arms_json)

    # Collect scores per arm
    arm_scores = {}
    for i, campaign_id in enumerate(campaign_ids):
        runs = session.exec(
            select(EvalRun).where(EvalRun.campaign_id == campaign_id, EvalRun.status == JobStatus.COMPLETED)
        ).all()
        arm_name = arms[i]["name"] if i < len(arms) else f"Arm {i}"
        arm_scores[arm_name] = [r.score for r in runs if r.score is not None]

    if len(arm_scores) < 2:
        raise HTTPException(400, detail="Need at least 2 arms with completed runs.")

    arm_names = list(arm_scores.keys())
    group_a = arm_scores[arm_names[0]]
    group_b = arm_scores[arm_names[1]]

    if not group_a or not group_b:
        raise HTTPException(400, detail="Both arms need completed runs with scores.")

    # Statistical tests
    mean_a = sum(group_a) / len(group_a)
    mean_b = sum(group_b) / len(group_b)

    # Mann-Whitney U (non-parametric)
    p_value, effect_size = _mann_whitney_u(group_a, group_b)

    # Bootstrap confidence interval for mean difference
    ci_lower, ci_upper = _bootstrap_ci(group_a, group_b, confidence=trial.confidence_level)

    conclusion = "significant" if p_value < (1 - trial.confidence_level) else "not_significant"
    if len(group_a) < 20 or len(group_b) < 20:
        conclusion = "inconclusive (small sample)"

    results = {
        "arms": {name: {"n": len(scores), "mean": round(sum(scores)/len(scores), 4),
                         "std": round(_std(scores), 4), "min": round(min(scores), 4), "max": round(max(scores), 4)}
                 for name, scores in arm_scores.items()},
        "comparison": {
            "test": trial.statistical_test,
            "groups": [arm_names[0], arm_names[1]],
            "mean_difference": round(mean_b - mean_a, 4),
            "p_value": round(p_value, 6),
            "effect_size": round(effect_size, 4),
            "ci": [round(ci_lower, 4), round(ci_upper, 4)],
            "confidence_level": trial.confidence_level,
        },
        "conclusion": conclusion,
    }

    trial.results_json = json.dumps(results)
    trial.p_value = round(p_value, 6)
    trial.effect_size = round(effect_size, 4)
    trial.ci_lower = round(ci_lower, 4)
    trial.ci_upper = round(ci_upper, 4)
    trial.conclusion = conclusion
    trial.status = "completed"
    trial.completed_at = datetime.utcnow()
    session.add(trial)
    session.commit()

    return results


# ── Real World Data ────────────────────────────────────────────────────────────

@router.post("/rwd/collect")
def collect_rwd(
    model_id: int,
    hours: int = 168,  # 7 days default
    name: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """Aggregate telemetry into a Real World Dataset."""
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    events = session.exec(
        select(TelemetryEvent).where(
            TelemetryEvent.model_id == model_id,
            TelemetryEvent.timestamp >= cutoff,
        )
    ).all()

    if not events:
        raise HTTPException(400, detail="No telemetry events found for this model in the given period.")

    model = session.get(LLMModel, model_id)
    model_name = model.name if model else f"Model {model_id}"

    scores = [e.score for e in events if e.score is not None]
    latencies = [e.latency_ms for e in events]
    safety_flags = [e for e in events if e.safety_flag]
    errors = [e for e in events if e.event_type == "error"]

    # Build distributions
    score_bins = _histogram(scores, bins=10) if scores else []
    latency_bins = _histogram(latencies, bins=10) if latencies else []

    flag_dist = {}
    for e in safety_flags:
        flag_dist[e.safety_flag] = flag_dist.get(e.safety_flag, 0) + 1

    rwd = RealWorldDataset(
        name=name or f"RWD — {model_name} — {hours}h",
        model_id=model_id,
        source_type="telemetry",
        collection_start=min(e.timestamp for e in events),
        collection_end=max(e.timestamp for e in events),
        total_events=len(events),
        total_safety_flags=len(safety_flags),
        avg_latency_ms=round(sum(latencies) / len(latencies), 1) if latencies else 0,
        avg_score=round(sum(scores) / len(scores), 4) if scores else None,
        safety_flag_rate=round(len(safety_flags) / len(events), 4),
        error_rate=round(len(errors) / len(events), 4),
        score_distribution_json=json.dumps(score_bins),
        latency_distribution_json=json.dumps(latency_bins),
        failure_type_distribution_json=json.dumps(flag_dist),
    )
    session.add(rwd)
    session.commit()
    session.refresh(rwd)

    return {"rwd_id": rwd.id, "name": rwd.name, "total_events": len(events), "avg_score": rwd.avg_score}


@router.get("/rwd")
def list_rwd(session: Session = Depends(get_session)):
    datasets = session.exec(select(RealWorldDataset).order_by(RealWorldDataset.created_at.desc())).all()
    return {"datasets": [{
        "id": d.id, "name": d.name, "model_id": d.model_id,
        "total_events": d.total_events, "avg_score": d.avg_score,
        "safety_flag_rate": d.safety_flag_rate, "created_at": d.created_at.isoformat(),
    } for d in datasets]}


# ── Real World Evidence Synthesis ──────────────────────────────────────────────

@router.post("/rwe/synthesize")
def synthesize_evidence(
    trial_id: int,
    rwd_dataset_id: int,
    name: Optional[str] = None,
    workspace_id: Optional[int] = None,
    session: Session = Depends(get_session),
):
    """Synthesize RCT results with RWD into Real World Evidence.
    Answers: does the model's controlled evaluation predict its production behavior?
    """
    trial = session.get(EvalTrial, trial_id)
    if not trial:
        raise HTTPException(404, detail="Trial not found.")
    rwd = session.get(RealWorldDataset, rwd_dataset_id)
    if not rwd:
        raise HTTPException(404, detail="RWD dataset not found.")

    # Get RCT scores
    rct_results = json.loads(trial.results_json) if trial.results_json != "{}" else None
    rct_score = None
    if rct_results and "arms" in rct_results:
        all_means = [arm["mean"] for arm in rct_results["arms"].values()]
        rct_score = sum(all_means) / len(all_means) if all_means else None

    rwd_score = rwd.avg_score

    # Compute concordance and drift
    concordance = None
    behavior_drift = None
    safety_drift = None

    if rct_score is not None and rwd_score is not None:
        # Concordance: 1 - |RCT - RWD| / max(RCT, RWD)
        max_score = max(abs(rct_score), abs(rwd_score), 0.01)
        concordance = round(1 - abs(rct_score - rwd_score) / max_score, 4)
        behavior_drift = round(rwd_score - rct_score, 4)

    # Safety drift from RWD
    safety_drift = rwd.safety_flag_rate

    # Evidence grading
    if concordance is not None:
        if concordance > 0.9 and trial.p_value is not None and trial.p_value < 0.05:
            grade = "A"
        elif concordance > 0.7:
            grade = "B"
        elif concordance > 0.4:
            grade = "C"
        else:
            grade = "D"
    else:
        grade = "D"

    # Generalizability
    generalizability = concordance  # Simplified: concordance ≈ generalizability

    rwe = RealWorldEvidence(
        name=name or f"RWE — Trial #{trial_id} × RWD #{rwd_dataset_id}",
        trial_id=trial_id,
        rwd_dataset_id=rwd_dataset_id,
        workspace_id=workspace_id,
        rct_score=rct_score,
        rwd_score=rwd_score,
        concordance=concordance,
        generalizability=generalizability,
        behavior_drift=behavior_drift,
        safety_drift=safety_drift,
        evidence_grade=grade,
        conclusion=f"Evidence grade {grade}. RCT→RWD concordance: {concordance:.1%}. Behavior drift: {behavior_drift:+.4f}." if concordance else "Insufficient data.",
    )
    session.add(rwe)
    session.commit()
    session.refresh(rwe)

    return {
        "rwe_id": rwe.id,
        "evidence_grade": grade,
        "rct_score": rct_score,
        "rwd_score": rwd_score,
        "concordance": concordance,
        "behavior_drift": behavior_drift,
        "safety_drift": safety_drift,
        "conclusion": rwe.conclusion,
    }


@router.get("/rwe")
def list_rwe(session: Session = Depends(get_session)):
    evidences = session.exec(select(RealWorldEvidence).order_by(RealWorldEvidence.created_at.desc())).all()
    return {"evidence": [{
        "id": e.id, "name": e.name, "evidence_grade": e.evidence_grade,
        "rct_score": e.rct_score, "rwd_score": e.rwd_score,
        "concordance": e.concordance, "behavior_drift": e.behavior_drift,
        "created_at": e.created_at.isoformat(),
    } for e in evidences]}


@router.get("/rwe/{rwe_id}")
def get_rwe(rwe_id: int, session: Session = Depends(get_session)):
    e = session.get(RealWorldEvidence, rwe_id)
    if not e:
        raise HTTPException(404, detail="RWE not found.")
    return {
        "id": e.id, "name": e.name,
        "trial_id": e.trial_id, "rwd_dataset_id": e.rwd_dataset_id,
        "rct_score": e.rct_score, "rwd_score": e.rwd_score,
        "concordance": e.concordance, "generalizability": e.generalizability,
        "behavior_drift": e.behavior_drift, "safety_drift": e.safety_drift,
        "propensity_drift": e.propensity_drift,
        "evidence_grade": e.evidence_grade,
        "conclusion": e.conclusion, "recommendations": e.recommendations,
        "created_at": e.created_at.isoformat(),
    }


# ── Statistical helpers ────────────────────────────────────────────────────────

def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((x - mean) ** 2 for x in values) / (len(values) - 1))


def _mann_whitney_u(a: list[float], b: list[float]) -> tuple[float, float]:
    """Simplified Mann-Whitney U test. Returns (p_value_approx, effect_size)."""
    combined = [(v, 0) for v in a] + [(v, 1) for v in b]
    combined.sort(key=lambda x: x[0])

    # Assign ranks
    ranks = {}
    i = 0
    while i < len(combined):
        j = i
        while j < len(combined) and combined[j][0] == combined[i][0]:
            j += 1
        avg_rank = (i + j + 1) / 2  # 1-based average rank for ties
        for k in range(i, j):
            ranks[id(combined[k])] = avg_rank
        i = j

    r_a = sum(ranks[id(x)] for x in combined if x[1] == 0)
    n_a, n_b = len(a), len(b)
    u_a = r_a - n_a * (n_a + 1) / 2
    u = min(u_a, n_a * n_b - u_a)

    # Normal approximation for p-value
    mu = n_a * n_b / 2
    sigma = math.sqrt(n_a * n_b * (n_a + n_b + 1) / 12)
    if sigma == 0:
        return 1.0, 0.0
    z = abs(u - mu) / sigma

    # Approximate p-value from z (two-tailed)
    p_value = 2 * (1 - _normal_cdf(z))

    # Effect size: r = Z / sqrt(N)
    effect_size = z / math.sqrt(n_a + n_b) if (n_a + n_b) > 0 else 0

    return max(0.0, min(1.0, p_value)), effect_size


def _normal_cdf(x: float) -> float:
    """Approximate standard normal CDF."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _bootstrap_ci(a: list[float], b: list[float], confidence: float = 0.95, n_boot: int = 1000) -> tuple[float, float]:
    """Bootstrap confidence interval for mean difference."""
    rng = random.Random(42)
    diffs = []
    for _ in range(n_boot):
        sample_a = [rng.choice(a) for _ in range(len(a))]
        sample_b = [rng.choice(b) for _ in range(len(b))]
        diffs.append(sum(sample_b) / len(sample_b) - sum(sample_a) / len(sample_a))

    diffs.sort()
    alpha = 1 - confidence
    lo = int(n_boot * alpha / 2)
    hi = int(n_boot * (1 - alpha / 2))
    return diffs[lo], diffs[min(hi, len(diffs) - 1)]


def _histogram(values: list, bins: int = 10) -> list[dict]:
    """Simple histogram."""
    if not values:
        return []
    mn, mx = min(values), max(values)
    if mn == mx:
        return [{"bin_start": mn, "bin_end": mx, "count": len(values)}]
    width = (mx - mn) / bins
    result = []
    for i in range(bins):
        lo = mn + i * width
        hi = mn + (i + 1) * width
        count = sum(1 for v in values if lo <= v < hi or (i == bins - 1 and v == hi))
        result.append({"bin_start": round(lo, 4), "bin_end": round(hi, 4), "count": count})
    return result
