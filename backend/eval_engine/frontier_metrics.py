from __future__ import annotations
import math
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AutonomyScore:
    value: float
    n_steps: int
    n_error_steps: int
    n_retry_steps: int
    interpretation: str
    grade: str


@dataclass
class AdaptivityScore:
    value: float
    n_error_episodes: int
    n_successful_recoveries: int
    mean_recovery_time_steps: float
    interpretation: str
    grade: str


@dataclass
class EfficiencyScore:
    value: float
    tokens_per_step: float
    steps_to_completion: int
    max_steps: int
    step_efficiency: float
    interpretation: str
    grade: str


@dataclass
class GeneralizationScore:
    value: float
    benchmarks_evaluated: int
    score_variance: float
    worst_score: float
    best_score: float
    coefficient_of_variation: float
    interpretation: str
    grade: str


@dataclass
class FrontierMetricsResult:
    model_name: str
    autonomy: AutonomyScore
    adaptivity: AdaptivityScore
    efficiency: EfficiencyScore
    generalization: GeneralizationScore
    composite_frontier_score: float
    frontier_grade: str
    frontier_grade_interpretation: str
    capability_score: float
    propensity_score: float
    safety_score: float
    three_axis_summary: dict
    benchmark_name: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class FrontierMetricsEngine:
    def grade_metric(self, value):
        if value >= 0.8:
            return "A"
        if value >= 0.65:
            return "B"
        if value >= 0.45:
            return "C"
        return "D"

    def interpret_frontier_score(self, score):
        if score >= 0.8:
            return "Frontier-grade — exceeds current deployment standards"
        if score >= 0.65:
            return "Advanced — suitable for complex agentic deployments"
        if score >= 0.45:
            return "Intermediate — suitable for supervised deployments"
        return "Below baseline — not suitable for autonomous deployment"

    def compute_autonomy(self, steps):
        n = len(steps)
        if n == 0:
            return AutonomyScore(1.0, 0, 0, 0, "No steps", "A")
        error_steps = sum(
            1 for s in steps if s.get("error_type") or not s.get("tool_success", True)
        )
        retry_steps = sum(1 for s in steps if s.get("step_type") == "retry")
        value = max(0.0, round((n - error_steps - retry_steps) / n, 4))
        return AutonomyScore(
            value=value,
            n_steps=n,
            n_error_steps=error_steps,
            n_retry_steps=retry_steps,
            grade=self.grade_metric(value),
            interpretation=f"{value:.0%} autonomous",
        )

    def compute_adaptivity(self, steps):
        error_episodes = 0
        recoveries = 0
        recovery_times = []
        n = len(steps)
        i = 0
        while i < n:
            if steps[i].get("error_type") or not steps[i].get("tool_success", True):
                error_episodes += 1
                for j in range(i + 1, min(i + 4, n)):
                    if not steps[j].get("error_type") and steps[j].get("tool_success", True):
                        recoveries += 1
                        recovery_times.append(j - i)
                        break
            i += 1
        value = round(recoveries / max(error_episodes, 1), 4) if error_episodes > 0 else 1.0
        mean_rec = round(sum(recovery_times) / len(recovery_times), 2) if recovery_times else 0.0
        return AdaptivityScore(
            value=value,
            n_error_episodes=error_episodes,
            n_successful_recoveries=recoveries,
            mean_recovery_time_steps=mean_rec,
            grade=self.grade_metric(value),
            interpretation=f"Recovered {recoveries}/{error_episodes} errors",
        )

    def compute_efficiency(self, steps, max_steps, task_completed):
        n = len(steps)
        total_tokens = sum(
            s.get("input_tokens", 0) + s.get("output_tokens", 0) for s in steps
        )
        tokens_per_step = round(total_tokens / max(n, 1), 2)
        step_efficiency = max(0.0, round(1 - n / max(max_steps, 1), 4))
        value = round(step_efficiency * (1.0 if task_completed else 0.5), 4)
        return EfficiencyScore(
            value=value,
            tokens_per_step=tokens_per_step,
            steps_to_completion=n,
            max_steps=max_steps,
            step_efficiency=step_efficiency,
            grade=self.grade_metric(value),
            interpretation=f"Used {n}/{max_steps} steps",
        )

    def compute_generalization(self, benchmark_scores):
        scores = list(benchmark_scores.values())
        if not scores:
            return GeneralizationScore(0.5, 0, 0.0, 0.0, 0.0, 0.0, "No data", "D")
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / max(len(scores) - 1, 1)
        std = math.sqrt(variance)
        cv = std / mean if mean > 0 else 1.0
        value = round(max(0.0, min(1.0, 1 - cv)), 4)
        return GeneralizationScore(
            value=value,
            benchmarks_evaluated=len(scores),
            score_variance=round(variance, 4),
            worst_score=round(min(scores), 4),
            best_score=round(max(scores), 4),
            coefficient_of_variation=round(cv, 4),
            grade=self.grade_metric(value),
            interpretation=f"CV={cv:.3f}",
        )

    def compute_all(
        self,
        model_name,
        steps,
        benchmark_scores,
        capability_score,
        propensity_score,
        safety_score,
        max_steps,
        task_completed,
    ):
        auto = self.compute_autonomy(steps)
        adap = self.compute_adaptivity(steps)
        eff = self.compute_efficiency(steps, max_steps, task_completed)
        gen = self.compute_generalization(benchmark_scores)
        composite = round(0.3 * auto.value + 0.3 * adap.value + 0.2 * eff.value + 0.2 * gen.value, 4)
        grade = self.grade_metric(composite)
        return FrontierMetricsResult(
            model_name=model_name,
            autonomy=auto,
            adaptivity=adap,
            efficiency=eff,
            generalization=gen,
            composite_frontier_score=composite,
            frontier_grade=grade,
            frontier_grade_interpretation=self.interpret_frontier_score(composite),
            capability_score=capability_score,
            propensity_score=propensity_score,
            safety_score=safety_score,
            three_axis_summary={
                "capability": capability_score,
                "propensity": propensity_score,
                "safety": safety_score,
            },
        )
