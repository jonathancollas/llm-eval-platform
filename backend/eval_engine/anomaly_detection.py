"""
Anomaly Detection Engine — Score & Performance Monitoring (#114 PR2)
====================================================================
Detects statistical anomalies in evaluation score distributions and
alerts on unexpected performance changes between model versions/runs.

Scientific grounding:
  "Make Mercury the place where new safety science is discovered."
  — INESIA Research OS

Capabilities:
  1. Score distribution anomaly detection
     - Suspiciously uniform score distributions (possible judge gaming)
     - Impossible scores (outside [0, 1] range after normalisation)
     - Bimodal collapse (all scores near 0 or 1 — loss of discrimination)
  2. Performance spike/drop alerting
     - Unexpected score changes between successive runs
     - Cross-model regression detection
  3. Novel failure pattern alerting
     - Clusters not seen in any previous run (uses failure_clustering)
"""
from __future__ import annotations

import math
import logging
import statistics
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class ScoreAnomalyAlert:
    alert_id: str
    alert_type: str           # "uniform_scores" | "impossible_scores" | "bimodal_collapse" | "score_spike" | "score_drop"
    severity: str             # "low" | "medium" | "high" | "critical"
    description: str
    model_name: str
    campaign_id: int
    metric_value: float       # The anomalous metric (e.g. std_dev, delta)
    threshold: float          # The threshold that was exceeded
    affected_count: int       # Number of affected scores
    recommendation: str


@dataclass
class PerformanceAlert:
    alert_id: str
    alert_type: str           # "regression" | "improvement" | "novel_cluster"
    severity: str
    description: str
    model_name: str
    benchmark: str
    baseline_score: float
    current_score: float
    delta: float
    recommendation: str


@dataclass
class AnomalyReport:
    campaign_id: int
    model_name: str
    n_scores: int
    score_alerts: list[ScoreAnomalyAlert]
    performance_alerts: list[PerformanceAlert]
    novel_pattern_alerts: list[str]
    summary: str
    is_clean: bool            # True if no anomalies detected


# ── Statistical helpers ───────────────────────────────────────────────────────

def _safe_stdev(scores: list[float]) -> float:
    if len(scores) < 2:
        return 0.0
    return statistics.stdev(scores)


def _safe_mean(scores: list[float]) -> float:
    if not scores:
        return 0.0
    return statistics.mean(scores)


def _entropy(scores: list[float], bins: int = 10) -> float:
    """Shannon entropy of score distribution — low = suspicious uniformity."""
    if len(scores) < 2:
        return 0.0
    bin_size = 1.0 / bins
    counts = [0] * bins
    for s in scores:
        idx = min(int(s / bin_size), bins - 1)
        counts[idx] += 1
    n = len(scores)
    ent = 0.0
    for c in counts:
        if c > 0:
            p = c / n
            ent -= p * math.log2(p)
    return ent


# ── Anomaly detection engine ─────────────────────────────────────────────────

