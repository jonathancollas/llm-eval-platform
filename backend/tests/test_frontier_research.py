"""
Tests for Milestone 5 — Frontier Research:
capability_forecasting, frontier_metrics, long_horizon.
"""
import pytest

from eval_engine.capability_forecasting import (
    fit_linear,
    fit_power_law,
    fit_logistic,
    fit_chinchilla,
    validate_data_quality,
    extrapolate,
    detect_phase_transition,
    CapabilityForecastingEngine,
    ScalingDataPoint,
    CapabilityForecast,
    MultiDimScalingFit,
    DataQualityReport,
    ForecastCalibrationRecord,
)
from eval_engine.frontier_metrics import FrontierMetricsEngine, FrontierMetricsResult
from eval_engine.long_horizon import (
    LongHorizonEvaluator,
    LONG_HORIZON_TASKS,
    SubGoalResult,
)


# ---------------------------------------------------------------------------
# fit_linear
# ---------------------------------------------------------------------------

def test_fit_linear_coefficients():
    x = [0.0, 1.0, 2.0, 3.0, 4.0]
    y = [1.0, 3.0, 5.0, 7.0, 9.0]  # y = 2x + 1
    fit = fit_linear(x, y)
    assert fit.law_type == "linear"
    assert abs(fit.coefficients["a"] - 2.0) < 0.01
    assert abs(fit.coefficients["b"] - 1.0) < 0.01
    assert fit.r_squared > 0.99


def test_fit_linear_insufficient_data():
    fit = fit_linear([1.0], [1.0])
    assert fit.valid is False


# ---------------------------------------------------------------------------
# fit_power_law
# ---------------------------------------------------------------------------

def test_fit_power_law_valid():
    import math
    x = [1.0, 2.0, 4.0, 8.0, 16.0]
    y = [1.0, 2.0 ** 0.5, 2.0, 2.0 ** 1.5, 4.0]  # y ≈ x^0.5
    fit = fit_power_law(x, y)
    assert fit.law_type == "power"
    assert fit.valid is True
    assert fit.r_squared > 0.9


def test_fit_power_law_insufficient():
    fit = fit_power_law([1.0], [1.0])
    assert fit.valid is False


# ---------------------------------------------------------------------------
# fit_logistic
# ---------------------------------------------------------------------------

def test_fit_logistic_sigmoid_data():
    import math
    # Generate sigmoid-shaped data
    x = [float(i) for i in range(10)]
    y = [1 / (1 + math.exp(-0.8 * (xi - 4.5))) for xi in x]
    fit = fit_logistic(x, y)
    assert fit.law_type == "logistic"
    assert fit.r_squared > 0.5


def test_fit_logistic_insufficient():
    fit = fit_logistic([1.0, 2.0], [0.3, 0.7])
    assert fit.valid is False


# ---------------------------------------------------------------------------
# extrapolate
# ---------------------------------------------------------------------------

def test_extrapolate_returns_triple():
    x = [0.0, 1.0, 2.0, 3.0]
    y = [0.2, 0.4, 0.6, 0.8]
    fit = fit_linear(x, y)
    result = extrapolate(fit, 5.0)
    assert isinstance(result, tuple)
    assert len(result) == 3
    pred, lower, upper = result
    assert 0.0 <= pred <= 1.0
    assert 0.0 <= lower <= pred
    assert pred <= upper <= 1.0


def test_extrapolate_logistic_bounded():
    import math
    x = [float(i) for i in range(8)]
    y = [1 / (1 + math.exp(-0.8 * (xi - 3.5))) for xi in x]
    fit = fit_logistic(x, y)
    pred, lower, upper = extrapolate(fit, 20.0)
    assert 0.0 <= pred <= 1.0


# ---------------------------------------------------------------------------
# detect_phase_transition
# ---------------------------------------------------------------------------

def test_detect_phase_transition_step_function():
    y = [0.1, 0.1, 0.1, 0.8, 0.8, 0.8]
    result = detect_phase_transition(y)
    assert result["detected"] is True
    assert result["transition_index"] > 0
    assert result["magnitude"] > 0.15


def test_detect_phase_transition_monotone():
    y = [0.1, 0.12, 0.14, 0.16, 0.18, 0.20]
    result = detect_phase_transition(y)
    assert result["detected"] is False


def test_detect_phase_transition_short_series():
    result = detect_phase_transition([0.1, 0.9])
    assert result["detected"] is False


