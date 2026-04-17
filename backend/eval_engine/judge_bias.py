"""Judge Bias Detection — positional, verbosity, and self-preference biases."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class BiasTestResult:
    bias_type: str
    score_original: float
    score_perturbed: float
    delta: float
    bias_detected: bool
    severity: str
    interpretation: str
    n_items_tested: int


@dataclass
class JudgeBiasReport:
    judge_name: str
    positional_bias: BiasTestResult
    verbosity_bias: BiasTestResult
    self_preference_bias: BiasTestResult
    overall_bias_score: float
    reliability_grade: str
    is_production_safe: bool
    recommendations: list
    n_tests: int
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class JudgeScorePair:
    item_id: str
    prompt: str
    response_a: str
    response_b: str
    score_a_first: float
    score_b_first: float
    score_a_second: float
    score_b_second: float
    expected_preference: str = ""


def _severity(delta: float) -> str:
    if delta > 0.25:
        return "high"
    if delta > 0.15:
        return "medium"
    if delta > 0.1:
        return "low"
    return "none"


def _empty_bias(bias_type: str) -> BiasTestResult:
    return BiasTestResult(bias_type, 0.0, 0.0, 0.0, False, "none", "No data", 0)


def detect_positional_bias(pairs: list) -> BiasTestResult:
    if not pairs:
        return _empty_bias("positional")
    deltas = [abs(p.score_a_first - p.score_a_second) for p in pairs]
    delta = sum(deltas) / len(deltas)
    orig = sum(p.score_a_first for p in pairs) / len(pairs)
    pert = sum(p.score_a_second for p in pairs) / len(pairs)
    return BiasTestResult(
        "positional", round(orig, 4), round(pert, 4), round(delta, 4),
        delta > 0.1, _severity(delta),
        f"Mean position-swap delta: {delta:.3f}", len(pairs),
    )


def detect_verbosity_bias(base_scores: list, verbose_scores: list) -> BiasTestResult:
    if not base_scores or not verbose_scores:
        return _empty_bias("verbosity")
    base_m = sum(d["judge_score"] for d in base_scores) / len(base_scores)
    verb_m = sum(d["judge_score"] for d in verbose_scores) / len(verbose_scores)
    delta = verb_m - base_m
    return BiasTestResult(
        "verbosity", round(base_m, 4), round(verb_m, 4), round(abs(delta), 4),
        delta > 0.1, _severity(abs(delta)),
        f"Verbosity increases score by {delta:+.3f}", len(base_scores),
    )


def detect_self_preference_bias(same_family: list, different_family: list) -> BiasTestResult:
    if not same_family or not different_family:
        return _empty_bias("self_preference")
    same_m = sum(same_family) / len(same_family)
    diff_m = sum(different_family) / len(different_family)
    delta = same_m - diff_m
    return BiasTestResult(
        "self_preference", round(same_m, 4), round(diff_m, 4), round(abs(delta), 4),
        delta > 0.1, _severity(abs(delta)),
        f"Self-preference delta: {delta:+.3f}", len(same_family),
    )


def pearson_correlation(x: list, y: list) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    mx, my = sum(x) / n, sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    den = math.sqrt(sum((xi - mx) ** 2 for xi in x) * sum((yi - my) ** 2 for yi in y))
    return round(num / den, 4) if den else 0.0


def compute_judge_human_agreement(judge_scores: list, human_scores: list) -> float:
    return pearson_correlation(judge_scores, human_scores)


def compute_bias_report(judge_name: str, positional: BiasTestResult,
                        verbosity: BiasTestResult, self_pref: BiasTestResult) -> JudgeBiasReport:
    detected = [b for b in [positional, verbosity, self_pref] if b.bias_detected]
    score = round(sum(b.delta for b in detected) / max(len(detected), 1), 4) if detected else 0.0
    grade = "A" if score < 0.1 else "B" if score < 0.2 else "C" if score < 0.3 else "D"
    recs = []
    if positional.bias_detected:
        recs.append("Apply position randomization during evaluation")
    if verbosity.bias_detected:
        recs.append("Normalize response length before judging")
    if self_pref.bias_detected:
        recs.append("Use cross-family judges to reduce self-preference")
    return JudgeBiasReport(
        judge_name=judge_name, positional_bias=positional,
        verbosity_bias=verbosity, self_preference_bias=self_pref,
        overall_bias_score=score, reliability_grade=grade,
        is_production_safe=score < 0.3, recommendations=recs, n_tests=3,
    )


class JudgeBiasDetector:
    def run_positional_swap_test(self, pairs: list) -> BiasTestResult:
        return detect_positional_bias(pairs)

    def run_verbosity_test(self, base: list, verbose: list) -> BiasTestResult:
        return detect_verbosity_bias(base, verbose)

    def generate_report(self, judge_name: str, test_results: dict) -> JudgeBiasReport:
        return compute_bias_report(
            judge_name,
            test_results.get("positional", _empty_bias("positional")),
            test_results.get("verbosity", _empty_bias("verbosity")),
            test_results.get("self_preference", _empty_bias("self_preference")),
        )

    def interpret_bias_score(self, score: float) -> str:
        if score < 0.1:
            return "Minimal bias — suitable for production evaluation"
        if score < 0.2:
            return "Low bias — acceptable with monitoring"
        if score < 0.3:
            return "Moderate bias — use with caution, recommend calibration"
        return "High bias — not recommended for production without debiasing"
