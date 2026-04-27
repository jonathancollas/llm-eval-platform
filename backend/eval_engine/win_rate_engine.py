"""
Win Rate Engine (#88 — engine-driven refactor)
===============================================
Pairwise win rate computation, extracted from api/routers/results.py.
"""
from dataclasses import dataclass
from typing import Any


@dataclass
class WinRateRow:
    model_name: str
    wins: int
    losses: int
    ties: int
    win_rate: float


def compute_win_rates(
    runs: list[Any],
    models: dict,
    benches: dict,
) -> list[WinRateRow]:
    """
    Pairwise win rate across all model pairs per benchmark.

    Args:
        runs: EvalRun objects (.status, .score, .model_id, .benchmark_id)
        models: {model_id → LLMModel}
        benches: {benchmark_id → Benchmark}
    """
    from core.models import JobStatus

    by_bench: dict[int, list] = {}
    for r in runs:
        if r.status == JobStatus.COMPLETED and r.score is not None:
            by_bench.setdefault(r.benchmark_id, []).append(r)

    win_count: dict[int, dict] = {}
    for bench_runs in by_bench.values():
        for i, r1 in enumerate(bench_runs):
            for r2 in bench_runs[i + 1:]:
                for mid in (r1.model_id, r2.model_id):
                    win_count.setdefault(mid, {"wins": 0, "losses": 0, "ties": 0})
                if r1.score > r2.score:
                    win_count[r1.model_id]["wins"]   += 1
                    win_count[r2.model_id]["losses"] += 1
                elif r2.score > r1.score:
                    win_count[r2.model_id]["wins"]   += 1
                    win_count[r1.model_id]["losses"] += 1
                else:
                    win_count[r1.model_id]["ties"] += 1
                    win_count[r2.model_id]["ties"] += 1

    rows = []
    for model_id, counts in win_count.items():
        total = counts["wins"] + counts["losses"] + counts["ties"]
        m = models.get(model_id)
        name = m.name if m else str(model_id)
        rows.append(WinRateRow(
            model_name=name,
            wins=counts["wins"],
            losses=counts["losses"],
            ties=counts["ties"],
            win_rate=round(counts["wins"] / total, 4) if total else 0.0,
        ))
    return sorted(rows, key=lambda x: x.win_rate, reverse=True)
