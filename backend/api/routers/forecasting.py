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
    fit_chinchilla,
    validate_data_quality,
    MultiDimScalingFit,
    ForecastCalibrationRecord,
)
from eval_engine.frontier_metrics import FrontierMetricsEngine
from eval_engine.long_horizon import LongHorizonEvaluator, LONG_HORIZON_TASKS

router = APIRouter(prefix="/forecasting", tags=["forecasting"])
_metrics_engine = FrontierMetricsEngine()
_lh_evaluator = LongHorizonEvaluator()

# ── In-memory calibration store (per-capability) ──────────────────────────────
# Maps capability -> list of ForecastCalibrationRecord
_calibration_store: dict[str, list[dict]] = {}


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
        "rmse": fit.rmse,
        "mae": fit.mae,
        "valid": fit.valid,
        "interpretation": fit.interpretation,
        "residuals": fit.residuals,
    }


class ChinchillaFitRequest(BaseModel):
    data_points: List[dict]  # each has: parameter_count, training_tokens, score


@router.post("/fit/chinchilla")
def fit_chinchilla_law(req: ChinchillaFitRequest):
    """Fit a Chinchilla-style multi-dimensional power law (compute + parameters)."""
    if len(req.data_points) < 4:
        raise HTTPException(400, "Need at least 4 data points for Chinchilla fitting")
    param_counts = [float(d["parameter_count"]) for d in req.data_points]
    token_counts = [float(d["training_tokens"]) for d in req.data_points]
    scores = [float(d["score"]) for d in req.data_points]
    fit = fit_chinchilla(param_counts, token_counts, scores)
    return {
        "alpha": fit.alpha,
        "beta": fit.beta,
        "A": fit.A,
        "B": fit.B,
        "r_squared": fit.r_squared,
        "rmse": fit.rmse,
        "n_points": fit.n_points,
        "valid": fit.valid,
        "interpretation": fit.interpretation,
    }


class AggregateRequest(BaseModel):
    data_points: List[dict]
    validate: bool = True


@router.post("/aggregate")
def aggregate_historical_data(req: AggregateRequest):
    """Aggregate and validate a batch of historical evaluation data points."""
    points = []
    for dp in req.data_points:
        points.append(
            ScalingDataPoint(
                model_name=dp.get("model_name", "unknown"),
                benchmark_name=dp.get("benchmark_name", "unknown"),
                capability=dp.get("capability", "general"),
                score=float(dp["score"]),
                ci_lower=float(dp.get("ci_lower", 0.0)),
                ci_upper=float(dp.get("ci_upper", 1.0)),
                parameter_count=dp.get("parameter_count"),
                training_tokens=dp.get("training_tokens"),
                compute_flops=dp.get("compute_flops"),
                score_type=dp.get("score_type", "capability"),
                date=dp.get("date", "2024-01-01"),
            )
        )

    quality = validate_data_quality(points) if req.validate else None

    return {
        "total_received": len(points),
        "capabilities": list({p.capability for p in points}),
        "benchmarks": list({p.benchmark_name for p in points}),
        "date_range": {
            "earliest": min(p.date for p in points) if points else None,
            "latest": max(p.date for p in points) if points else None,
        },
        "quality_report": {
            "total_points": quality.total_points,
            "valid_points": quality.valid_points,
            "invalid_points": quality.invalid_points,
            "duplicate_count": quality.duplicate_count,
            "missing_ci_count": quality.missing_ci_count,
            "score_range_violations": quality.score_range_violations,
            "issues": quality.issues,
            "passed": quality.passed,
        } if quality else None,
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
                score_type=dp.get("score_type", "capability"),
                date=dp.get("date", "2024-01-01"),
            )
        )
    forecast = engine.forecast(req.capability, req.horizon_steps)
    return {
        "capability": forecast.capability,
        "current_score": forecast.current_score,
        "forecast_score": forecast.forecast_score,
        "uncertainty_lower": forecast.uncertainty_lower,
        "uncertainty_upper": forecast.uncertainty_upper,
        "trend_direction": forecast.trend_direction,
        "confidence": forecast.confidence,
        "scaling_law_type": forecast.scaling_law_type,
        "capability_score": forecast.capability_score,
        "propensity_score": forecast.propensity_score,
        "gap_to_frontier": forecast.gap_to_frontier,
        "forecast_horizon_label": forecast.forecast_horizon_label,
        "key_assumptions": forecast.key_assumptions,
    }


class ReportRequest(BaseModel):
    data_points: List[dict]
    capabilities: Optional[List[str]] = None


