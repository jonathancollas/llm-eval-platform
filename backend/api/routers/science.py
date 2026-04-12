"""
Science Engine API (#81, #82, #85)
====================================
Capability vs Propensity · Mech Interp Validation · Benchmark Contamination
"""
import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from core.database import get_session
from core.config import get_settings
from core.models import LLMModel, Benchmark, EvalRun, EvalResult, JobStatus
from inference.adapter import get_adapter
from eval_engine.capability_propensity import CapabilityPropensityEngine
from eval_engine.mech_interp import MechInterpValidator
from eval_engine.contamination import analyze_contamination

router = APIRouter(prefix="/science", tags=["science"])
logger = logging.getLogger(__name__)
settings = get_settings()


# ── Shared helper ─────────────────────────────────────────────────────────────

def _get_questions(benchmark: Benchmark, n: int, session: Session) -> list[dict]:
    """Pull sample questions from DB eval results or benchmark dataset file."""
    runs = session.exec(
        select(EvalRun).where(
            EvalRun.benchmark_id == benchmark.id,
            EvalRun.status == JobStatus.COMPLETED,
        ).limit(3)
    ).all()

    if runs:
        run_ids = [r.id for r in runs]
        results = session.exec(
            select(EvalResult).where(EvalResult.run_id.in_(run_ids)).limit(n)
        ).all()
        if results:
            return [{"question": r.prompt, "expected": r.expected or "",
                     "category": benchmark.type} for r in results if r.prompt]

    if benchmark.dataset_path:
        from pathlib import Path
        bench_path = Path(settings.bench_library_path) / benchmark.dataset_path
        if bench_path.exists():
            try:
                data = json.loads(bench_path.read_text())
                items = data if isinstance(data, list) else data.get("items", [])
                return [
                    {"question": i.get("prompt", i.get("question", "")),
                     "expected": i.get("expected", i.get("answer", "")),
                     "category": i.get("category", benchmark.type)}
                    for i in items[:n] if i.get("prompt") or i.get("question")
                ]
            except Exception as e:
                logger.warning(f"Failed to load benchmark dataset for questions: {e}")
    return []


# ── #81 Capability vs Propensity ──────────────────────────────────────────────

class CapPropRequest(BaseModel):
    model_id: int
    benchmark_id: int
    n_samples: int = 15
    include_tail: bool = True


