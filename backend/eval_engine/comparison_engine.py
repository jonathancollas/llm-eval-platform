"""
System Comparison Engine (#88 — engine-driven refactor)
=========================================================
Extracted from api/routers/results.py for testability.
Compares two campaigns, detects regressions and improvements.
"""
from dataclasses import dataclass, field


@dataclass
class ComparisonEntry:
    key: str
    model: str
    benchmark: str
    baseline_score: float | None
    candidate_score: float | None
    delta: float
    pct_change: float
    direction: str   # improved | regressed | stable


@dataclass
class ComparisonReport:
    baseline_id: int
    baseline_name: str
    candidate_id: int
    candidate_name: str
    total_comparisons: int
    regressions: list[ComparisonEntry]
    improvements: list[ComparisonEntry]
    stable: int
    avg_delta: float
    overall: str   # regression | improvement | stable
    all_comparisons: list[ComparisonEntry]


def compare_campaigns(
    baseline_runs: dict,
    candidate_runs: dict,
    baseline_id: int,
    candidate_id: int,
    baseline_name: str,
    candidate_name: str,
    regression_threshold: float = 0.05,
    improvement_threshold: float = 0.05,
) -> ComparisonReport:
    """
    Compare two sets of evaluation runs.

    Args:
        baseline_runs / candidate_runs: {key → {"score": float, "model": str, "benchmark": str}}
        regression_threshold: delta below which → regression
        improvement_threshold: delta above which → improvement
    """
    comparisons: list[ComparisonEntry] = []
    regressions: list[ComparisonEntry] = []
    improvements: list[ComparisonEntry] = []

    for key in sorted(set(baseline_runs) | set(candidate_runs)):
        b = baseline_runs.get(key)
        c = candidate_runs.get(key)
        if not b or not c:
            continue

        b_score = b.get("score") or 0.0
        c_score = c.get("score") or 0.0
        delta = c_score - b_score
        pct_change = (delta / max(b_score, 0.001)) * 100

        direction = (
            "improved"  if delta >  improvement_threshold else
            "regressed" if delta < -regression_threshold  else
            "stable"
        )

        entry = ComparisonEntry(
            key=key,
            model=b["model"],
            benchmark=b["benchmark"],
            baseline_score=b_score,
            candidate_score=c_score,
            delta=round(delta, 4),
            pct_change=round(pct_change, 1),
            direction=direction,
        )
        comparisons.append(entry)
        if direction == "regressed":
            regressions.append(entry)
        elif direction == "improved":
            improvements.append(entry)

    avg_delta = (
        sum(e.delta for e in comparisons) / len(comparisons)
        if comparisons else 0.0
    )
    overall = (
        "regression"  if avg_delta < -0.02 else
        "improvement" if avg_delta >  0.02 else
        "stable"
    )

    return ComparisonReport(
        baseline_id=baseline_id,
        baseline_name=baseline_name,
        candidate_id=candidate_id,
        candidate_name=candidate_name,
        total_comparisons=len(comparisons),
        regressions=regressions,
        improvements=improvements,
        stable=len(comparisons) - len(regressions) - len(improvements),
        avg_delta=round(avg_delta, 4),
        overall=overall,
        all_comparisons=comparisons,
    )
