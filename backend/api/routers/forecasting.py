from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from sqlmodel import Session, select
from core.database import get_session
from core.models import AgentTrajectory
from eval_engine.capability_forecasting import (
    CapabilityForecastingEngine,
    ScalingDataPoint,
    fit_linear,
    fit_power_law,
    fit_logistic,
)
from eval_engine.frontier_metrics import FrontierMetricsEngine
from eval_engine.long_horizon import LongHorizonEvaluator, LONG_HORIZON_TASKS

router = APIRouter(prefix="/forecasting", tags=["forecasting"])
_metrics_engine = FrontierMetricsEngine()
_lh_evaluator = LongHorizonEvaluator()


@router.get("/capabilities")
def list_capabilities():
    return [
        "cybersecurity",
        "reasoning",
        "instruction_following",
        "knowledge",
        "agentic",
        "safety",
        "multimodal",
    ]


class FitRequest(BaseModel):
    data_points: List[dict]
    method: str = "auto"


@router.post("/fit")
def fit_scaling_law(req: FitRequest):
    if len(req.data_points) < 2:
        raise HTTPException(400, "Need at least 2 data points")
    x = [float(d.get("x", i)) for i, d in enumerate(req.data_points)]
    y = [float(d["score"]) for d in req.data_points]
    if req.method == "linear":
        fit = fit_linear(x, y)
    elif req.method == "power":
        fit = fit_power_law(x, y)
    elif req.method == "logistic":
        fit = fit_logistic(x, y)
    else:
        fit = fit_linear(x, y)
    return {
        "law_type": fit.law_type,
        "coefficients": fit.coefficients,
        "r_squared": fit.r_squared,
        "valid": fit.valid,
    }


class ForecastRequest(BaseModel):
    data_points: List[dict]
    capability: str
    horizon_steps: int = 3


@router.post("/forecast")
def forecast_capability(req: ForecastRequest):
    engine = CapabilityForecastingEngine()
    for dp in req.data_points:
        engine.add_data_point(
            ScalingDataPoint(
                model_name=dp.get("model_name", "unknown"),
                benchmark_name=dp.get("benchmark_name", "unknown"),
                capability=req.capability,
                score=float(dp["score"]),
                date=dp.get("date", "2024-01-01"),
            )
        )
    forecast = engine.forecast(req.capability, req.horizon_steps)
    return {
        "capability": forecast.capability,
        "current_score": forecast.current_score,
        "forecast_score": forecast.forecast_score,
        "trend_direction": forecast.trend_direction,
        "confidence": forecast.confidence,
    }


@router.get("/long-horizon/tasks")
def list_long_horizon_tasks(domain: Optional[str] = None):
    if domain:
        return [t for t in LONG_HORIZON_TASKS if t["domain"] == domain]
    return LONG_HORIZON_TASKS


class LongHorizonSimRequest(BaseModel):
    task_id: str
    step_responses: List[dict]
    model_name: str = "test"


@router.post("/long-horizon/simulate")
def simulate_long_horizon(req: LongHorizonSimRequest):
    task_dict = next((t for t in LONG_HORIZON_TASKS if t["task_id"] == req.task_id), None)
    if not task_dict:
        raise HTTPException(404, f"Task '{req.task_id}' not found")
    task = _lh_evaluator.load_task(task_dict)
    result = _lh_evaluator.simulate_run(task, req.step_responses)
    return {
        "task_id": result.task_id,
        "completion_rate": result.completion_rate,
        "partial_credit_score": result.partial_credit_score,
        "main_goal_achieved": result.main_goal_achieved,
    }


class FrontierMetricsRequest(BaseModel):
    model_name: str
    steps: List[dict]
    benchmark_scores: dict
    capability_score: float
    propensity_score: float
    safety_score: float
    max_steps: int
    task_completed: bool


@router.post("/metrics/compute")
def compute_frontier_metrics(req: FrontierMetricsRequest):
    result = _metrics_engine.compute_all(
        req.model_name,
        req.steps,
        req.benchmark_scores,
        req.capability_score,
        req.propensity_score,
        req.safety_score,
        req.max_steps,
        req.task_completed,
    )
    return {
        "model_name": result.model_name,
        "composite_frontier_score": result.composite_frontier_score,
        "frontier_grade": result.frontier_grade,
        "autonomy": result.autonomy.value,
        "adaptivity": result.adaptivity.value,
        "efficiency": result.efficiency.value,
        "generalization": result.generalization.value,
    }


@router.get("/metrics/{run_id}")
def get_run_metrics(run_id: int, session: Session = Depends(get_session)):
    trajectories = session.exec(
        select(AgentTrajectory).where(AgentTrajectory.campaign_id == run_id)
    ).all()
    if not trajectories:
        raise HTTPException(404, f"No trajectories found for run {run_id}")
    return {
        "run_id": run_id,
        "n_trajectories": len(trajectories),
        "message": "Use POST /metrics/compute for full frontier metrics",
    }