# ---------------------------------------------------------------------------
# CapabilityForecastingEngine
# ---------------------------------------------------------------------------

def test_forecasting_engine_produces_forecast():
    engine = CapabilityForecastingEngine()
    for i, score in enumerate([0.3, 0.4, 0.5, 0.6, 0.7]):
        engine.add_data_point(
            ScalingDataPoint(
                model_name=f"model_{i}",
                benchmark_name="bench",
                capability="reasoning",
                score=score,
                date=f"2024-0{i+1}-01",
            )
        )
    forecast = engine.forecast("reasoning", horizon_steps=3)
    assert isinstance(forecast, CapabilityForecast)
    assert forecast.capability == "reasoning"
    assert hasattr(forecast, "confidence")
    assert forecast.confidence in ("high", "medium", "low")
    assert 0.0 <= forecast.forecast_score <= 1.0


def test_forecasting_engine_report():
    engine = CapabilityForecastingEngine()
    for cap in ("reasoning", "safety"):
        for i, score in enumerate([0.5, 0.6, 0.7]):
            engine.add_data_point(
                ScalingDataPoint(
                    model_name="m",
                    benchmark_name="b",
                    capability=cap,
                    score=score,
                    date=f"2024-0{i+1}-01",
                )
            )
    report = engine.generate_report()
    assert report.benchmarks_analyzed >= 1
    assert len(report.forecasts) == 2


# ---------------------------------------------------------------------------
# FrontierMetricsEngine — grade_metric
# ---------------------------------------------------------------------------

def test_grade_metric():
    eng = FrontierMetricsEngine()
    assert eng.grade_metric(0.9) == "A"
    assert eng.grade_metric(0.7) == "B"
    assert eng.grade_metric(0.5) == "C"
    assert eng.grade_metric(0.3) == "D"


# ---------------------------------------------------------------------------
# compute_autonomy
# ---------------------------------------------------------------------------

def test_compute_autonomy_all_success():
    eng = FrontierMetricsEngine()
    steps = [{"tool_success": True} for _ in range(5)]
    score = eng.compute_autonomy(steps)
    assert score.value == 1.0
    assert score.grade == "A"


def test_compute_autonomy_all_errors():
    eng = FrontierMetricsEngine()
    steps = [{"tool_success": False, "error_type": "timeout"} for _ in range(4)]
    score = eng.compute_autonomy(steps)
    assert score.value == 0.0


def test_compute_autonomy_empty():
    eng = FrontierMetricsEngine()
    score = eng.compute_autonomy([])
    assert score.value == 1.0


# ---------------------------------------------------------------------------
# compute_adaptivity
# ---------------------------------------------------------------------------

def test_compute_adaptivity_error_then_recovery():
    eng = FrontierMetricsEngine()
    steps = [
        {"tool_success": False, "error_type": "timeout"},
        {"tool_success": True},
    ]
    score = eng.compute_adaptivity(steps)
    assert score.n_error_episodes == 1
    assert score.n_successful_recoveries == 1
    assert score.value == 1.0


def test_compute_adaptivity_no_errors():
    eng = FrontierMetricsEngine()
    steps = [{"tool_success": True} for _ in range(3)]
    score = eng.compute_adaptivity(steps)
    assert score.value == 1.0


# ---------------------------------------------------------------------------
# compute_efficiency
# ---------------------------------------------------------------------------

def test_compute_efficiency_fewer_steps_higher_value():
    eng = FrontierMetricsEngine()
    steps_few = [{"input_tokens": 100, "output_tokens": 50}] * 3
    steps_many = [{"input_tokens": 100, "output_tokens": 50}] * 8
    eff_few = eng.compute_efficiency(steps_few, max_steps=10, task_completed=True)
    eff_many = eng.compute_efficiency(steps_many, max_steps=10, task_completed=True)
    assert eff_few.value > eff_many.value


def test_compute_efficiency_incomplete_task():
    eng = FrontierMetricsEngine()
    steps = [{}] * 4
    eff = eng.compute_efficiency(steps, max_steps=10, task_completed=False)
    # incomplete => multiplied by 0.5
    assert eff.value < eng.compute_efficiency(steps, max_steps=10, task_completed=True).value


# ---------------------------------------------------------------------------
# compute_generalization
# ---------------------------------------------------------------------------

