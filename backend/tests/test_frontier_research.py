"""
Tests for Milestone 5 — Frontier Research:
capability_forecasting, frontier_metrics, long_horizon.
"""
import pytest

from eval_engine.capability_forecasting import (
    fit_linear,
    fit_power_law,
    fit_logistic,
    extrapolate,
    detect_phase_transition,
    CapabilityForecastingEngine,
    ScalingDataPoint,
    CapabilityForecast,
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
