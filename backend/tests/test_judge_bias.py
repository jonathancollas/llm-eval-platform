"""Tests for judge_bias.py and scenario_runtime.py (Milestone 4)."""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from eval_engine.judge_bias import (
    BiasTestResult, JudgeBiasReport, JudgeScorePair,
    detect_positional_bias, detect_verbosity_bias, detect_self_preference_bias,
    compute_judge_human_agreement, compute_bias_report, JudgeBiasDetector,
    _empty_bias,
)
from eval_engine.scenario_runtime import (
    EXAMPLE_SCENARIOS, ScenarioRuntime, load_scenario, validate_scenario,
    evaluate_step, ScenarioStep, StepExecutionResult,
)


# ---------------------------------------------------------------------------
# detect_positional_bias
# ---------------------------------------------------------------------------

def _make_pair(a_first, a_second):
    return JudgeScorePair(
        item_id="x", prompt="p", response_a="a", response_b="b",
        score_a_first=a_first, score_b_first=0.5,
        score_a_second=a_second, score_b_second=0.5,
    )


def test_positional_bias_not_detected_when_consistent():
    pairs = [_make_pair(0.8, 0.8), _make_pair(0.6, 0.6)]
    result = detect_positional_bias(pairs)
    assert result.bias_detected is False
    assert result.delta == 0.0


def test_positional_bias_detected_when_large_delta():
    pairs = [_make_pair(0.9, 0.4), _make_pair(0.8, 0.3)]
    result = detect_positional_bias(pairs)
    assert result.bias_detected is True
    assert result.severity in ("medium", "high")


def test_positional_bias_empty():
    result = detect_positional_bias([])
    assert result.bias_detected is False
    assert result.n_items_tested == 0


# ---------------------------------------------------------------------------
# detect_verbosity_bias
# ---------------------------------------------------------------------------

def test_verbosity_bias_detected_when_verbose_higher():
    base = [{"judge_score": 0.5}, {"judge_score": 0.5}]
    verbose = [{"judge_score": 0.8}, {"judge_score": 0.8}]
    result = detect_verbosity_bias(base, verbose)
    assert result.bias_detected is True
    assert result.score_perturbed > result.score_original


def test_verbosity_bias_not_detected_when_equal():
    base = [{"judge_score": 0.7}]
    verbose = [{"judge_score": 0.7}]
    result = detect_verbosity_bias(base, verbose)
    assert result.bias_detected is False


def test_verbosity_bias_empty():
    assert detect_verbosity_bias([], []).bias_detected is False


# ---------------------------------------------------------------------------
# detect_self_preference_bias
# ---------------------------------------------------------------------------

def test_self_preference_detected_when_same_family_higher():
    result = detect_self_preference_bias([0.9, 0.85], [0.5, 0.55])
    assert result.bias_detected is True
    assert result.score_original > result.score_perturbed


def test_self_preference_not_detected_when_equal():
    result = detect_self_preference_bias([0.7, 0.7], [0.7, 0.7])
    assert result.bias_detected is False


def test_self_preference_empty():
    assert detect_self_preference_bias([], []).bias_detected is False


# ---------------------------------------------------------------------------
# compute_judge_human_agreement
# ---------------------------------------------------------------------------

def test_agreement_monotone_approx_one():
    judge = [0.1, 0.3, 0.5, 0.7, 0.9]
    human = [0.1, 0.3, 0.5, 0.7, 0.9]
    r = compute_judge_human_agreement(judge, human)
    assert abs(r - 1.0) < 0.001


def test_agreement_anticorrelated():
    judge = [0.1, 0.3, 0.5, 0.7, 0.9]
    human = [0.9, 0.7, 0.5, 0.3, 0.1]
    r = compute_judge_human_agreement(judge, human)
    assert r < -0.9


def test_agreement_too_short():
    assert compute_judge_human_agreement([0.5], [0.5]) == 0.0


# ---------------------------------------------------------------------------
# compute_bias_report
# ---------------------------------------------------------------------------

def test_grade_a_with_low_biases():
    pos = _empty_bias("positional")
    verb = _empty_bias("verbosity")
    sp = _empty_bias("self_preference")
    report = compute_bias_report("gpt-4o", pos, verb, sp)
    assert report.reliability_grade == "A"
    assert report.is_production_safe is True
    assert report.overall_bias_score == 0.0


def test_grade_d_with_high_biases():
    pos = BiasTestResult("positional", 0.9, 0.4, 0.5, True, "high", "", 5)
    verb = BiasTestResult("verbosity", 0.5, 0.9, 0.4, True, "high", "", 5)
    sp = BiasTestResult("self_preference", 0.9, 0.4, 0.5, True, "high", "", 5)
    report = compute_bias_report("gpt-4o", pos, verb, sp)
    assert report.reliability_grade == "D"
    assert len(report.recommendations) == 3