def test_compute_generalization_identical_scores():
    eng = FrontierMetricsEngine()
    scores = {"bench_a": 0.8, "bench_b": 0.8, "bench_c": 0.8}
    gen = eng.compute_generalization(scores)
    assert gen.value > 0.95  # CV ≈ 0 => value ≈ 1


def test_compute_generalization_empty():
    eng = FrontierMetricsEngine()
    gen = eng.compute_generalization({})
    assert gen.value == 0.5


# ---------------------------------------------------------------------------
# compute_all
# ---------------------------------------------------------------------------

def test_compute_all_returns_full_result():
    eng = FrontierMetricsEngine()
    steps = [{"tool_success": True, "input_tokens": 100, "output_tokens": 50}] * 5
    result = eng.compute_all(
        model_name="gpt-test",
        steps=steps,
        benchmark_scores={"a": 0.7, "b": 0.8},
        capability_score=0.75,
        propensity_score=0.6,
        safety_score=0.9,
        max_steps=10,
        task_completed=True,
    )
    assert isinstance(result, FrontierMetricsResult)
    assert result.model_name == "gpt-test"
    assert 0.0 <= result.composite_frontier_score <= 1.0
    assert result.frontier_grade in ("A", "B", "C", "D")
    assert result.capability_score == 0.75
    assert result.propensity_score == 0.6
    assert result.safety_score == 0.9
    assert "capability" in result.three_axis_summary
    assert "propensity" in result.three_axis_summary
    assert "safety" in result.three_axis_summary


# ---------------------------------------------------------------------------
# LONG_HORIZON_TASKS — all 5 loadable
# ---------------------------------------------------------------------------

def test_all_tasks_loadable():
    ev = LongHorizonEvaluator()
    assert len(LONG_HORIZON_TASKS) == 5
    for task_dict in LONG_HORIZON_TASKS:
        task = ev.load_task(task_dict)
        assert task.task_id == task_dict["task_id"]
        assert len(task.sub_goals) == len(task_dict["sub_goals"])


# ---------------------------------------------------------------------------
# simulate_run
# ---------------------------------------------------------------------------

def _make_perfect_responses(task_dict):
    """Build step responses that satisfy each sub-goal's first success criterion."""
    responses = []
    for sg in task_dict["sub_goals"]:
        crit = sg["success_criteria"][0] if sg["success_criteria"] else "ok"
        responses.append({"text": crit, "tokens": 100})
    return responses


def test_simulate_run_perfect_responses():
    ev = LongHorizonEvaluator()
    task_dict = LONG_HORIZON_TASKS[0]  # data_analysis_pipeline
    task = ev.load_task(task_dict)
    responses = _make_perfect_responses(task_dict)
    result = ev.simulate_run(task, responses)
    assert result.completion_rate > 0
    assert result.task_id == task_dict["task_id"]


def test_simulate_run_no_responses():
    ev = LongHorizonEvaluator()
    task_dict = LONG_HORIZON_TASKS[1]  # code_review_comprehensive
    task = ev.load_task(task_dict)
    result = ev.simulate_run(task, [])
    assert result.completion_rate == 0.0
    assert result.main_goal_achieved is False


# ---------------------------------------------------------------------------
# compute_partial_credit
# ---------------------------------------------------------------------------

def test_compute_partial_credit():
    ev = LongHorizonEvaluator()
    results = [
        SubGoalResult("sg1", completed=True, partial_credit=0.4, steps_taken=1, tokens_used=50),
        SubGoalResult("sg2", completed=True, partial_credit=0.3, steps_taken=1, tokens_used=50),
        SubGoalResult("sg3", completed=False, partial_credit=0.0, steps_taken=1, tokens_used=0),
    ]
    credit = ev.compute_partial_credit(results)
    assert abs(credit - round((0.4 + 0.3 + 0.0) / 3, 4)) < 1e-6


def test_compute_partial_credit_empty():
    ev = LongHorizonEvaluator()
    assert ev.compute_partial_credit([]) == 0.0


# ---------------------------------------------------------------------------
# compute_recovery_rate
# ---------------------------------------------------------------------------

def test_compute_recovery_rate_no_failures():
    ev = LongHorizonEvaluator()
    results = [
        SubGoalResult("sg1", completed=True, partial_credit=0.5, steps_taken=1, tokens_used=0),
    ]
    assert ev.compute_recovery_rate(results) == 1.0


