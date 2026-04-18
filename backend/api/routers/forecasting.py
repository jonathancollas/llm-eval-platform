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
from eval_engine.frontier_metrics import FrontierMetricsEngine, MetricCorrelations

router = APIRouter(prefix="/forecasting", tags=["forecasting"])
_metrics_engine = FrontierMetricsEngine()

from eval_engine.long_horizon import LongHorizonEvaluator, LONG_HORIZON_TASKS
_lh_evaluator = LongHorizonEvaluator()

# ── In-memory frontier metrics leaderboard ────────────────────────────────────
# Maps model_name -> list of leaderboard entries (supports trend over versions)
_frontier_leaderboard: dict[str, list[dict]] = {}


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
    version: Optional[str] = None


def _result_to_dict(result) -> dict:
    """Serialize a FrontierMetricsResult to a JSON-safe dict."""
    def _ci(ci):
        if ci is None:
            return None
        return {"lower": ci.lower, "upper": ci.upper, "level": ci.level}

    return {
        "model_name": result.model_name,
        "composite_frontier_score": result.composite_frontier_score,
        "frontier_grade": result.frontier_grade,
        "frontier_grade_interpretation": result.frontier_grade_interpretation,
        "autonomy": {
            "value": result.autonomy.value,
            "grade": result.autonomy.grade,
            "interpretation": result.autonomy.interpretation,
            "n_steps": result.autonomy.n_steps,
            "n_error_steps": result.autonomy.n_error_steps,
            "n_retry_steps": result.autonomy.n_retry_steps,
            "ci": _ci(result.autonomy.ci),
        },
        "adaptivity": {
            "value": result.adaptivity.value,
            "grade": result.adaptivity.grade,
            "interpretation": result.adaptivity.interpretation,
            "n_error_episodes": result.adaptivity.n_error_episodes,
            "n_successful_recoveries": result.adaptivity.n_successful_recoveries,
            "mean_recovery_time_steps": result.adaptivity.mean_recovery_time_steps,
            "ci": _ci(result.adaptivity.ci),
        },
        "efficiency": {
            "value": result.efficiency.value,
            "grade": result.efficiency.grade,
            "interpretation": result.efficiency.interpretation,
            "tokens_per_step": result.efficiency.tokens_per_step,
            "steps_to_completion": result.efficiency.steps_to_completion,
            "max_steps": result.efficiency.max_steps,
            "step_efficiency": result.efficiency.step_efficiency,
            "ci": _ci(result.efficiency.ci),
        },
        "generalization": {
            "value": result.generalization.value,
            "grade": result.generalization.grade,
            "interpretation": result.generalization.interpretation,
            "benchmarks_evaluated": result.generalization.benchmarks_evaluated,
            "score_variance": result.generalization.score_variance,
            "worst_score": result.generalization.worst_score,
            "best_score": result.generalization.best_score,
            "coefficient_of_variation": result.generalization.coefficient_of_variation,
            "ci": _ci(result.generalization.ci),
        },
        "capability_breakdown": [
            {
                "capability": cb.capability,
                "autonomy": cb.autonomy,
                "adaptivity": cb.adaptivity,
                "efficiency": cb.efficiency,
                "composite": cb.composite,
                "n_steps": cb.n_steps,
            }
            for cb in result.capability_breakdown
        ],
        "three_axis_summary": result.three_axis_summary,
        "capability_score": result.capability_score,
        "propensity_score": result.propensity_score,
        "safety_score": result.safety_score,
        "created_at": result.created_at,
    }


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
    payload = _result_to_dict(result)
    # Also persist to the in-memory leaderboard
    entry = {
        **payload,
        "version": req.version or req.model_name,
    }
    _frontier_leaderboard.setdefault(req.model_name, []).append(entry)
    return payload


@router.get("/metrics/leaderboard")
def get_frontier_leaderboard():
    """Return the latest frontier metrics entry per model, ranked by composite score."""
    rows = []
    for model_name, entries in _frontier_leaderboard.items():
        latest = entries[-1]
        rows.append({
            "model_name": model_name,
            "composite_frontier_score": latest["composite_frontier_score"],
            "frontier_grade": latest["frontier_grade"],
            "autonomy": latest["autonomy"]["value"],
            "adaptivity": latest["adaptivity"]["value"],
            "efficiency": latest["efficiency"]["value"],
            "generalization": latest["generalization"]["value"],
            "frontier_grade_interpretation": latest["frontier_grade_interpretation"],
            "version_count": len(entries),
            "created_at": latest["created_at"],
        })
    rows.sort(key=lambda r: r["composite_frontier_score"], reverse=True)
    for i, row in enumerate(rows):
        row["rank"] = i + 1
    return {"rows": rows, "total": len(rows)}


@router.get("/metrics/leaderboard/trend/{model_name}")
def get_model_trend(model_name: str):
    """Return all historical frontier metric entries for a model (for trend chart)."""
    entries = _frontier_leaderboard.get(model_name)
    if not entries:
        raise HTTPException(404, f"No metrics found for model '{model_name}'")
    trend = [
        {
            "version": e.get("version", e["model_name"]),
            "composite_frontier_score": e["composite_frontier_score"],
            "autonomy": e["autonomy"]["value"],
            "adaptivity": e["adaptivity"]["value"],
            "efficiency": e["efficiency"]["value"],
            "generalization": e["generalization"]["value"],
            "created_at": e["created_at"],
        }
        for e in entries
    ]
    return {"model_name": model_name, "trend": trend}


@router.post("/metrics/correlations")
def compute_metric_correlations(results: List[dict]):
    """
    Compute pairwise Pearson correlations between the 4 frontier metrics
    given a list of previously computed result payloads.
    """
    if len(results) < 2:
        raise HTTPException(400, "Need at least 2 result entries to compute correlations")

    from eval_engine.frontier_metrics import (
        FrontierMetricsResult, AutonomyScore, AdaptivityScore,
        EfficiencyScore, GeneralizationScore,
    )

    def _mock_score(sub: dict, cls):
        # Build a minimal score object from the serialised dict
        return cls(**{k: v for k, v in sub.items() if k != "ci"})

    parsed = []
    for r in results:
        try:
            parsed.append(FrontierMetricsResult(
                model_name=r["model_name"],
                autonomy=_mock_score(r["autonomy"], AutonomyScore),
                adaptivity=_mock_score(r["adaptivity"], AdaptivityScore),
                efficiency=_mock_score(r["efficiency"], EfficiencyScore),
                generalization=_mock_score(r["generalization"], GeneralizationScore),
                composite_frontier_score=r["composite_frontier_score"],
                frontier_grade=r.get("frontier_grade", ""),
                frontier_grade_interpretation=r.get("frontier_grade_interpretation", ""),
                capability_score=r.get("capability_score", 0.0),
                propensity_score=r.get("propensity_score", 0.0),
                safety_score=r.get("safety_score", 0.0),
                three_axis_summary=r.get("three_axis_summary", {}),
            ))
        except Exception:
            raise HTTPException(422, "Invalid result payload structure")

    corr: MetricCorrelations = _metrics_engine.compute_correlations(parsed)
    return {
        "autonomy_adaptivity": corr.autonomy_adaptivity,
        "autonomy_efficiency": corr.autonomy_efficiency,
        "autonomy_generalization": corr.autonomy_generalization,
        "adaptivity_efficiency": corr.adaptivity_efficiency,
        "adaptivity_generalization": corr.adaptivity_generalization,
        "efficiency_generalization": corr.efficiency_generalization,
        "interpretation": corr.interpretation,
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
