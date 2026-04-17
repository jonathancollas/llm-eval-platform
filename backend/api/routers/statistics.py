from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from sqlmodel import Session, select
from core.database import get_session
from core.models import EvalRun, EvalResult
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

    result = compute_confidence(scores)
    return result.__dict__
