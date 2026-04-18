import math
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Optional


# ---------------------------------------------------------------------------
# Score dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ConfidenceInterval:
    lower: float
    upper: float
    level: float = 0.95


@dataclass
class AutonomyScore:
    value: float
    n_steps: int
    n_error_steps: int
    n_retry_steps: int
    interpretation: str
    grade: str
    ci: Optional[ConfidenceInterval] = None


@dataclass
class AdaptivityScore:
    value: float
    n_error_episodes: int
    n_successful_recoveries: int
    mean_recovery_time_steps: float
    interpretation: str
    grade: str
    ci: Optional[ConfidenceInterval] = None


@dataclass
class EfficiencyScore:
    value: float
    tokens_per_step: float
    steps_to_completion: int
    max_steps: int
    step_efficiency: float
    interpretation: str
    grade: str
    ci: Optional[ConfidenceInterval] = None


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
    ci: Optional[ConfidenceInterval] = None


@dataclass
class CapabilityBreakdown:
    """Per-capability frontier metric scores."""
    capability: str
    autonomy: float
    adaptivity: float
    efficiency: float
    composite: float
    n_steps: int


@dataclass
class MetricCorrelations:
    """Pairwise Pearson correlations between the 4 frontier metrics."""
    autonomy_adaptivity: float
    autonomy_efficiency: float
    autonomy_generalization: float
    adaptivity_efficiency: float
    adaptivity_generalization: float
    efficiency_generalization: float
    interpretation: str


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
    capability_breakdown: list = field(default_factory=list)
    benchmark_name: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class FrontierMetricsEngine:
    # ── Grading & interpretation ──────────────────────────────────────────────

    def grade_metric(self, value: float) -> str:
        if value >= 0.8:
            return "A"
        if value >= 0.65:
            return "B"
        if value >= 0.45:
            return "C"
        return "D"

    def interpret_frontier_score(self, score: float) -> str:
        if score >= 0.8:
            return "Frontier-grade — exceeds current deployment standards"
        if score >= 0.65:
            return "Advanced — suitable for complex agentic deployments"
        if score >= 0.45:
            return "Intermediate — suitable for supervised deployments"
        return "Below baseline — not suitable for autonomous deployment"

    # ── Uncertainty quantification ────────────────────────────────────────────

    @staticmethod
    def wilson_ci(successes: int, n: int, level: float = 0.95) -> ConfidenceInterval:
        """Wilson score confidence interval for a proportion (successes/n)."""
        if n == 0:
            return ConfidenceInterval(0.0, 1.0, level)
        # z-score for 95% CI ≈ 1.96
        z = 1.96 if level == 0.95 else 1.645
        p = successes / n
        denom = 1 + z ** 2 / n
        centre = (p + z ** 2 / (2 * n)) / denom
        half = (z * math.sqrt(p * (1 - p) / n + z ** 2 / (4 * n ** 2))) / denom
        lower = round(max(0.0, centre - half), 4)
        upper = round(min(1.0, centre + half), 4)
        return ConfidenceInterval(lower=lower, upper=upper, level=level)

    # ── Individual metric computation ─────────────────────────────────────────

    def compute_autonomy(self, steps: list) -> AutonomyScore:
        """Fraction of task steps completed without human intervention or error recovery."""
        n = len(steps)
        if n == 0:
            return AutonomyScore(1.0, 0, 0, 0, "No steps", "A",
                                 ci=ConfidenceInterval(1.0, 1.0))
        error_steps = sum(
            1 for s in steps if s.get("error_type") or not s.get("tool_success", True)
        )
        retry_steps = sum(1 for s in steps if s.get("step_type") == "retry")
        autonomous = n - error_steps - retry_steps
        value = max(0.0, round(autonomous / n, 4))
        ci = self.wilson_ci(max(0, autonomous), n)
        return AutonomyScore(
            value=value,
            n_steps=n,
            n_error_steps=error_steps,
            n_retry_steps=retry_steps,
            grade=self.grade_metric(value),
            interpretation=f"{value:.0%} autonomous",
            ci=ci,
        )

    def compute_adaptivity(self, steps: list) -> AdaptivityScore:
        """Performance recovery rate after encountering unexpected states (error recovery)."""
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
        ci = self.wilson_ci(recoveries, max(error_episodes, 1)) if error_episodes > 0 else ConfidenceInterval(1.0, 1.0)
        return AdaptivityScore(
            value=value,
            n_error_episodes=error_episodes,
            n_successful_recoveries=recoveries,
            mean_recovery_time_steps=mean_rec,
            grade=self.grade_metric(value),
            interpretation=f"Recovered {recoveries}/{error_episodes} errors",
            ci=ci,
        )

    def compute_efficiency(self, steps: list, max_steps: int, task_completed: bool) -> EfficiencyScore:
        """Goal progress per unit resource (tokens, steps)."""
        n = len(steps)
        total_tokens = sum(
            s.get("input_tokens", 0) + s.get("output_tokens", 0) for s in steps
        )
        tokens_per_step = round(total_tokens / max(n, 1), 2)
        step_efficiency = max(0.0, round(1 - n / max(max_steps, 1), 4))
        value = round(step_efficiency * (1.0 if task_completed else 0.5), 4)
        # CI: treat step_efficiency as proportion-like in [0,1]; approximate using Wilson
        effective_n = max(max_steps, 1)
        effective_k = round(step_efficiency * effective_n)
        ci = self.wilson_ci(effective_k, effective_n)
        return EfficiencyScore(
            value=value,
            tokens_per_step=tokens_per_step,
            steps_to_completion=n,
            max_steps=max_steps,
            step_efficiency=step_efficiency,
            grade=self.grade_metric(value),
            interpretation=f"Used {n}/{max_steps} steps",
            ci=ci,
        )

    def compute_generalization(self, benchmark_scores: dict) -> GeneralizationScore:
        """Cross-distribution performance consistency (IRT-inspired, low CV = high generalization)."""
        scores = list(benchmark_scores.values())
        if not scores:
            return GeneralizationScore(0.5, 0, 0.0, 0.0, 0.0, 0.0, "No data", "D",
                                       ci=ConfidenceInterval(0.0, 1.0))
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / max(len(scores) - 1, 1)
        std = math.sqrt(variance)
        cv = std / mean if mean > 0 else 1.0
        value = round(max(0.0, min(1.0, 1 - cv)), 4)
        # Bootstrap-style CI: ±1.96 * std / sqrt(n) on mean, propagated through 1-CV
        n = len(scores)
        sem = std / math.sqrt(n) if n > 1 else 0.0
        ci_half = round(1.96 * sem / max(mean, 1e-9), 4)
        ci = ConfidenceInterval(
            lower=round(max(0.0, value - ci_half), 4),
            upper=round(min(1.0, value + ci_half), 4),
        )
        return GeneralizationScore(
            value=value,
            benchmarks_evaluated=len(scores),
            score_variance=round(variance, 4),
            worst_score=round(min(scores), 4),
            best_score=round(max(scores), 4),
            coefficient_of_variation=round(cv, 4),
            grade=self.grade_metric(value),
            interpretation=f"CV={cv:.3f}",
            ci=ci,
        )

    # ── Per-capability metric breakdown ───────────────────────────────────────

    def compute_by_capability(self, steps: list, max_steps: int, task_completed: bool) -> list[CapabilityBreakdown]:
        """Group steps by their 'capability' field and compute frontier metrics per capability."""
        by_cap: dict[str, list] = {}
        for s in steps:
            cap = s.get("capability", "general")
            by_cap.setdefault(cap, []).append(s)

        breakdowns = []
        for cap, cap_steps in by_cap.items():
            n = len(cap_steps)
            cap_max = max(max_steps * n // max(len(steps), 1), 1)
            auto = self.compute_autonomy(cap_steps)
            adap = self.compute_adaptivity(cap_steps)
            eff = self.compute_efficiency(cap_steps, cap_max, task_completed)
            composite = round(0.3 * auto.value + 0.3 * adap.value + 0.4 * eff.value, 4)
            breakdowns.append(CapabilityBreakdown(
                capability=cap,
                autonomy=auto.value,
                adaptivity=adap.value,
                efficiency=eff.value,
                composite=composite,
                n_steps=n,
            ))
        breakdowns.sort(key=lambda b: b.composite, reverse=True)
        return breakdowns

    # ── Metric correlation analysis ───────────────────────────────────────────

    @staticmethod
    def compute_correlations(results: list[FrontierMetricsResult]) -> MetricCorrelations:
        """
        Compute pairwise Pearson correlations between the 4 frontier metrics across a
        collection of FrontierMetricsResult objects.
        """
        def _pearson(xs: list[float], ys: list[float]) -> float:
            n = len(xs)
            if n < 2:
                return 0.0
            mx = sum(xs) / n
            my = sum(ys) / n
            num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
            denom = math.sqrt(
                sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)
            )
            return round(num / denom, 4) if denom > 1e-12 else 0.0

        auto_vals = [r.autonomy.value for r in results]
        adap_vals = [r.adaptivity.value for r in results]
        eff_vals = [r.efficiency.value for r in results]
        gen_vals = [r.generalization.value for r in results]

        corrs = {
            "autonomy_adaptivity": _pearson(auto_vals, adap_vals),
            "autonomy_efficiency": _pearson(auto_vals, eff_vals),
            "autonomy_generalization": _pearson(auto_vals, gen_vals),
            "adaptivity_efficiency": _pearson(adap_vals, eff_vals),
            "adaptivity_generalization": _pearson(adap_vals, gen_vals),
            "efficiency_generalization": _pearson(eff_vals, gen_vals),
        }

        # Describe dominant correlation
        max_pair = max(corrs, key=lambda k: abs(corrs[k]))
        max_r = corrs[max_pair]
        if abs(max_r) >= 0.7:
            interp = f"Strong correlation between {max_pair.replace('_', ' & ')} (r={max_r:.2f})"
        elif abs(max_r) >= 0.4:
            interp = f"Moderate correlation between {max_pair.replace('_', ' & ')} (r={max_r:.2f})"
        else:
            interp = "Metrics are largely independent — measuring distinct capabilities"

        return MetricCorrelations(**corrs, interpretation=interp)

    # ── Full computation ──────────────────────────────────────────────────────

    def compute_all(
        self,
        model_name: str,
        steps: list,
        benchmark_scores: dict,
        capability_score: float,
        propensity_score: float,
        safety_score: float,
        max_steps: int,
        task_completed: bool,
    ) -> FrontierMetricsResult:
        auto = self.compute_autonomy(steps)
        adap = self.compute_adaptivity(steps)
        eff = self.compute_efficiency(steps, max_steps, task_completed)
        gen = self.compute_generalization(benchmark_scores)
        composite = round(0.3 * auto.value + 0.3 * adap.value + 0.2 * eff.value + 0.2 * gen.value, 4)
        grade = self.grade_metric(composite)
        breakdown = self.compute_by_capability(steps, max_steps, task_completed)
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
            capability_breakdown=breakdown,
        )
