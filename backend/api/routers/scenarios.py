from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from sqlmodel import Session, select
from core.database import get_session
from core.models import JudgeEvaluation
from eval_engine.scenario_runtime import (
    EXAMPLE_SCENARIOS, ScenarioRuntime, load_scenario, validate_scenario,
    evaluate_step, ScenarioStep,
)
from eval_engine.judge_bias import pearson_correlation

router = APIRouter(prefix="/scenarios", tags=["scenarios"])
_runtime = ScenarioRuntime()


@router.get("/examples")
def get_examples():
    return EXAMPLE_SCENARIOS


@router.post("/validate")
def validate(req: dict):
    try:
        s = load_scenario(req)
        errors = validate_scenario(s)
        return {"valid": len(errors) == 0, "errors": errors}
    except Exception as e:
        return {"valid": False, "errors": [str(e)]}


class SimulateRequest(BaseModel):
    scenario: dict
    responses: List[dict]
    model_name: str = "test"


@router.post("/simulate")
def simulate(req: SimulateRequest):
    scenario = load_scenario(req.scenario)
    result = _runtime.simulate_run(scenario, req.responses, req.model_name)
    return {
        "scenario_name": result.scenario_name,
        "completion_rate": result.completion_rate,
        "partial_credit_score": result.partial_credit_score,
        "overall_success": result.overall_success,
        "failure_modes": result.failure_modes,
    }


class StepEvalRequest(BaseModel):
    step: dict
    response: dict
    state: dict = {}


@router.post("/evaluate-step")
def evaluate_step_endpoint(req: StepEvalRequest):
    step = ScenarioStep(**req.step)
    success, credit = evaluate_step(step, req.response, req.state)
    return {"success": success, "credit": credit}


@router.get("/bias/report/{campaign_id}")
def bias_report(campaign_id: int, session: Session = Depends(get_session)):
    evals = session.exec(
        select(JudgeEvaluation).where(JudgeEvaluation.campaign_id == campaign_id)
    ).all()
    by_judge: dict = {}
    for e in evals:
        by_judge.setdefault(e.judge_model, []).append(e)
    judges_out = []
    for judge_model, judge_evals in by_judge.items():
        judge_scores = [e.judge_score for e in judge_evals if e.judge_score is not None]
        oracle_scores = [
            e.oracle_score for e in judge_evals
            if hasattr(e, "oracle_score") and e.oracle_score is not None
        ]
        agreement = (
            pearson_correlation(judge_scores, oracle_scores)
            if len(judge_scores) == len(oracle_scores) and oracle_scores
            else None
        )
        judges_out.append({
            "judge_model": judge_model,
            "n_evaluations": len(judge_evals),
            "mean_score": round(sum(judge_scores) / len(judge_scores), 4) if judge_scores else 0.0,
            "human_agreement": agreement,
        })
    return {"campaign_id": campaign_id, "judges": judges_out}
