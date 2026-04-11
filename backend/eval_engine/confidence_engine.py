"""
Confidence Calibration Engine (#88 — engine-driven refactor)
==============================================================
Extracted from api/routers/results.py for testability.

Scientific grounding:
  - Bootstrap confidence intervals (Efron & Tibshirani, 1993)
  - Wilson score interval for binomial proportions (Wilson, 1927)
"""
from __future__ import annotations
import math
import random
from dataclasses import dataclass


@dataclass
class ConfidenceResult:
    run_id: int
    n_items: int
    score_mean: float
    score_std_dev: float
    score_variance: float
    ci_lower: float
    ci_upper: float
    ci_width: float
    wilson_lower: float
    wilson_upper: float
    reliability_grade: str   # A | B | C | D
    reliability_label: str
    recommendation: str


def compute_confidence(run_id: int, scores: list[float]) -> ConfidenceResult:
    """
    Bootstrap 95% CI + Wilson score interval for an eval run.

    Args:
        run_id: EvalRun PK (reference only)
        scores: Per-item scores (0.0–1.0)
    """
    n = len(scores)
    if n == 0:
        raise ValueError("No scores provided.")

    mean = sum(scores) / n
    variance = sum((s - mean) ** 2 for s in scores) / max(n - 1, 1)
    std_dev = math.sqrt(variance)

    # Bootstrap 95% CI — 1000 resamples, seeded for reproducibility
    rng = random.Random(42)
    bootstrap = sorted(
        sum(rng.choice(scores) for _ in range(n)) / n
        for _ in range(1000)
    )
    ci_lower = bootstrap[25]   # 2.5th percentile
    ci_upper = bootstrap[975]  # 97.5th percentile

    # Wilson score CI
    z = 1.96
    denom = 1 + z ** 2 / n
    center = (mean + z ** 2 / (2 * n)) / denom
    margin = z * math.sqrt(mean * (1 - mean) / n + z ** 2 / (4 * n ** 2)) / denom
    wilson_lower = max(0.0, center - margin)
    wilson_upper = min(1.0, center + margin)

    # Reliability grade
    if n >= 100 and std_dev < 0.15:
        grade, label = "A", "High reliability — large sample, low variance"
    elif n >= 50 and std_dev < 0.25:
        grade, label = "B", "Moderate reliability — sufficient sample size"
    elif n >= 20:
        grade, label = "C", "Low reliability — small sample, consider expanding"
    else:
        grade, label = "D", "Insufficient data — results not statistically robust"

    rec = (
        f"Expand to {max(100, n * 2)} samples for grade A reliability."
        if grade in ("C", "D")
        else "Sample size is adequate for this confidence level."
    )

    return ConfidenceResult(
        run_id=run_id,
        n_items=n,
        score_mean=round(mean, 4),
        score_std_dev=round(std_dev, 4),
        score_variance=round(variance, 4),
        ci_lower=round(ci_lower, 4),
        ci_upper=round(ci_upper, 4),
        ci_width=round(ci_upper - ci_lower, 4),
        wilson_lower=round(wilson_lower, 4),
        wilson_upper=round(wilson_upper, 4),
        reliability_grade=grade,
        reliability_label=label,
        recommendation=rec,
    )