def test_compute_recovery_rate_with_recovery():
    ev = LongHorizonEvaluator()
    results = [
        SubGoalResult("sg1", completed=False, partial_credit=0.0, steps_taken=1, tokens_used=0, recovery_occurred=True),
        SubGoalResult("sg2", completed=False, partial_credit=0.0, steps_taken=1, tokens_used=0, recovery_occurred=False),
    ]
    rate = ev.compute_recovery_rate(results)
    assert abs(rate - 0.5) < 1e-6


# ---------------------------------------------------------------------------
# fit_linear — residuals and MAE
# ---------------------------------------------------------------------------

def test_fit_linear_returns_residuals():
    x = [0.0, 1.0, 2.0, 3.0]
    y = [0.0, 1.0, 2.0, 3.0]  # perfect y=x
    fit = fit_linear(x, y)
    assert isinstance(fit.residuals, list)
    assert len(fit.residuals) == 4
    # perfect fit -> all residuals ~0
    assert all(abs(r) < 1e-6 for r in fit.residuals)
    assert fit.mae < 1e-6


def test_fit_power_law_returns_residuals():
    x = [1.0, 2.0, 4.0, 8.0]
    y = [1.0, 2.0 ** 0.5, 2.0, 2.0 ** 1.5]  # y = x^0.5
    fit = fit_power_law(x, y)
    assert isinstance(fit.residuals, list)
    assert len(fit.residuals) == 4


def test_fit_logistic_returns_residuals():
    import math
    x = [float(i) for i in range(8)]
    y = [1 / (1 + math.exp(-0.8 * (xi - 3.5))) for xi in x]
    fit = fit_logistic(x, y)
    assert isinstance(fit.residuals, list)
    assert len(fit.residuals) == 8
    assert fit.mae >= 0.0


# ---------------------------------------------------------------------------
# fit_chinchilla
# ---------------------------------------------------------------------------

def test_fit_chinchilla_valid():
    import math
    # Synthetic Chinchilla data: score = 1 - (1/N^0.5 + 1/D^0.5) * 0.2
    params = [1e8, 3e8, 1e9, 3e9, 1e10]
    tokens = [1e9, 3e9, 1e10, 3e10, 1e11]
    scores = [1 - 0.2 * (1 / n ** 0.5 + 1 / d ** 0.5) for n, d in zip(params, tokens)]
    scores = [max(0.01, min(0.99, s)) for s in scores]
    fit = fit_chinchilla(params, tokens, scores)
    assert isinstance(fit, MultiDimScalingFit)
    assert fit.n_points == 5
    assert fit.alpha != 0.0 or not fit.valid  # if valid, alpha should be non-trivial
    assert 0.0 <= fit.r_squared <= 1.0


def test_fit_chinchilla_insufficient():
    fit = fit_chinchilla([1e8, 3e8], [1e9, 3e9], [0.5, 0.6])
    assert fit.valid is False
    assert fit.n_points <= 2


# ---------------------------------------------------------------------------
# validate_data_quality
# ---------------------------------------------------------------------------

def _make_points(overrides=None):
    base = [
        ScalingDataPoint("m1", "bench", "reasoning", 0.6),
        ScalingDataPoint("m2", "bench", "reasoning", 0.7),
        ScalingDataPoint("m3", "bench", "safety", 0.8),
    ]
    if overrides:
        base.extend(overrides)
    return base


def test_validate_data_quality_clean():
    report = validate_data_quality(_make_points())
    assert isinstance(report, DataQualityReport)
    assert report.total_points == 3
    assert report.valid_points == 3
    assert report.invalid_points == 0
    assert report.score_range_violations == 0
    assert report.passed is True


def test_validate_data_quality_out_of_range():
    bad = ScalingDataPoint("m_bad", "bench", "reasoning", 1.5)
    report = validate_data_quality(_make_points([bad]))
    assert report.score_range_violations == 1
    assert report.invalid_points == 1
    assert report.passed is False
    assert any("1.5" in issue or "m_bad" in issue for issue in report.issues)


def test_validate_data_quality_duplicates():
    dup = ScalingDataPoint("m1", "bench", "reasoning", 0.6, date="1970-01-01T00:00:00")
    dup2 = ScalingDataPoint("m1", "bench", "reasoning", 0.6, date="1970-01-01T00:00:00")
    report = validate_data_quality([dup, dup2])
    assert report.duplicate_count == 1
    assert report.passed is False


