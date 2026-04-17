"""Cross-Benchmark Normalization — z-score normalization and generalization metrics."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class NormalizedScore:
    model_name: str; benchmark_name: str
    raw_score: float; z_score: float
    percentile_rank: float; n_models_in_comparison: int

@dataclass
class TransferScore:
    model_name: str; source_benchmark: str; target_benchmark: str
    source_score: float; target_score: float
    transfer_coefficient: float; generalization_gap: float; interpretation: str

@dataclass
class GeneralizationReport:
    model_name: str; domain: str; benchmarks_evaluated: list
    scores: dict; mean_score: float; score_variance: float
    generalization_index: float; worst_benchmark: str; best_benchmark: str
    transfer_scores: list

def _mean(v): return sum(v)/max(len(v),1)
def _std(v):
    m = _mean(v)
    return math.sqrt(sum((x-m)**2 for x in v)/max(len(v)-1,1))

def z_normalize(scores: dict) -> dict:
    vals = list(scores.values())
    m, s = _mean(vals), _std(vals)
    if s == 0: return {k: 0.0 for k in scores}
    return {k: round((v-m)/s, 4) for k,v in scores.items()}

def percentile_rank(score: float, all_scores: list) -> float:
    n = len(all_scores)
    if n == 0: return 50.0
    return round(sum(1 for s in all_scores if s <= score) / n * 100, 2)

def pearson_correlation(x: list, y: list) -> float:
    n = len(x)
    if n < 2: return 0.0
    mx, my = _mean(x), _mean(y)
    num = sum((xi-mx)*(yi-my) for xi,yi in zip(x,y))
    den = math.sqrt(sum((xi-mx)**2 for xi in x) * sum((yi-my)**2 for yi in y))
    return round(num/den, 4) if den else 0.0

def generalization_index(scores: list) -> float:
    if not scores: return 0.5
    m = _mean(scores)
    if m == 0: return 0.0
    cv = _std(scores) / m
    return round(max(0.0, min(1.0, 1 - cv)), 4)

class CrossBenchmarkAnalyzer:
    def normalize_scores(self, runs: list) -> list:
        by_bench = {}
        for r in runs:
            by_bench.setdefault(r["benchmark_name"], []).append(r["score"])
        result = []
        for r in runs:
            bench_scores = by_bench[r["benchmark_name"]]
            zs = z_normalize({str(i): s for i,s in enumerate(bench_scores)})
            idx = bench_scores.index(r["score"])
            z = list(zs.values())[idx]
            pr = percentile_rank(r["score"], bench_scores)
            result.append(NormalizedScore(model_name=r["model_name"], benchmark_name=r["benchmark_name"],
                raw_score=r["score"], z_score=z, percentile_rank=pr, n_models_in_comparison=len(bench_scores)))
        return result

    def compute_transfer_scores(self, runs: list, capability_mapping=None) -> list:
        by_model = {}
        for r in runs:
            by_model.setdefault(r["model_name"], {})[r["benchmark_name"]] = r["score"]
        results = []
        for model, bench_scores in by_model.items():
            benches = list(bench_scores.keys())
            for i in range(len(benches)):
                for j in range(i+1, len(benches)):
                    src, tgt = benches[i], benches[j]
                    coeff = abs(bench_scores[src] - bench_scores[tgt])
                    gap = abs(bench_scores[src] - bench_scores[tgt])
                    results.append(TransferScore(model_name=model, source_benchmark=src, target_benchmark=tgt,
                        source_score=bench_scores[src], target_score=bench_scores[tgt],
                        transfer_coefficient=round(1-coeff,4), generalization_gap=round(gap,4),
                        interpretation="consistent" if gap < 0.1 else "variable"))
        return results

    def generate_report(self, model_name: str, runs: list, capability_mapping=None) -> GeneralizationReport:
        model_runs = [r for r in runs if r["model_name"] == model_name]
        scores = {r["benchmark_name"]: r["score"] for r in model_runs}
        vals = list(scores.values())
        mean_s = _mean(vals) if vals else 0.0
        var = sum((v-mean_s)**2 for v in vals)/max(len(vals)-1,1) if len(vals)>1 else 0.0
        gi = generalization_index(vals)
        worst = min(scores, key=scores.get) if scores else ""
        best = max(scores, key=scores.get) if scores else ""
        return GeneralizationReport(model_name=model_name, domain="all",
            benchmarks_evaluated=list(scores.keys()), scores=scores,
            mean_score=round(mean_s,4), score_variance=round(var,4),
            generalization_index=gi, worst_benchmark=worst, best_benchmark=best,
            transfer_scores=self.compute_transfer_scores(model_runs))