# ---------------------------------------------------------------------------
# JudgeBiasDetector.interpret_bias_score
# ---------------------------------------------------------------------------

def test_interpret_all_ranges():
    d = JudgeBiasDetector()
    assert "Minimal" in d.interpret_bias_score(0.05)
    assert "Low" in d.interpret_bias_score(0.15)
    assert "Moderate" in d.interpret_bias_score(0.25)
    assert "High" in d.interpret_bias_score(0.35)


# ---------------------------------------------------------------------------
# load_scenario
# ---------------------------------------------------------------------------

def test_load_all_example_scenarios():
    for raw in EXAMPLE_SCENARIOS:
        s = load_scenario(raw)
        assert s.name
        assert len(s.steps) > 0


# ---------------------------------------------------------------------------
# validate_scenario
# ---------------------------------------------------------------------------

def test_validate_valid_scenario():
    s = load_scenario(EXAMPLE_SCENARIOS[0])
    errors = validate_scenario(s)
    assert errors == []


def test_validate_missing_name():
    raw = dict(EXAMPLE_SCENARIOS[0])
    raw["name"] = ""
    s = load_scenario(raw)
    errors = validate_scenario(s)
    assert any("name" in e for e in errors)


# ---------------------------------------------------------------------------
# evaluate_step
# ---------------------------------------------------------------------------

def test_evaluate_step_keyword_match():
    step = ScenarioStep(
        step_id="s1", description="test", expected_action_type="answer",
        success_condition="contains_keyword", keywords=["revenue", "users"],
        partial_credit=0.5,
    )
    success, credit = evaluate_step(step, {"text": "Revenue is high"}, {})
    assert success is True
    assert credit == 0.5


def test_evaluate_step_no_keyword_match():
    step = ScenarioStep(
        step_id="s1", description="test", expected_action_type="answer",
        success_condition="contains_keyword", keywords=["revenue"],
        partial_credit=0.5,
    )
    success, credit = evaluate_step(step, {"text": "Nothing relevant here"}, {})
    assert success is False
    assert credit == 0.0


def test_evaluate_step_tool_called():
    step = ScenarioStep(
        step_id="s2", description="use tool", expected_action_type="tool",
        expected_tool="search", success_condition="tool_called", partial_credit=1.0,
    )
    success, credit = evaluate_step(step, {"tool": "search"}, {})
    assert success is True
    assert credit == 1.0


# ---------------------------------------------------------------------------
# ScenarioRuntime.simulate_run
# ---------------------------------------------------------------------------

def _perfect_responses(scenario_name: str):
    """Return responses that satisfy all keyword checks for a named example scenario."""
    mapping = {
        "data_extraction": [
            {"text": "revenue users growth churn"},
            {"text": "1.2 45000 23 2.1"},
        ],
        "code_debugging": [
            {"text": "off-by-one index range 0"},
            {"text": "range(0 start"},
        ],
        "information_synthesis": [
            {"text": "2024 2026"},
            {"text": "2 two years"},
        ],
    }
    return mapping[scenario_name]


def test_simulate_run_perfect_responses():
    runtime = ScenarioRuntime()
    raw = EXAMPLE_SCENARIOS[0]  # data_extraction
    scenario = load_scenario(raw)
    responses = _perfect_responses(scenario.name)
    result = runtime.simulate_run(scenario, responses)
    assert result.completion_rate == 1.0
    assert result.overall_success is True
    assert result.failure_modes == []


def test_simulate_run_empty_responses():
    runtime = ScenarioRuntime()
    scenario = load_scenario(EXAMPLE_SCENARIOS[0])
    result = runtime.simulate_run(scenario, [])
    assert result.completion_rate == 0.0
    assert result.overall_success is False
    assert len(result.failure_modes) == len(scenario.steps)


# ---------------------------------------------------------------------------
# evaluate_partial_credit
# ---------------------------------------------------------------------------

def test_evaluate_partial_credit():
    runtime = ScenarioRuntime()
    results = [
        StepExecutionResult("s1", 0, "", "", "", True, 0.4),
        StepExecutionResult("s2", 1, "", "", "", True, 0.6),
    ]
    assert runtime.evaluate_partial_credit(results) == 0.5


def test_evaluate_partial_credit_empty():
    assert ScenarioRuntime().evaluate_partial_credit([]) == 0.0


# ---------------------------------------------------------------------------
# classify_failures
# ---------------------------------------------------------------------------

def test_classify_failures():
    runtime = ScenarioRuntime()
    results = [
        StepExecutionResult("step_a", 0, "", "", "", True, 0.5),
        StepExecutionResult("step_b", 1, "", "", "", False, 0.0),
        StepExecutionResult("step_c", 2, "", "", "", False, 0.0),
    ]
    failures = runtime.classify_failures(results)
    assert "step_step_b_failed" in failures
    assert "step_step_c_failed" in failures
    assert len(failures) == 2