@router.post("/report")
def generate_forecast_report(req: ReportRequest):
    """Generate a full forecast report across all capabilities."""
    engine = CapabilityForecastingEngine()
    for dp in req.data_points:
        engine.add_data_point(
            ScalingDataPoint(
                model_name=dp.get("model_name", "unknown"),
                benchmark_name=dp.get("benchmark_name", "unknown"),
                capability=dp.get("capability", "general"),
                score=float(dp["score"]),
                score_type=dp.get("score_type", "capability"),
                date=dp.get("date", "2024-01-01"),
            )
        )
    report = engine.generate_report(req.capabilities)

    def _serialize_forecast(f):
        return {
            "capability": f.capability,
            "current_score": f.current_score,
            "forecast_score": f.forecast_score,
            "uncertainty_lower": f.uncertainty_lower,
            "uncertainty_upper": f.uncertainty_upper,
            "trend_direction": f.trend_direction,
            "confidence": f.confidence,
            "scaling_law_type": f.scaling_law_type,
            "capability_score": f.capability_score,
            "propensity_score": f.propensity_score,
            "gap_to_frontier": f.gap_to_frontier,
            "forecast_horizon_label": f.forecast_horizon_label,
        }

    return {
        "benchmarks_analyzed": report.benchmarks_analyzed,
        "capabilities_covered": report.capabilities_covered,
        "forecasts": [_serialize_forecast(f) for f in report.forecasts],
        "overall_trend": report.overall_trend,
        "riskiest_capability": report.riskiest_capability,
        "plateau_capabilities": report.plateau_capabilities,
        "emerging_capabilities": report.emerging_capabilities,
        "recommendations": report.recommendations,
        "frontier_gaps": report.frontier_gaps,
        "calibration_mae": report.calibration_mae,
        "created_at": report.created_at,
    }


class ResidualRequest(BaseModel):
    data_points: List[dict]
    capability: str
    method: str = "auto"


@router.post("/scaling/residuals")
def get_residual_analysis(req: ResidualRequest):
    """Compute residual analysis / goodness-of-fit diagnostics for a capability."""
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
    return engine.residual_analysis(req.capability, req.method)


class GapRequest(BaseModel):
    data_points: List[dict]
    capabilities: Optional[List[str]] = None


@router.post("/gaps/frontier")
def compute_frontier_gaps(req: GapRequest):
    """Compute 'capability gap to frontier' metric for each capability."""
    engine = CapabilityForecastingEngine()
    for dp in req.data_points:
        engine.add_data_point(
            ScalingDataPoint(
                model_name=dp.get("model_name", "unknown"),
                benchmark_name=dp.get("benchmark_name", "unknown"),
                capability=dp.get("capability", "general"),
                score=float(dp["score"]),
                date=dp.get("date", "2024-01-01"),
            )
        )
    gaps = engine.capability_gap_to_frontier(req.capabilities)
    return {
        "gaps": gaps,
        "worst_capability": max(gaps, key=lambda k: gaps[k]) if gaps else None,
        "best_capability": min(gaps, key=lambda k: gaps[k]) if gaps else None,
    }


class CalibrationRecordRequest(BaseModel):
    capability: str
    predicted_score: float
    actual_score: float
    horizon_label: str = "unknown"


@router.post("/calibration/record")
def record_calibration(req: CalibrationRecordRequest):
    """Record a historical forecast prediction vs actual outcome."""
    record = {
        "capability": req.capability,
        "predicted_score": round(req.predicted_score, 4),
        "actual_score": round(req.actual_score, 4),
        "absolute_error": round(abs(req.predicted_score - req.actual_score), 4),
        "horizon_label": req.horizon_label,
        "recorded_at": __import__("datetime").datetime.utcnow().isoformat(),
    }
    _calibration_store.setdefault(req.capability, []).append(record)
    return record


@router.get("/calibration")
def get_calibration_history(capability: Optional[str] = None):
    """Retrieve forecast calibration history (how accurate were past forecasts?)."""
    if capability:
        records = _calibration_store.get(capability, [])
    else:
        records = [r for recs in _calibration_store.values() for r in recs]

    if not records:
        return {"records": [], "overall_mae": 0.0, "by_capability": {}}

    overall_mae = round(sum(r["absolute_error"] for r in records) / len(records), 4)
    by_cap: dict[str, dict] = {}
    for r in records:
        cap = r["capability"]
        if cap not in by_cap:
            by_cap[cap] = {"count": 0, "total_error": 0.0}
        by_cap[cap]["count"] += 1
        by_cap[cap]["total_error"] += r["absolute_error"]

    return {
        "records": records,
        "overall_mae": overall_mae,
        "by_capability": {
            cap: {"count": v["count"], "mae": round(v["total_error"] / v["count"], 4)}
            for cap, v in by_cap.items()
        },
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