@router.post("/capability-propensity")
async def run_capability_propensity(
    payload: CapPropRequest,
    session: Session = Depends(get_session),
):
    """
    Formally separate capability from propensity scores.

    CAPABILITY — maximum performance under expert elicitation (CoT, few-shot, optimal prompting)
    PROPENSITY — spontaneous behaviour under operational/default prompting

    Gap = capability - propensity.
    A large positive gap means the model is capable but doesn't apply it spontaneously.
    Critical for safety benchmarks: high capability ≠ safe propensity.

    Reference: INESIA PDF Priority 2 · AgentDojo (Debenedetti et al., 2024)
    """
    model = session.get(LLMModel, payload.model_id)
    if not model:
        raise HTTPException(404, "Model not found.")
    benchmark = session.get(Benchmark, payload.benchmark_id)
    if not benchmark:
        raise HTTPException(404, "Benchmark not found.")

    questions = _get_questions(benchmark, payload.n_samples, session)
    if not questions:
        raise HTTPException(422, "No questions available. Run an evaluation campaign first.")

    engine = CapabilityPropensityEngine(adapter_factory=get_adapter)
    try:
        report = await asyncio.wait_for(
            engine.run(model=model, benchmark_name=benchmark.name,
                       questions=questions, n_samples=payload.n_samples,
                       include_tail=payload.include_tail),
            timeout=300.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(408, "Analysis timed out. Reduce n_samples.")

    return {
        "model_name": report.model_name,
        "benchmark_name": report.benchmark_name,
        "n_probes": report.n_probes,
        "scores": {
            "mean_capability": report.mean_capability,
            "mean_propensity": report.mean_propensity,
            "mean_gap": report.mean_gap,
            "gap_direction": report.gap_direction,
            "gap_significance": report.gap_significance,
        },
        "tail_analysis": {
            "p10_propensity": report.tail_propensity_p10,
            "p5_propensity": report.tail_propensity_p5,
            "worst_case_gap": report.worst_case_gap,
            "propensity_skew": report.propensity_skew,
        },
        "variance": {
            "capability_variance": report.capability_variance,
            "propensity_variance": report.propensity_variance,
        },
        "safety": {
            "concern": report.safety_concern,
            "reason": report.safety_concern_reason,
        },
        "probes": [
            {
                "question": p.question,
                "capability_score": p.capability_score,
                "propensity_score": p.propensity_score,
                "gap": p.gap,
                "category": p.category,
            }
            for p in report.probes
        ],
        "performance": {
            "total_tokens": report.total_tokens,
            "total_cost_usd": report.total_cost_usd,
        },
        "references": [
            "INESIA PDF Priority 2 — Capability vs propensity: a distinction that must be formalised",
            "AgentDojo (Debenedetti et al., 2024) — high capability ≠ safe propensity",
            "INESIA PDF — tail-of-distribution propensity measurement (importance sampling)",
        ],
    }


@router.get("/capability-propensity/runs")
def get_capability_propensity_from_runs(
    model_id: int,
    benchmark_id: Optional[int] = None,
    session: Session = Depends(get_session),
):
    """
    Retrieve already-computed capability vs propensity scores from eval runs.
    Benchmarks with eval_dimension='capability' or 'propensity' are separated.
    """
    query = select(EvalRun).where(
        EvalRun.model_id == model_id,
        EvalRun.status == JobStatus.COMPLETED,
    )
    if benchmark_id:
        query = query.where(EvalRun.benchmark_id == benchmark_id)

    runs = session.exec(query).all()
    model = session.get(LLMModel, model_id)
    model_name = model.name if model else f"Model {model_id}"

    capability_runs = []
    propensity_runs = []

    for run in runs:
        bench = session.get(Benchmark, run.benchmark_id)
        dim = getattr(bench, "eval_dimension", "capability") if bench else "capability"
        bench_name = bench.name if bench else f"Bench {run.benchmark_id}"
        entry = {
            "run_id": run.id,
            "benchmark_name": bench_name,
            "eval_dimension": dim,
            "score": run.score,
            "capability_score": getattr(run, "capability_score", None),
            "propensity_score": getattr(run, "propensity_score", None),
        }
        if dim == "propensity":
            propensity_runs.append(entry)
        else:
            capability_runs.append(entry)

    cap_scores = [r["capability_score"] or r["score"] for r in capability_runs if r.get("capability_score") or r.get("score")]
    prop_scores = [r["propensity_score"] or r["score"] for r in propensity_runs if r.get("propensity_score") or r.get("score")]

    avg_cap = round(sum(cap_scores) / len(cap_scores), 4) if cap_scores else None
    avg_prop = round(sum(prop_scores) / len(prop_scores), 4) if prop_scores else None
    gap = round(avg_cap - avg_prop, 4) if avg_cap and avg_prop else None

    return {
        "model_id": model_id,
        "model_name": model_name,
        "capability": {
            "runs": capability_runs,
            "avg_score": avg_cap,
            "n_runs": len(capability_runs),
        },
        "propensity": {
            "runs": propensity_runs,
            "avg_score": avg_prop,
            "n_runs": len(propensity_runs),
        },
        "gap": gap,
        "gap_significance": (
            "critical" if gap and abs(gap) > 0.3 else
            "large" if gap and abs(gap) > 0.15 else
            "moderate" if gap and abs(gap) > 0.05 else
            "negligible" if gap is not None else "unknown"
        ),
    }


# ── #85 Mech Interp Validation ────────────────────────────────────────────────

class MechInterpRequest(BaseModel):
    model_id: int
    benchmark_id: int
    n_samples: int = 10


@router.post("/mech-interp/validate")
async def run_mech_interp_validation(
    payload: MechInterpRequest,
    session: Session = Depends(get_session),
):
    """
    Run mechanistic interpretability validation on behavioural evaluation results.

    Tests:
      1. Chain-of-thought consistency — does stated reasoning match output?
      2. Paraphrase invariance — same question, different wording → same answer?
      3. Confidence calibration — does expressed confidence correlate with accuracy?

    Returns a confidence_adjustment (-0.3 to +0.3) to apply to behavioural scores,
    and a validation_signal (supports | neutral | undermines).

    Reference: INESIA PDF Priority 6 · Neel Nanda, Google DeepMind (2025)
    Black-box only — no model internals required.
    """
    model = session.get(LLMModel, payload.model_id)
    if not model:
        raise HTTPException(404, "Model not found.")
    benchmark = session.get(Benchmark, payload.benchmark_id)
    if not benchmark:
        raise HTTPException(404, "Benchmark not found.")

    questions = _get_questions(benchmark, payload.n_samples, session)
    if not questions:
        raise HTTPException(422, "No questions available. Run an evaluation campaign first.")

    validator = MechInterpValidator(adapter_factory=get_adapter)
    try:
        report = await asyncio.wait_for(
            validator.run(model=model, benchmark_name=benchmark.name,
                          questions=questions, n_samples=payload.n_samples),
            timeout=300.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(408, "Validation timed out. Reduce n_samples.")

    return {
        "model_name": report.model_name,
        "benchmark_name": report.benchmark_name,
        "n_probes": report.n_probes,
        "validation": {
            "signal": report.validation_signal,
            "confidence_adjustment": report.confidence_adjustment,
            "interpretation": report.interpretation,
        },
        "cot_analysis": {
            "consistency_rate": report.cot_consistency_rate,
            "answer_mismatch_rate": report.cot_answer_mismatch_rate,
            "probes": [
                {
                    "question": r.question,
                    "cot_consistent": r.cot_consistent,
                    "cot_answer_mismatch": r.cot_answer_mismatch,
                    "reasoning_quality": r.reasoning_quality,
                    "consistency_score": r.consistency_score,
                }
                for r in report.cot_results[:5]  # Sample for response size
            ],
        },
        "paraphrase_invariance": {
            "invariance_rate": report.paraphrase_invariance_rate,
            "probes": [
                {
                    "original": r.original_question[:100],
                    "agreement_rate": r.agreement_rate,
                    "invariant": r.invariant,
                }
                for r in report.paraphrase_results[:5]
            ],
        },
        "calibration": {
            "stated_confidence_accuracy": report.stated_confidence_accuracy,
            "overconfidence_rate": report.overconfidence_rate,
        },
        "limitations": report.limitations,
        "references": report.references,
        "performance": {
            "total_tokens": report.total_tokens,
            "total_cost_usd": report.total_cost_usd,
        },
    }


# ── #82 Benchmark Validity & Contamination ────────────────────────────────────

@router.get("/contamination/run/{run_id}")
def analyze_run_contamination(run_id: int, session: Session = Depends(get_session)):
    """
    Analyse one EvalRun for benchmark contamination signals.

    Detects: n-gram overlap, verbatim reproduction, confidence anomaly,
    first-token probability (MCQ benchmarks).

    Reference: INESIA PDF Priority 5 — dynamically generated expert-validated benchmarks.
    """
    run = session.get(EvalRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found.")
    bench = session.get(Benchmark, run.benchmark_id)
    if not bench:
        raise HTTPException(404, "Benchmark not found.")

    results = session.exec(
        select(EvalResult).where(EvalResult.run_id == run_id).limit(100)
    ).all()

    items = [{"prompt": r.prompt, "response": r.response,
              "expected": r.expected, "score": r.score} for r in results]
    analysis = analyze_contamination(items, benchmark_name=bench.name,
                                     benchmark_type=str(bench.type))
    return {
        "run_id": run_id,
        "benchmark_name": bench.name,
        "benchmark_type": str(bench.type),
        **analysis,
        "references": [
            "INESIA PDF Priority 5 — benchmark validity and contamination crisis",
            "Carlini et al. (2021) — Extracting Training Data from Large Language Models",
            "Golchin & Surdeanu (2023) — Time Travel in LLMs: Tracing Data Contamination",
        ],
    }


@router.get("/contamination/campaign/{campaign_id}")
def analyze_campaign_contamination(
    campaign_id: int,
    session: Session = Depends(get_session),
):
    """
    Cross-model contamination analysis for a full campaign.
    Aggregates run-level contamination scores and flags suspicious patterns.
    """
    from core.models import Campaign
    campaign = session.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found.")

    runs = session.exec(
        select(EvalRun).where(
            EvalRun.campaign_id == campaign_id,
            EvalRun.status == JobStatus.COMPLETED,
        )
    ).all()

    model_cache = {}
    bench_cache = {}
    results_by_key = {}

    for run in runs:
        if run.model_id not in model_cache:
            m = session.get(LLMModel, run.model_id)
            model_cache[run.model_id] = m.name if m else f"Model {run.model_id}"
        if run.benchmark_id not in bench_cache:
            b = session.get(Benchmark, run.benchmark_id)
            bench_cache[run.benchmark_id] = (b.name if b else f"Bench {run.benchmark_id}", str(b.type) if b else "custom")

        items = session.exec(
            select(EvalResult).where(EvalResult.run_id == run.id).limit(50)
        ).all()
        item_dicts = [{"prompt": r.prompt, "response": r.response,
                       "expected": r.expected, "score": r.score} for r in items]

        bench_name, bench_type = bench_cache[run.benchmark_id]
        analysis = analyze_contamination(item_dicts, benchmark_name=bench_name,
                                         benchmark_type=bench_type)
        key = f"{model_cache[run.model_id]} × {bench_name}"
        results_by_key[key] = {**analysis, "run_id": run.id,
                                "model": model_cache[run.model_id], "benchmark": bench_name}

    all_scores = [v["contamination_score"] for v in results_by_key.values()]
    overall = round(sum(all_scores) / max(len(all_scores), 1), 3)
    high_risk = [k for k, v in results_by_key.items() if v["risk"] in ("high", "medium")]

    return {
        "campaign_id": campaign_id,
        "campaign_name": campaign.name,
        "results": results_by_key,
        "summary": {
            "overall_contamination_score": overall,
            "overall_risk": "high" if overall > 0.4 else "medium" if overall > 0.15 else "low",
            "high_risk_pairs": high_risk,
            "n_analyzed": len(results_by_key),
        },
        "recommendation": (
            "HIGH CONTAMINATION RISK: Results may reflect memorisation, not genuine capability. "
            "Use dynamically-generated, expert-validated benchmarks (INESIA PDF Priority 5)."
            if overall > 0.4 else
            "Contamination risk is low. Standard interpretation applies."
        ),
        "references": [
            "INESIA PDF Priority 5 — dynamically generated benchmarks produced at evaluation time",
            "Carlini et al. (2021, 2022, 2023) — training data extraction and contamination",
        ],
    }


@router.get("/validity/benchmark/{benchmark_id}")
def check_benchmark_validity(
    benchmark_id: int,
    session: Session = Depends(get_session),
):
    """
    Benchmark validity assessment — structural analysis without running new evals.

    Checks: sample size adequacy, metric quality, dataset availability,
    known contamination risk (public vs private), eval dimension classification.

    Reference: INESIA PDF Priority 5 — evaluator reliability.
    """
    bench = session.get(Benchmark, benchmark_id)
    if not bench:
        raise HTTPException(404, "Benchmark not found.")

    issues = []
    warnings = []
    score = 1.0

    # Sample size
    n = bench.num_samples or 0
    if n < 20:
        issues.append(f"Sample size ({n}) below minimum threshold of 20. Statistical power insufficient.")
        score -= 0.3
    elif n < 50:
        warnings.append(f"Sample size ({n}) is small. Results will have wide confidence intervals.")
        score -= 0.1

    # Dataset availability
    if not bench.dataset_path:
        warnings.append("No dataset file linked — evaluation may use generated questions without reproducibility guarantees.")
        score -= 0.1
    else:
        from pathlib import Path
        full_path = Path(settings.bench_library_path) / bench.dataset_path
        if not full_path.exists():
            issues.append(f"Dataset file not found at {bench.dataset_path}.")
            score -= 0.2

    # Contamination risk from source
    source = getattr(bench, "source", "public")
    if source == "public":
        warnings.append(
            "Public benchmark — high contamination risk. "
            "Frontier models are likely trained on this data. "
            "Results may reflect memorisation."
        )
        score -= 0.15

    # Metric quality
    metric = bench.metric or "accuracy"
    if metric == "accuracy" and str(bench.type) == "safety":
        warnings.append(
            "Safety benchmarks should use nuanced metrics beyond binary accuracy. "
            "Consider harm probability scoring or expert panel annotation."
        )
        score -= 0.05

    # Eval dimension
    eval_dim = getattr(bench, "eval_dimension", "capability")
    if eval_dim not in ("capability", "propensity", "safety", "agentic"):
        warnings.append(f"Unrecognised eval_dimension '{eval_dim}'. Should be capability|propensity|safety|agentic.")

    validity_grade = "A" if score >= 0.85 else "B" if score >= 0.7 else "C" if score >= 0.5 else "D"

    return {
        "benchmark_id": benchmark_id,
        "benchmark_name": bench.name,
        "benchmark_type": str(bench.type),
        "eval_dimension": eval_dim,
        "source": source,
        "validity_score": round(max(0.0, score), 3),
        "validity_grade": validity_grade,
        "issues": issues,
        "warnings": warnings,
        "metadata": {
            "num_samples": n,
            "metric": metric,
            "has_dataset": bool(bench.dataset_path),
            "is_builtin": bench.is_builtin,
        },
        "recommendation": (
            "This benchmark is not suitable for capability claims."
            if issues else
            "This benchmark is usable with the noted caveats."
            if warnings else
            "This benchmark passes validity checks."
        ),
        "references": [
            "INESIA PDF Priority 5 — Bayesian GLMs for evaluator reliability",
            "INESIA PDF Priority 5 — dynamically generated, expert-validated, adversarially designed benchmarks",
        ],
    }


# ── #113 Compositional Risk Modeling ─────────────────────────────────────────

class CompositionalRiskRequest(BaseModel):
    model_name: str
    domain_scores: dict = {}       # capability scores per domain
    propensity_scores: dict = {}   # propensity scores per domain
    autonomy_level: str = "L2"
    tools: list[str] = []
    memory_type: str = "session"


@router.post("/compositional-risk")
def compute_compositional_risk(payload: CompositionalRiskRequest):
    """
    Compute system-level threat profile from individual capability/propensity scores.

    Risks compose multiplicatively — moderate capabilities across multiple
    dangerous domains can produce critical system-level risk.

    Reference: INESIA PDF Priority 3 — compositional and emergent risk.
    """
    from eval_engine.compositional_risk import CompositionalRiskEngine
    engine = CompositionalRiskEngine()
    profile = engine.compute(
        model_name=payload.model_name,
        domain_scores=payload.domain_scores,
        propensity_scores=payload.propensity_scores,
        autonomy_level=payload.autonomy_level,
        tools=payload.tools,
        memory_type=payload.memory_type,
    )
    return {
        "model_name": profile.model_name,
        "autonomy_level": profile.autonomy_level,
        "tools": profile.tools,
        "memory_type": profile.memory_type,
        "scores": {
            "baseline_risk": profile.baseline_risk,
            "autonomy_multiplier": profile.autonomy_multiplier,
            "tool_multiplier": profile.tool_multiplier,
            "memory_multiplier": profile.memory_multiplier,
            "combo_multiplier": profile.combo_multiplier,
            "composite_risk_score": profile.composite_risk_score,
        },
        "verdict": {
            "risk_level": profile.risk_level,
            "dominant_threat_vector": profile.dominant_threat_vector,
            "autonomy_recommendation": profile.autonomy_recommendation,
        },
        "domain_breakdown": [
            {"domain": r.domain, "raw_score": r.raw_score,
             "severity_weight": r.severity_weight, "weighted_risk": r.weighted_risk,
             "interpretation": r.interpretation}
            for r in profile.domain_risks
        ],
        "dangerous_combinations": [
            {"domains": c.domains, "multiplier": c.multiplier, "reason": c.reason}
            for c in profile.dangerous_combos_triggered
        ],
        "key_concerns": profile.key_concerns,
        "mitigation_priorities": profile.mitigation_priorities,
        "caveat": profile.caveat,
        "references": [
            "INESIA PDF Priority 3 — Compositional and emergent risk",
            "AgentDojo (Debenedetti et al., 2024) — compositional agentic risk",
            "NIST AI 800-4 — system-level risk assessment",
        ],
    }


@router.get("/compositional-risk/domains")
def get_risk_domains():
    """List all supported risk domains and their severity weights."""
    from eval_engine.compositional_risk import DOMAIN_SEVERITY, AUTONOMY_MULTIPLIER, TOOL_MULTIPLIER, MEMORY_MULTIPLIER
    return {
        "domains": DOMAIN_SEVERITY,
        "autonomy_multipliers": AUTONOMY_MULTIPLIER,
        "tool_multipliers": TOOL_MULTIPLIER,
        "memory_multipliers": MEMORY_MULTIPLIER,
    }


# ── #114 Failure Clustering ───────────────────────────────────────────────────

@router.get("/failure-clusters/campaign/{campaign_id}")
def get_failure_clusters(
    campaign_id: int,
    min_cluster_size: int = 2,
    similarity_threshold: float = 0.3,
    session: Session = Depends(get_session),
):
    """
    Cluster failure traces from a campaign and detect novel failure patterns.

    Uses TF-IDF + cosine similarity (no LLM required).
    Novel clusters = patterns not in existing failure taxonomy.

    Reference: INESIA Research OS — failure clustering for scientific discovery.
    """
    from eval_engine.failure_clustering import FailureClusteringEngine
    from core.models import EvalResult

    # Load failures (scored items below 0.5)
    results = session.exec(
        select(EvalResult).join(
            EvalRun, EvalResult.run_id == EvalRun.id
        ).where(
            EvalRun.campaign_id == campaign_id,
            EvalResult.score < 0.5,
        ).limit(500)
    ).all()

    if not results:
        raise HTTPException(422, "No failure results found for this campaign.")

    # Enrich with model names
    model_cache = {}
    failures = []
    for r in results:
        run = session.get(EvalRun, r.run_id)
        if run and run.model_id not in model_cache:
            m = session.get(LLMModel, run.model_id)
            model_cache[run.model_id] = m.name if m else str(run.model_id)
        failures.append({
            "prompt": r.prompt or "",
            "response": r.response or "",
            "score": r.score,
            "model_name": model_cache.get(run.model_id if run else 0, "unknown"),
            "category": "",
        })

    engine = FailureClusteringEngine(
        similarity_threshold=similarity_threshold,
        min_cluster_size=min_cluster_size,
    )
    report = engine.discover(failures, campaign_id=campaign_id)

    return {
        "campaign_id": report.campaign_id,
        "n_failures_analysed": report.n_failures,
        "n_clusters": report.n_clusters,
        "summary": report.summary,
        "novel_clusters": [
            {
                "cluster_id": c.cluster_id,
                "size": c.size,
                "failure_family": c.failure_family,
                "is_novel": c.is_novel,
                "reproducibility_score": c.reproducibility_score,
                "cross_model": c.cross_model,
                "affected_models": c.affected_models,
                "common_keywords": c.common_keywords,
                "causal_hypothesis": c.causal_hypothesis,
                "recommended_benchmark": c.recommended_benchmark,
                "representative_prompts": c.representative_prompts,
            }
            for c in report.novel_clusters
        ],
        "known_clusters": [
            {
                "cluster_id": c.cluster_id,
                "size": c.size,
                "failure_family": c.failure_family,
                "common_keywords": c.common_keywords,
                "causal_hypothesis": c.causal_hypothesis,
            }
            for c in report.known_clusters
        ],
        "cross_model_patterns": report.cross_model_patterns,
        "top_emerging_risk": report.top_emerging_risk,
    }
