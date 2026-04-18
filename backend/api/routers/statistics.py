import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from sqlmodel import Session, select
from core.database import get_session
from core.models import EvalRun, EvalResult, LLMModel, Benchmark, Campaign
from eval_engine.statistical_tests import (
    mcnemar_test,
    permutation_test,
    bonferroni_correction,
    benjamini_hochberg_correction,
    cohens_d,
    power_analysis,
    compare_runs,
)
from eval_engine.human_calibration import AnnotationItem, compute_calibration_report
from eval_engine.reproducibility_engine import (
    generate_fingerprint,
    validate_reproducibility,
)

router = APIRouter(prefix="/statistics", tags=["statistics"])


class CompareRunsRequest(BaseModel):
    run_id_a: int
    run_id_b: int
    method: str = "both"


class PowerAnalysisRequest(BaseModel):
    effect_size: float
    alpha: float = 0.05
    power: float = 0.8


class CalibrationRequest(BaseModel):
    items: List[dict]
    llm_scores: dict


class ValidateReproducibilityRequest(BaseModel):
    run_id_a: int
    run_id_b: int


@router.post("/compare-runs")
def compare_runs_endpoint(
    req: CompareRunsRequest, session: Session = Depends(get_session)
):
    scores_a = [
        r.score
        for r in session.exec(
            select(EvalResult).where(EvalResult.run_id == req.run_id_a)
        ).all()
        if r.score is not None
    ]
    scores_b = [
        r.score
        for r in session.exec(
            select(EvalResult).where(EvalResult.run_id == req.run_id_b)
        ).all()
        if r.score is not None
    ]
    if not scores_a:
        raise HTTPException(404, f"No results for run {req.run_id_a}")
    if not scores_b:
        raise HTTPException(404, f"No results for run {req.run_id_b}")
    return compare_runs(scores_a, scores_b)


@router.post("/power-analysis")
def power_analysis_endpoint(req: PowerAnalysisRequest):
    return power_analysis(req.effect_size, req.alpha, req.power)


@router.post("/calibration")
def calibration_endpoint(req: CalibrationRequest):
    items = [
        AnnotationItem(
            item_id=it["item_id"],
            prompt=it.get("prompt", ""),
            response=it.get("response", ""),
            expected=it.get("expected", ""),
            scores=it["scores"],
        )
        for it in req.items
    ]
    report = compute_calibration_report(items, req.llm_scores)
    return report.__dict__


@router.get("/run/{run_id}/confidence")
def run_confidence(run_id: int, session: Session = Depends(get_session)):
    results = session.exec(
        select(EvalResult).where(EvalResult.run_id == run_id)
    ).all()
    if not results:
        raise HTTPException(404, "Run not found")
    scores = [r.score for r in results if r.score is not None]
    from eval_engine.confidence_engine import compute_confidence

    result = compute_confidence(run_id, scores)
    return result.__dict__


def _run_to_fingerprint_inputs(run: EvalRun, session: Session):
    """Extract the config inputs needed to generate a reproducibility fingerprint."""
    model = session.get(LLMModel, run.model_id)
    benchmark = session.get(Benchmark, run.benchmark_id)

    campaign_config = {
        "id": run.campaign_id,
        "model_id": run.model_id,
        "benchmark_id": run.benchmark_id,
        "judge_model": run.judge_model,
        "system_prompt_hash": run.system_prompt_hash,
        "dataset_version": run.dataset_version,
    }
    model_configs = (
        [{"id": model.id, "name": model.name, "provider": model.provider}]
        if model
        else []
    )
    benchmark_configs = (
        [
            {
                "id": benchmark.id,
                "name": benchmark.name,
                "dataset_path": benchmark.dataset_path,
                "metric": benchmark.metric,
                "num_samples": benchmark.num_samples,
            }
        ]
        if benchmark
        else []
    )

    run_ctx = json.loads(run.run_context_json or "{}")
    seed = run_ctx.get("seed", 42)
    temperature = run_ctx.get("temperature", 0.0)

    return campaign_config, model_configs, benchmark_configs, seed, temperature


@router.get("/run/{run_id}/fingerprint")
def run_fingerprint(run_id: int, session: Session = Depends(get_session)):
    """Generate a reproducibility fingerprint for an eval run.

    Returns a cryptographic hash of all inputs (config, model, benchmark, seed,
    temperature) that uniquely identifies the exact experimental conditions.
    """
    run = session.get(EvalRun, run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")

    campaign_config, model_configs, benchmark_configs, seed, temperature = (
        _run_to_fingerprint_inputs(run, session)
    )
    fp = generate_fingerprint(campaign_config, model_configs, benchmark_configs, seed, temperature)
    return {
        "run_id": run_id,
        "fingerprint_hash": fp.fingerprint_hash,
        "config_hash": fp.config_hash,
        "dataset_hash": fp.dataset_hash,
        "prompt_hash": fp.prompt_hash,
        "seed": fp.seed,
        "temperature": fp.temperature,
        "created_at": fp.created_at,
        "environment": {
            "python_version": fp.environment.python_version,
            "platform_os": fp.environment.platform_os,
            "platform_arch": fp.environment.platform_arch,
        },
    }


@router.post("/validate-reproducibility")
def validate_runs_reproducibility(
    req: ValidateReproducibilityRequest, session: Session = Depends(get_session)
):
    """Compare two eval runs to determine if they are reproducible (identical inputs)."""
    run_a = session.get(EvalRun, req.run_id_a)
    run_b = session.get(EvalRun, req.run_id_b)
    if not run_a:
        raise HTTPException(404, f"Run {req.run_id_a} not found")
    if not run_b:
        raise HTTPException(404, f"Run {req.run_id_b} not found")

    cfg_a, mc_a, bc_a, seed_a, temp_a = _run_to_fingerprint_inputs(run_a, session)
    cfg_b, mc_b, bc_b, seed_b, temp_b = _run_to_fingerprint_inputs(run_b, session)

    fp_a = generate_fingerprint(cfg_a, mc_a, bc_a, seed_a, temp_a)
    fp_b = generate_fingerprint(cfg_b, mc_b, bc_b, seed_b, temp_b)

    result = validate_reproducibility(fp_a, fp_b)
    return {
        "run_id_a": req.run_id_a,
        "run_id_b": req.run_id_b,
        "fingerprint_a": fp_a.fingerprint_hash,
        "fingerprint_b": fp_b.fingerprint_hash,
        **result,
    }