class AnomalyDetectionEngine:
    """
    Detects statistical anomalies in LLM evaluation scores.

    Parameters
    ----------
    uniform_entropy_threshold : float
        If the Shannon entropy of the score distribution is below this value,
        scores are flagged as suspiciously uniform (possible judge gaming).
        Default: 0.5 (0 = fully uniform, log2(bins)=3.32 = fully random).
    bimodal_extreme_ratio : float
        If the proportion of scores at extremes (< 0.1 or > 0.9) exceeds this,
        flag as bimodal collapse. Default: 0.85.
    spike_threshold : float
        Minimum absolute score change (0-1) to trigger a spike/drop alert.
        Default: 0.15 (15 percentage points).
    min_scores : int
        Minimum number of scores required for meaningful analysis. Default: 5.
    """

    def __init__(
        self,
        uniform_entropy_threshold: float = 0.5,
        bimodal_extreme_ratio: float = 0.85,
        spike_threshold: float = 0.15,
        min_scores: int = 5,
    ):
        self.uniform_entropy_threshold = uniform_entropy_threshold
        self.bimodal_extreme_ratio = bimodal_extreme_ratio
        self.spike_threshold = spike_threshold
        self.min_scores = min_scores

    # ── Public API ────────────────────────────────────────────────────────────

    def analyse_score_distribution(
        self,
        scores: list[float],
        campaign_id: int = 0,
        model_name: str = "unknown",
    ) -> list[ScoreAnomalyAlert]:
        """
        Detect statistical anomalies in a score distribution.

        Returns a list of alerts (empty = clean distribution).
        """
        alerts: list[ScoreAnomalyAlert] = []
        if len(scores) < self.min_scores:
            return alerts

        # 1. Impossible scores
        impossible = [s for s in scores if s < 0.0 or s > 1.0]
        if impossible:
            alerts.append(ScoreAnomalyAlert(
                alert_id=f"impossible_{campaign_id}_{model_name}",
                alert_type="impossible_scores",
                severity="critical",
                description=(
                    f"{len(impossible)} score(s) outside valid [0, 1] range "
                    f"detected for '{model_name}'. "
                    f"Min={min(impossible):.3f}, Max={max(impossible):.3f}."
                ),
                model_name=model_name,
                campaign_id=campaign_id,
                metric_value=max(abs(min(impossible)), abs(max(impossible) - 1.0)),
                threshold=0.0,
                affected_count=len(impossible),
                recommendation=(
                    "Investigate the scoring pipeline — normalisation may be broken. "
                    "Do not include these results in benchmarks until corrected."
                ),
            ))

        valid_scores = [s for s in scores if 0.0 <= s <= 1.0]
        if len(valid_scores) < self.min_scores:
            return alerts

        # 2. Suspiciously uniform scores (low entropy → judge may be anchored)
        ent = _entropy(valid_scores)
        if ent < self.uniform_entropy_threshold:
            stdev = _safe_stdev(valid_scores)
            severity = "high" if ent < self.uniform_entropy_threshold / 2 else "medium"
            alerts.append(ScoreAnomalyAlert(
                alert_id=f"uniform_{campaign_id}_{model_name}",
                alert_type="uniform_scores",
                severity=severity,
                description=(
                    f"Score distribution for '{model_name}' is suspiciously uniform "
                    f"(entropy={ent:.3f}, stdev={stdev:.3f}). "
                    "This may indicate judge anchoring, scoring collapse, or eval contamination."
                ),
                model_name=model_name,
                campaign_id=campaign_id,
                metric_value=ent,
                threshold=self.uniform_entropy_threshold,
                affected_count=len(valid_scores),
                recommendation=(
                    "Review judge prompts for anchoring bias. "
                    "Run the same benchmark with a different judge model to compare distributions."
                ),
            ))

        # 3. Bimodal collapse (all scores at extremes — judge lost discrimination)
        extremes = [s for s in valid_scores if s < 0.1 or s > 0.9]
        extreme_ratio = len(extremes) / len(valid_scores)
        if extreme_ratio > self.bimodal_extreme_ratio:
            alerts.append(ScoreAnomalyAlert(
                alert_id=f"bimodal_{campaign_id}_{model_name}",
                alert_type="bimodal_collapse",
                severity="medium",
                description=(
                    f"{extreme_ratio:.0%} of scores for '{model_name}' are at extremes "
                    f"(< 0.1 or > 0.9). The judge has lost discriminative ability — "
                    "nuanced failures may be invisible."
                ),
                model_name=model_name,
                campaign_id=campaign_id,
                metric_value=extreme_ratio,
                threshold=self.bimodal_extreme_ratio,
                affected_count=len(extremes),
                recommendation=(
                    "Recalibrate the judge rubric. Consider adding mid-range calibration "
                    "examples to the judge prompt."
                ),
            ))

        return alerts

    def detect_performance_changes(
        self,
        baseline_scores: dict[str, float],   # {benchmark_name: mean_score}
        current_scores: dict[str, float],
        model_name: str = "unknown",
        campaign_id: int = 0,
    ) -> list[PerformanceAlert]:
        """
        Compare current scores against a baseline.

        Returns alerts for significant regressions or unexpected improvements.
        """
        alerts: list[PerformanceAlert] = []
        common_benchmarks = set(baseline_scores) & set(current_scores)

        for bench in sorted(common_benchmarks):
            baseline = baseline_scores[bench]
            current = current_scores[bench]
            delta = current - baseline

            if abs(delta) < self.spike_threshold:
                continue

            is_regression = delta < 0
            alert_type = "regression" if is_regression else "improvement"
            severity = (
                "critical" if abs(delta) > 0.3
                else "high" if abs(delta) > 0.2
                else "medium"
            )

            alerts.append(PerformanceAlert(
                alert_id=f"perf_{alert_type}_{campaign_id}_{model_name}_{bench}",
                alert_type=alert_type,
                severity=severity,
                description=(
                    f"{'Regression' if is_regression else 'Improvement'} detected on "
                    f"'{bench}' for '{model_name}': "
                    f"{baseline:.3f} → {current:.3f} (Δ={delta:+.3f})."
                ),
                model_name=model_name,
                benchmark=bench,
                baseline_score=baseline,
                current_score=current,
                delta=delta,
                recommendation=(
                    f"Investigate {'capability regression' if is_regression else 'unexpected score increase'} "
                    f"on {bench}. "
                    + ("A score drop of this magnitude may indicate model drift, data contamination, "
                       "or a change in the scoring rubric." if is_regression
                       else "An unusually large improvement may indicate eval contamination or rubric changes.")
                ),
            ))

        return alerts

    def analyse_run(
        self,
        scores: list[float],
        campaign_id: int = 0,
        model_name: str = "unknown",
        baseline_scores: Optional[dict[str, float]] = None,
        current_scores: Optional[dict[str, float]] = None,
        novel_pattern_alerts: Optional[list[str]] = None,
    ) -> AnomalyReport:
        """
        Full anomaly analysis for a single evaluation run.

        Returns an AnomalyReport with all detected issues.
        """
        score_alerts = self.analyse_score_distribution(scores, campaign_id, model_name)

        perf_alerts: list[PerformanceAlert] = []
        if baseline_scores and current_scores:
            perf_alerts = self.detect_performance_changes(
                baseline_scores, current_scores, model_name, campaign_id
            )

        novel = novel_pattern_alerts or []

        all_clean = not score_alerts and not perf_alerts and not novel

        # Build summary
        parts: list[str] = []
        if score_alerts:
            critical = [a for a in score_alerts if a.severity == "critical"]
            parts.append(
                f"{len(score_alerts)} score distribution alert(s)"
                + (f" including {len(critical)} critical" if critical else "")
                + "."
            )
        if perf_alerts:
            regressions = [a for a in perf_alerts if a.alert_type == "regression"]
            parts.append(
                f"{len(perf_alerts)} performance change alert(s)"
                + (f", {len(regressions)} regression(s)" if regressions else "")
                + "."
            )
        if novel:
            parts.append(f"{len(novel)} novel failure pattern alert(s) require human validation.")

        summary = " ".join(parts) if parts else "No anomalies detected."

        return AnomalyReport(
            campaign_id=campaign_id,
            model_name=model_name,
            n_scores=len(scores),
            score_alerts=score_alerts,
            performance_alerts=perf_alerts,
            novel_pattern_alerts=novel,
            summary=summary,
            is_clean=all_clean,
        )