def test_validate_data_quality_missing_ci_flagged():
    # Default ci_lower=0.0, ci_upper=1.0 → flagged as missing CI
    pts = [ScalingDataPoint("m", "b", "cap", 0.5)]
    report = validate_data_quality(pts)
    assert report.missing_ci_count == 1
    # missing CI doesn't count as invalid
    assert report.valid_points == 1


# ---------------------------------------------------------------------------
# CapabilityForecastingEngine — new methods
# ---------------------------------------------------------------------------

def _make_engine(capability="reasoning", n=5):
    engine = CapabilityForecastingEngine()
    scores = [0.3 + i * 0.1 for i in range(n)]
    for i, score in enumerate(scores):
        engine.add_data_point(
            ScalingDataPoint(
                model_name=f"model_{i}",
                benchmark_name="bench",
                capability=capability,
                score=score,
                date=f"2024-0{i+1}-01",
            )
        )
    return engine


def test_residual_analysis_returns_dict():
    engine = _make_engine("reasoning")
    result = engine.residual_analysis("reasoning")
    assert isinstance(result, dict)
    assert "residuals" in result
    assert "r_squared" in result
    assert "mae" in result
    assert result["n_points"] == 5


def test_capability_gap_to_frontier_zero_when_at_frontier():
    engine = _make_engine("reasoning", n=1)
    gaps = engine.capability_gap_to_frontier(["reasoning"])
    # Single point: current == frontier → gap == 0
    assert gaps.get("reasoning", -1) == 0.0


def test_capability_gap_to_frontier_nonzero():
    engine = _make_engine("reasoning", n=5)
    # Add a higher frontier point
    engine.add_data_point(ScalingDataPoint("frontier_model", "bench", "reasoning", 0.95, date="2025-01-01"))
    # Then add a non-frontier point as last
    engine.add_data_point(ScalingDataPoint("recent_model", "bench", "reasoning", 0.75, date="2025-02-01"))
    gaps = engine.capability_gap_to_frontier(["reasoning"])
    # frontier = 0.95, last = 0.75 → gap = 0.20
    assert gaps["reasoning"] > 0.0


def test_forecast_includes_new_fields():
    engine = _make_engine("reasoning")
    forecast = engine.forecast("reasoning")
    assert hasattr(forecast, "capability_score")
    assert hasattr(forecast, "propensity_score")
    assert hasattr(forecast, "gap_to_frontier")
    assert 0.0 <= forecast.gap_to_frontier <= 1.0


def test_forecast_separates_capability_propensity():
    engine = CapabilityForecastingEngine()
    for i, (score, stype) in enumerate([
        (0.5, "capability"), (0.6, "capability"), (0.7, "capability"),
        (0.3, "propensity"), (0.35, "propensity"), (0.4, "propensity"),
    ]):
        engine.add_data_point(
            ScalingDataPoint("m", "b", "agentic", score, score_type=stype, date=f"2024-0{i+1}-01")
        )
    fc = engine.forecast("agentic")
    assert fc.capability_score != fc.propensity_score


def test_record_calibration():
    engine = _make_engine("reasoning")
    record = engine.record_calibration("reasoning", 0.75, 0.70, "+3 cycles")
    assert isinstance(record, ForecastCalibrationRecord)
    assert record.absolute_error == 0.05
    history = engine.get_calibration_history()
    assert len(history) == 1
    assert history[0].capability == "reasoning"


def test_calibration_mae_computed():
    engine = _make_engine("reasoning")
    engine.record_calibration("reasoning", 0.75, 0.70)
    engine.record_calibration("reasoning", 0.80, 0.76)
    mae = engine._compute_calibration_mae()
    expected = round((0.05 + 0.04) / 2, 4)
    assert abs(mae - expected) < 1e-4


def test_generate_report_includes_frontier_gaps():
    engine = CapabilityForecastingEngine()
    for cap in ("reasoning", "safety"):
        for i, score in enumerate([0.5, 0.6, 0.7]):
            engine.add_data_point(
                ScalingDataPoint("m", "b", cap, score, date=f"2024-0{i+1}-01")
            )
    report = engine.generate_report()
    assert isinstance(report.frontier_gaps, dict)
    assert "reasoning" in report.frontier_gaps
    assert "safety" in report.frontier_gaps
    # calibration MAE with no records should be 0
    assert report.calibration_mae == 0.0
