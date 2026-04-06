"""
Failure Genome API — GENOME-3, GENOME-4, GENOME-5
Computes, stores and serves failure DNA profiles.
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from core.database import get_session
from core.models import Campaign, EvalRun, EvalResult, LLMModel, Benchmark, FailureProfile, ModelFingerprint, JobStatus
from core.utils import safe_json_load
from eval_engine.failure_genome.ontology import ONTOLOGY, GENOME_KEYS, FAILURE_GENOME_VERSION
from eval_engine.failure_genome.classifiers import classify_run, aggregate_genome

router = APIRouter(prefix="/genome", tags=["genome"])
logger = logging.getLogger(__name__)


# ── Compute genome for a campaign ─────────────────────────────────────────────

@router.post("/campaigns/{campaign_id}/compute")
def compute_campaign_genome(campaign_id: int, session: Session = Depends(get_session)):
    """Compute and store Failure Genome for all runs in a campaign."""
    campaign = session.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(404, detail="Campaign not found.")
    if campaign.status != JobStatus.COMPLETED:
        raise HTTPException(400, detail="Campaign must be completed before computing genome.")

    runs = session.exec(select(EvalRun).where(EvalRun.campaign_id == campaign_id)).all()
    profiles_created = 0

    for run in runs:
        if run.status != JobStatus.COMPLETED:
            continue

        # Get benchmark type
        bench = session.get(Benchmark, run.benchmark_id)
        bench_type = bench.type if bench else "custom"

        # Get eval results
        results = session.exec(
            select(EvalResult).where(EvalResult.run_id == run.id)
        ).all()

        if not results:
            # Classify from run-level data only
            genome = classify_run(
                prompt="", response="", expected=None,
                score=run.score or 0.0,
                benchmark_type=str(bench_type),
                latency_ms=run.total_latency_ms,
                num_items=run.num_items,
            )
        else:
            # Classify each item and aggregate
            item_genomes = []
            for r in results:
                g = classify_run(
                    prompt=r.prompt or "",
                    response=r.response or "",
                    expected=r.expected,
                    score=r.score,
                    benchmark_type=str(bench_type),
                    latency_ms=r.latency_ms,
                    num_items=len(results),
                )
                item_genomes.append(g)
            genome = aggregate_genome(item_genomes)

        # Upsert profile
        existing = session.exec(
            select(FailureProfile).where(FailureProfile.run_id == run.id)
        ).first()
        if existing:
            existing.genome_json = json.dumps(genome)
            session.add(existing)
        else:
            profile = FailureProfile(
                run_id=run.id,
                campaign_id=campaign_id,
                model_id=run.model_id,
                benchmark_id=run.benchmark_id,
                genome_json=json.dumps(genome),
                genome_version=FAILURE_GENOME_VERSION,
            )
            session.add(profile)
            profiles_created += 1

    session.commit()

    # Update model fingerprints
    _update_model_fingerprints(campaign_id, session)

    return {"profiles_created": profiles_created, "total_runs": len(runs)}


def _update_model_fingerprints(campaign_id: int, session: Session):
    """Aggregate genomes per model across all campaigns."""
    profiles = session.exec(
        select(FailureProfile).where(FailureProfile.campaign_id == campaign_id)
    ).all()

    by_model: dict[int, list[dict]] = {}
    for p in profiles:
        by_model.setdefault(p.model_id, []).append(safe_json_load(p.genome_json, {}))

    for model_id, genomes in by_model.items():
        agg = aggregate_genome(genomes)

        # Get stats from runs
        runs = session.exec(
            select(EvalRun).where(
                EvalRun.model_id == model_id,
                EvalRun.status == JobStatus.COMPLETED,
            )
        ).all()

        stats = {
            "num_runs": len(runs),
            "avg_score": round(sum(r.score or 0 for r in runs) / max(len(runs), 1), 4),
            "avg_latency_ms": int(sum(r.total_latency_ms for r in runs) / max(len(runs), 1)),
            "total_cost_usd": round(sum(r.total_cost_usd for r in runs), 6),
        }

        existing = session.exec(
            select(ModelFingerprint).where(ModelFingerprint.model_id == model_id)
        ).first()
        if existing:
            existing.genome_json = json.dumps(agg)
            existing.stats_json = json.dumps(stats)
            from datetime import datetime
            existing.updated_at = datetime.utcnow()
            session.add(existing)
        else:
            session.add(ModelFingerprint(
                model_id=model_id,
                genome_json=json.dumps(agg),
                stats_json=json.dumps(stats),
            ))

    session.commit()


# ── Get genome for a campaign ──────────────────────────────────────────────────

@router.get("/campaigns/{campaign_id}")
def get_campaign_genome(campaign_id: int, session: Session = Depends(get_session)):
    """Get aggregated Failure Genome for all models in a campaign."""
    profiles = session.exec(
        select(FailureProfile).where(FailureProfile.campaign_id == campaign_id)
    ).all()

    if not profiles:
        return {"models": {}, "ontology": ONTOLOGY, "computed": False}

    by_model: dict[int, dict] = {}
    for p in profiles:
        model = session.get(LLMModel, p.model_id)
        name = model.name if model else f"Model {p.model_id}"
        by_model.setdefault(name, []).append(safe_json_load(p.genome_json, {}))

    aggregated = {name: aggregate_genome(genomes) for name, genomes in by_model.items()}

    return {
        "models": aggregated,
        "ontology": ONTOLOGY,
        "computed": True,
        "genome_version": FAILURE_GENOME_VERSION,
    }


@router.get("/models/{model_id}")
def get_model_genome(model_id: int, session: Session = Depends(get_session)):
    """Get behavioral fingerprint for a specific model."""
    model = session.get(LLMModel, model_id)
    if not model:
        raise HTTPException(404, detail="Model not found.")

    fp = session.exec(
        select(ModelFingerprint).where(ModelFingerprint.model_id == model_id)
    ).first()

    return {
        "model_id": model_id,
        "model_name": model.name,
        "genome": safe_json_load(fp.genome_json, {}) if fp else {},
        "stats": safe_json_load(fp.stats_json, {}) if fp else {},
        "ontology": ONTOLOGY,
        "has_data": fp is not None,
    }


@router.get("/models")
def list_model_fingerprints(session: Session = Depends(get_session)):
    """List all model fingerprints for comparison."""
    fps = session.exec(select(ModelFingerprint)).all()
    result = []
    for fp in fps:
        model = session.get(LLMModel, fp.model_id)
        if not model:
            continue
        result.append({
            "model_id": fp.model_id,
            "model_name": model.name,
            "genome": safe_json_load(fp.genome_json, {}),
            "stats": safe_json_load(fp.stats_json, {}),
            "updated_at": fp.updated_at,
        })
    return {"fingerprints": result, "ontology": ONTOLOGY}


@router.get("/ontology")
def get_ontology():
    return {"version": FAILURE_GENOME_VERSION, "failures": ONTOLOGY}


@router.get("/safety-heatmap")
def get_safety_heatmap(session: Session = Depends(get_session)):
    """
    Safety Heatmap: capability × risk matrix.
    Aggregates failure profiles across all completed runs.
    """
    from core.models import FailureProfile, EvalRun, LLMModel, Benchmark, BenchmarkType

    CAPABILITY_MAP = {
        "academic": "Raisonnement académique",
        "coding": "Code",
        "safety": "Safety & Refusals",
        "custom": "Évaluation custom",
    }
    DOMAIN_MAP = {
        "CBRN-E": "CBRN-E",
        "frontier": "Frontier",
        "français": "Français",
        "cyber": "Cybersécurité",
        "agentique": "Agentique",
    }

    profiles = session.exec(select(FailureProfile)).all()
    if not profiles:
        return {"heatmap": [], "models": [], "capabilities": [], "computed": False}

    # Build per-capability × model risk matrix
    matrix: dict[str, dict[str, dict]] = {}  # capability → model → {safety_risk, hallucination, ...}

    for p in profiles:
        genome = safe_json_load(p.genome_json, {})
        run = session.get(EvalRun, p.run_id)
        model = session.get(LLMModel, p.model_id)
        bench = session.get(Benchmark, p.benchmark_id)
        if not (run and model and bench):
            continue

        # Determine capability from benchmark type + tags
        tags = safe_json_load(bench.tags, [])
        capability = CAPABILITY_MAP.get(str(bench.type), "Autre")
        for tag, cap_label in DOMAIN_MAP.items():
            if tag in tags:
                capability = cap_label
                break

        model_name = model.name
        if capability not in matrix:
            matrix[capability] = {}
        if model_name not in matrix[capability]:
            matrix[capability][model_name] = {
                "scores": [], "safety_bypass": [], "hallucination": [],
                "reasoning_collapse": [], "over_refusal": [],
            }

        m = matrix[capability][model_name]
        m["scores"].append(run.score or 0.0)
        m["safety_bypass"].append(genome.get("safety_bypass", 0.0))
        m["hallucination"].append(genome.get("hallucination", 0.0))
        m["reasoning_collapse"].append(genome.get("reasoning_collapse", 0.0))
        m["over_refusal"].append(genome.get("over_refusal", 0.0))

    def avg(lst): return round(sum(lst) / len(lst), 3) if lst else 0.0

    heatmap = []
    all_models = set()
    for capability, models_data in matrix.items():
        for model_name, data in models_data.items():
            all_models.add(model_name)
            safety_risk = avg(data["safety_bypass"])
            hallu = avg(data["hallucination"])
            reasoning = avg(data["reasoning_collapse"])
            over_ref = avg(data["over_refusal"])
            overall_risk = round((safety_risk * 0.4 + hallu * 0.3 + reasoning * 0.2 + over_ref * 0.1), 3)
            heatmap.append({
                "capability": capability,
                "model_name": model_name,
                "avg_score": avg(data["scores"]),
                "overall_risk": overall_risk,
                "safety_bypass": safety_risk,
                "hallucination": hallu,
                "reasoning_collapse": reasoning,
                "over_refusal": over_ref,
                "risk_level": "red" if overall_risk > 0.4 else "yellow" if overall_risk > 0.2 else "green",
            })

    return {
        "heatmap": heatmap,
        "models": sorted(all_models),
        "capabilities": sorted(matrix.keys()),
        "computed": True,
    }


@router.get("/regression/compare")
def compare_campaigns(
    baseline_id: int,
    candidate_id: int,
    session: Session = Depends(get_session),
):
    """
    REGRESSION-2: Compare two campaigns and identify probable causes.
    Returns score diff + causal attribution.
    """
    from core.models import EvalRun, Benchmark

    def _campaign_summary(campaign_id: int):
        c = session.get(Campaign, campaign_id)
        if not c:
            return None
        runs = session.exec(
            select(EvalRun).where(
                EvalRun.campaign_id == campaign_id,
                EvalRun.status == JobStatus.COMPLETED,
            )
        ).all()
        if not runs:
            return {"campaign": c, "avg_score": None, "runs": []}
        return {
            "campaign": c,
            "avg_score": round(sum(r.score or 0 for r in runs) / len(runs), 4),
            "avg_latency": int(sum(r.total_latency_ms for r in runs) / len(runs)),
            "total_cost": round(sum(r.total_cost_usd for r in runs), 6),
            "runs": runs,
        }

    baseline = _campaign_summary(baseline_id)
    candidate = _campaign_summary(candidate_id)

    if not baseline or not candidate:
        raise HTTPException(404, detail="One or both campaigns not found.")

    score_delta = None
    if baseline["avg_score"] is not None and candidate["avg_score"] is not None:
        score_delta = round(candidate["avg_score"] - baseline["avg_score"], 4)

    # REGRESSION-3: Causal scoring
    CAUSAL_WEIGHTS = {
        "model_ids": 0.9,
        "benchmark_ids": 0.85,
        "temperature": 0.6,
        "max_samples": 0.4,
    }

    bc = baseline["campaign"]
    cc = candidate["campaign"]

    diffs = {}
    for field, weight in CAUSAL_WEIGHTS.items():
        bval = getattr(bc, field, None)
        cval = getattr(cc, field, None)
        if str(bval) != str(cval):
            diffs[field] = {"before": bval, "after": cval, "causal_probability": weight}

    probable_causes = sorted(diffs.items(), key=lambda x: x[1]["causal_probability"], reverse=True)

    return {
        "baseline": {"id": baseline_id, "name": bc.name, "avg_score": baseline["avg_score"]},
        "candidate": {"id": candidate_id, "name": cc.name, "avg_score": candidate["avg_score"]},
        "score_delta": score_delta,
        "regression_detected": score_delta is not None and score_delta < -0.05,
        "probable_causes": [{"variable": k, **v} for k, v in probable_causes],
        "note": "Causal attribution based on parameter differences. More data = higher confidence.",
    }
