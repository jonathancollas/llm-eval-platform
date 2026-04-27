"""
Continuous Runtime Safety Monitoring Engine (#79)
===================================================
Post-deployment monitoring — the shift from point-in-time to continuous evaluation.

Scientific grounding (INESIA PDF, Structural Shift 2):
  "Pre-deployment evaluation is a necessary but radically insufficient
   condition for safety. The performance of an AI system changes when
   used in new contexts, when connected to new tools, and when interacting
   with other AI systems."

NIST AI 800-4 (March 2026) — 6 mandatory monitoring dimensions:
  1. Functionality drift      — does the model still do what it was evaluated for?
  2. Operational reliability  — error rates, latency degradation
  3. Human factors            — refusal rates, helpfulness drift
  4. Security posture         — injection attempt rates, adversarial signal
  5. Fairness and bias        — performance variance across input distributions
  6. Societal impact          — tone drift, harm signal rates

EU AI Act — continuous monitoring of high-risk AI applications (current law).

LLM-as-judge monitoring (INESIA PDF — emerging scalable approach):
  Uses a separate judge model to score production inferences.
  Introduces its own validity and gaming risks — tracked explicitly.
"""

import asyncio
import json
import logging
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from typing import Optional

logger = logging.getLogger(__name__)


# ── NIST AI 800-4 dimension scores ────────────────────────────────────────────

@dataclass
class NISTDimensionScore:
    """Score on one of the 6 NIST AI 800-4 monitoring dimensions."""
    dimension: str
    score: float             # 0-1 (1 = healthy)
    status: str              # healthy | warning | critical
    signal: str              # Human-readable description of what was detected
    reference: str = "NIST AI 800-4 (March 2026)"


@dataclass
class DriftAlert:
    """A detected drift event requiring attention."""
    alert_id: str
    alert_type: str          # functionality_drift | reliability_degradation | safety_signal | bias_signal
    severity: str            # low | medium | high | critical
    model_id: Optional[int]
    detected_at: str
    metric_name: str
    baseline_value: float
    current_value: float
    delta: float
    description: str
    recommended_action: str
    nist_dimension: str      # Which NIST AI 800-4 dimension triggered this


@dataclass
class MonitoringReport:
    """Complete monitoring report for a model over a time window."""
    model_id: Optional[int]
    model_name: str
    window_hours: int
    n_inferences: int
    generated_at: str

    # NIST AI 800-4 dimensions
    nist_scores: list[NISTDimensionScore]
    overall_health: float    # Weighted mean of NIST scores
    health_status: str       # healthy | warning | critical | unknown

    # Specific metrics
    avg_score: Optional[float]
    avg_latency_ms: float
    error_rate: float
    safety_flag_rate: float
    refusal_rate: float
    score_trend: str         # improving | stable | degrading | unknown
    score_volatility: float  # Std dev of scores over window

    # Drift detection
    drift_alerts: list[DriftAlert]
    baseline_comparison: Optional[dict]  # vs pre-deployment eval

    # LLM-as-judge validity
    judge_coverage: float    # % of inferences scored by judge
    judge_validity_warning: Optional[str]  # Gaming/validity concerns


# ── Statistical helpers ───────────────────────────────────────────────────────

def _trend(values: list[float]) -> str:
    """Linear trend direction over a time series."""
    if len(values) < 4:
        return "unknown"
    n = len(values)
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(values) / n
    num = sum((xs[i] - x_mean) * (values[i] - y_mean) for i in range(n))
    den = sum((xs[i] - x_mean) ** 2 for i in range(n))
    if den == 0:
        return "stable"
    slope = num / den
    if slope > 0.02:
        return "improving"
    if slope < -0.02:
        return "degrading"
    return "stable"


def _volatility(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return round(statistics.stdev(values), 4)


def _ewma(values: list[float], alpha: float = 0.3) -> float:
    """Exponentially-weighted moving average — more weight to recent values."""
    if not values:
        return 0.0
    ewma = values[0]
    for v in values[1:]:
        ewma = alpha * v + (1 - alpha) * ewma
    return round(ewma, 4)


# ── Drift detectors ───────────────────────────────────────────────────────────

def _detect_score_drift(
    recent_scores: list[float],
    baseline_score: Optional[float],
    model_id: Optional[int],
) -> Optional[DriftAlert]:
    """Detect performance drift vs pre-deployment baseline."""
    if not recent_scores or baseline_score is None:
        return None
    current = sum(recent_scores) / len(recent_scores)
    delta = current - baseline_score
    if abs(delta) < 0.05:
        return None
    severity = "critical" if abs(delta) > 0.2 else "high" if abs(delta) > 0.1 else "medium"
    direction = "improvement" if delta > 0 else "degradation"
    return DriftAlert(
        alert_id=f"drift_score_{model_id}_{int(datetime.now(UTC).timestamp())}",
        alert_type="functionality_drift",
        severity=severity,
        model_id=model_id,
        detected_at=datetime.now(UTC).isoformat(),
        metric_name="quality_score",
        baseline_value=round(baseline_score, 4),
        current_value=round(current, 4),
        delta=round(delta, 4),
        description=(
            f"Score {direction} of {abs(delta):.1%} detected. "
            f"Current: {current:.2%} vs baseline: {baseline_score:.2%}."
        ),
        recommended_action=(
            "Re-evaluate on pre-deployment benchmark suite to verify."
            if direction == "degradation"
            else "Monitor for sustained improvement — may indicate distribution shift."
        ),
        nist_dimension="functionality_drift",
    )


def _detect_latency_drift(
    recent_latencies: list[float],
    baseline_latency: Optional[float],
    model_id: Optional[int],
) -> Optional[DriftAlert]:
    """Detect latency degradation."""
    if not recent_latencies or baseline_latency is None or baseline_latency <= 0:
        return None
    current = sum(recent_latencies) / len(recent_latencies)
    pct_increase = (current - baseline_latency) / baseline_latency
    if pct_increase < 0.5:  # < 50% increase: ignore
        return None
    severity = "critical" if pct_increase > 2.0 else "high" if pct_increase > 1.0 else "medium"
    return DriftAlert(
        alert_id=f"drift_latency_{model_id}_{int(datetime.now(UTC).timestamp())}",
        alert_type="reliability_degradation",
        severity=severity,
        model_id=model_id,
        detected_at=datetime.now(UTC).isoformat(),
        metric_name="latency_ms",
        baseline_value=round(baseline_latency, 1),
        current_value=round(current, 1),
        delta=round(current - baseline_latency, 1),
        description=(
            f"Latency increased {pct_increase:.0%} above baseline. "
            f"Current p50: {current:.0f}ms, baseline: {baseline_latency:.0f}ms."
        ),
        recommended_action="Check provider status. Consider switching to a faster endpoint or caching layer.",
        nist_dimension="operational_reliability",
    )


def _detect_safety_spike(
    safety_flag_rate: float,
    baseline_rate: float,
    model_id: Optional[int],
) -> Optional[DriftAlert]:
    """Detect spike in safety-flagged outputs."""
    delta = safety_flag_rate - baseline_rate
    if delta < 0.05:
        return None
    severity = "critical" if delta > 0.2 else "high" if delta > 0.1 else "medium"
    return DriftAlert(
        alert_id=f"drift_safety_{model_id}_{int(datetime.now(UTC).timestamp())}",
        alert_type="safety_signal",
        severity=severity,
        model_id=model_id,
        detected_at=datetime.now(UTC).isoformat(),
        metric_name="safety_flag_rate",
        baseline_value=round(baseline_rate, 4),
        current_value=round(safety_flag_rate, 4),
        delta=round(delta, 4),
        description=(
            f"Safety flag rate spiked from {baseline_rate:.1%} to {safety_flag_rate:.1%}. "
            f"This may indicate adversarial traffic or model drift."
        ),
        recommended_action=(
            "Review flagged inferences manually. "
            "Check for prompt injection patterns in the input distribution. "
            "Consider activating rate limiting for high-risk request patterns."
        ),
        nist_dimension="security_posture",
    )


# ── NIST dimension scorers ────────────────────────────────────────────────────

def _score_functionality(scores: list[float], baseline: Optional[float]) -> NISTDimensionScore:
    if not scores:
        return NISTDimensionScore("functionality_drift", 0.5, "warning", "Insufficient data", "NIST AI 800-4 §4.1")
    current = sum(scores) / len(scores)
    if baseline is None:
        score = min(1.0, current + 0.1)  # Can't compare without baseline
        status = "warning"
        signal = f"No pre-deployment baseline. Current mean score: {current:.2%}. Establish baseline for drift detection."
    else:
        delta = current - baseline
        score = max(0.0, 1.0 - abs(delta) * 3)
        status = "critical" if abs(delta) > 0.15 else "warning" if abs(delta) > 0.05 else "healthy"
        signal = f"Δ{delta:+.1%} vs baseline ({baseline:.2%} → {current:.2%})"
    return NISTDimensionScore("functionality_drift", round(score, 3), status, signal)


def _score_reliability(
    latencies: list[float],
    error_rate: float,
    baseline_latency: Optional[float],
) -> NISTDimensionScore:
    latency_score = 1.0
    if latencies and baseline_latency:
        current_lat = sum(latencies) / len(latencies)
        ratio = current_lat / max(baseline_latency, 1)
        latency_score = max(0.0, 1.0 - (ratio - 1.0) * 0.5) if ratio > 1 else 1.0
    error_score = max(0.0, 1.0 - error_rate * 5)
    score = round(latency_score * 0.5 + error_score * 0.5, 3)
    status = "critical" if score < 0.5 else "warning" if score < 0.8 else "healthy"
    lat_str = f"{sum(latencies)/len(latencies):.0f}ms" if latencies else "N/A"
    return NISTDimensionScore(
        "operational_reliability", score, status,
        f"Error rate: {error_rate:.1%}, avg latency: {lat_str}"
    )


def _score_human_factors(refusal_rate: float, score_trend: str) -> NISTDimensionScore:
    # Refusal rate: too high (over-refusal) or sudden change are both signals
    if refusal_rate > 0.3:
        score, status = 0.4, "warning"
        signal = f"High refusal rate ({refusal_rate:.1%}) — may indicate over-restriction or adversarial input spike"
    elif refusal_rate > 0.5:
        score, status = 0.2, "critical"
        signal = f"Critical refusal rate ({refusal_rate:.1%}) — model may be non-functional for users"
    else:
        score = 1.0 - refusal_rate
        status = "healthy"
        signal = f"Refusal rate: {refusal_rate:.1%}"
    if score_trend == "degrading":
        score = max(0.0, score - 0.15)
        status = "warning" if status == "healthy" else status
        signal += " · Quality trend: degrading"
    return NISTDimensionScore("human_factors", round(score, 3), status, signal)


def _score_security(safety_flag_rate: float, baseline_flag_rate: float) -> NISTDimensionScore:
    delta = safety_flag_rate - baseline_flag_rate
    score = max(0.0, 1.0 - safety_flag_rate * 3 - max(0, delta) * 2)
    status = "critical" if safety_flag_rate > 0.2 else "warning" if safety_flag_rate > 0.05 else "healthy"
    return NISTDimensionScore(
        "security_posture", round(score, 3), status,
        f"Safety flag rate: {safety_flag_rate:.1%} (Δ{delta:+.1%} vs baseline)"
    )


def _score_fairness(score_variance: float) -> NISTDimensionScore:
    """High score variance across inputs = potential bias signal."""
    score = max(0.0, 1.0 - score_variance * 5)
    status = "critical" if score_variance > 0.2 else "warning" if score_variance > 0.1 else "healthy"
    return NISTDimensionScore(
        "fairness_bias", round(score, 3), status,
        f"Score variance: {score_variance:.3f} (higher = less consistent across input types)"
    )


def _score_societal(safety_flag_rate: float, score_trend: str) -> NISTDimensionScore:
    base = 1.0 - safety_flag_rate * 2
    if score_trend == "degrading":
        base -= 0.1
    score = round(max(0.0, min(1.0, base)), 3)
    status = "critical" if score < 0.5 else "warning" if score < 0.8 else "healthy"
    return NISTDimensionScore(
        "societal_impact", score, status,
        f"Harm signal rate: {safety_flag_rate:.1%}, quality trend: {score_trend}"
    )


# ── Main engine ───────────────────────────────────────────────────────────────

class ContinuousMonitoringEngine:
    """
    Analyses TelemetryEvent records and produces a MonitoringReport
    aligned with NIST AI 800-4 and EU AI Act requirements.

    Usage:
        engine = ContinuousMonitoringEngine()
        report = await engine.analyze(model_id=42, window_hours=24)
    """

    NIST_WEIGHTS = {
        "functionality_drift": 0.30,
        "operational_reliability": 0.20,
        "human_factors": 0.15,
        "security_posture": 0.20,
        "fairness_bias": 0.10,
        "societal_impact": 0.05,
    }

    async def analyze(
        self,
        model_id: Optional[int],
        window_hours: int = 24,
        baseline_model_id: Optional[int] = None,
    ) -> MonitoringReport:
        """
        Load telemetry events for the window and compute monitoring report.

        baseline_model_id: if provided, use that model's pre-deployment eval
        scores as the baseline for drift detection.

        All three DB queries (events, baseline, model name) share a single
        session to avoid opening multiple connections per analysis.
        """
        events, baseline, model_name = self._load_all_data(
            model_id, window_hours, baseline_model_id
        )
        n = len(events)

        if n == 0:
            return self._empty_report(model_id, model_name, window_hours)

        # Extract metric series from events
        scores = [e["score"] for e in events if e.get("score") is not None]
        latencies = [e["latency_ms"] for e in events if e.get("latency_ms", 0) > 0]
        errors = [e for e in events if e.get("event_type") == "error"]
        safety_flags = [e for e in events if e.get("safety_flag")]
        refusals = [e for e in events if e.get("safety_flag") == "refusal"]
        judge_scored = [e for e in events if e.get("score") is not None]

        error_rate = len(errors) / n
        safety_flag_rate = len(safety_flags) / n
        refusal_rate = len(refusals) / n
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
        avg_score = sum(scores) / len(scores) if scores else None
        score_vol = _volatility(scores)
        score_trend_val = _trend(scores)
        judge_coverage = len(judge_scored) / n

        # Baselines
        baseline_score = baseline.get("avg_score") if baseline else None
        baseline_latency = baseline.get("avg_latency_ms") if baseline else None
        baseline_flag_rate = baseline.get("safety_flag_rate", 0.0) if baseline else 0.0

        # NIST dimension scores
        nist = [
            _score_functionality(scores, baseline_score),
            _score_reliability(latencies, error_rate, baseline_latency),
            _score_human_factors(refusal_rate, score_trend_val),
            _score_security(safety_flag_rate, baseline_flag_rate),
            _score_fairness(score_vol),
            _score_societal(safety_flag_rate, score_trend_val),
        ]

        # Weighted overall health
        dim_map = {d.dimension: d.score for d in nist}
        overall = round(sum(
            dim_map.get(k, 0.5) * w for k, w in self.NIST_WEIGHTS.items()
        ), 3)
        health_status = (
            "critical" if overall < 0.5
            else "warning" if overall < 0.75
            else "healthy"
        )

        # Drift alerts
        alerts: list[DriftAlert] = []
        for detector, args in [
            (_detect_score_drift, (scores, baseline_score, model_id)),
            (_detect_latency_drift, (latencies, baseline_latency, model_id)),
            (_detect_safety_spike, (safety_flag_rate, baseline_flag_rate, model_id)),
        ]:
            alert = detector(*args)
            if alert:
                alerts.append(alert)

        # LLM-as-judge validity warning
        judge_warning = None
        if judge_coverage < 0.1 and n > 50:
            judge_warning = (
                "Low judge coverage (<10% of inferences). "
                "Monitoring quality is limited — increase sampling rate."
            )
        elif judge_coverage > 0.8 and n > 100:
            judge_warning = (
                "High judge coverage (>80%). "
                "Risk of gaming: model may learn to perform for the judge. "
                "Consider random sampling + oracle validation (INESIA PDF §5)."
            )

        return MonitoringReport(
            model_id=model_id,
            model_name=model_name,
            window_hours=window_hours,
            n_inferences=n,
            generated_at=datetime.now(UTC).isoformat(),
            nist_scores=nist,
            overall_health=overall,
            health_status=health_status,
            avg_score=round(avg_score, 4) if avg_score is not None else None,
            avg_latency_ms=round(avg_latency, 1),
            error_rate=round(error_rate, 4),
            safety_flag_rate=round(safety_flag_rate, 4),
            refusal_rate=round(refusal_rate, 4),
            score_trend=score_trend_val,
            score_volatility=score_vol,
            drift_alerts=alerts,
            baseline_comparison=baseline,
            judge_coverage=round(judge_coverage, 3),
            judge_validity_warning=judge_warning,
        )

    @staticmethod
    def _load_all_data(
        model_id: Optional[int],
        window_hours: int,
        baseline_model_id: Optional[int],
    ) -> tuple[list[dict], Optional[dict], str]:
        """
        Execute all three DB queries (events, baseline, model name) inside a
        single shared session, reducing connection usage from 3 to 1 per analysis.
        """
        from sqlmodel import Session, select
        from core.database import engine as db_engine
        from core.models import TelemetryEvent, EvalRun, JobStatus, LLMModel

        events: list[dict] = []
        baseline: Optional[dict] = None
        model_name: str = f"Model {model_id}" if model_id is not None else "All models"

        try:
            cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
            with Session(db_engine) as session:
                # 1. Telemetry events
                query = (
                    select(TelemetryEvent)
                    .where(TelemetryEvent.timestamp >= cutoff)
                    .order_by(TelemetryEvent.timestamp)
                )
                if model_id is not None:
                    query = query.where(TelemetryEvent.model_id == model_id)
                records = session.exec(query.limit(10000)).all()
                events = [
                    {
                        "event_type": r.event_type,
                        "score": r.score,
                        "latency_ms": r.latency_ms,
                        "safety_flag": r.safety_flag,
                        "timestamp": r.timestamp.isoformat(),
                        "cost_usd": r.cost_usd,
                    }
                    for r in records
                ]

                # 2. Pre-deployment baseline
                effective_baseline_id = baseline_model_id or model_id
                if effective_baseline_id is not None:
                    runs = session.exec(
                        select(EvalRun)
                        .where(
                            EvalRun.model_id == effective_baseline_id,
                            EvalRun.status == JobStatus.COMPLETED,
                        )
                        .limit(50)
                    ).all()
                    if runs:
                        bl_scores = [r.score for r in runs if r.score is not None]
                        bl_latencies = [r.total_latency_ms for r in runs if r.total_latency_ms > 0]
                        baseline = {
                            "avg_score": round(sum(bl_scores) / len(bl_scores), 4) if bl_scores else None,
                            "avg_latency_ms": round(sum(bl_latencies) / len(bl_latencies), 1) if bl_latencies else None,
                            "safety_flag_rate": 0.02,  # Assumed baseline from pre-deployment eval
                            "n_runs": len(runs),
                            "source": "pre_deployment_eval",
                        }

                # 3. Model name
                if model_id is None:
                    model_name = "All models"
                else:
                    m = session.get(LLMModel, model_id)
                    model_name = m.name if m else f"Model {model_id}"
        except Exception as e:
            logger.error(f"[monitoring] Failed to load data for model {model_id}: {e}")

        return events, baseline, model_name

    @staticmethod
    async def _load_events(model_id: Optional[int], window_hours: int) -> list[dict]:
        try:
            from sqlmodel import Session, select
            from core.database import engine
            from core.models import TelemetryEvent

            cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
            with Session(engine) as session:
                query = (
                    select(TelemetryEvent)
                    .where(TelemetryEvent.timestamp >= cutoff)
                    .order_by(TelemetryEvent.timestamp)
                )
                if model_id is not None:
                    query = query.where(TelemetryEvent.model_id == model_id)
                records = session.exec(query.limit(10000)).all()

            return [
                {
                    "event_type": r.event_type,
                    "score": r.score,
                    "latency_ms": r.latency_ms,
                    "safety_flag": r.safety_flag,
                    "timestamp": r.timestamp.isoformat(),
                    "cost_usd": r.cost_usd,
                }
                for r in records
            ]
        except Exception as e:
            logger.error(f"[monitoring] Failed to load events: {e}")
            return []

    @staticmethod
    async def _load_baseline(model_id: Optional[int]) -> Optional[dict]:
        """Load pre-deployment eval baseline for a model."""
        if model_id is None:
            return None
        try:
            from sqlmodel import Session, select
            from core.database import engine
            from core.models import EvalRun, JobStatus

            with Session(engine) as session:
                runs = session.exec(
                    select(EvalRun)
                    .where(EvalRun.model_id == model_id, EvalRun.status == JobStatus.COMPLETED)
                    .limit(50)
                ).all()

            if not runs:
                return None

            scores = [r.score for r in runs if r.score is not None]
            latencies = [r.total_latency_ms for r in runs if r.total_latency_ms > 0]

            return {
                "avg_score": round(sum(scores) / len(scores), 4) if scores else None,
                "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
                "safety_flag_rate": 0.02,  # Assumed baseline from pre-deployment eval
                "n_runs": len(runs),
                "source": "pre_deployment_eval",
            }
        except Exception as e:
            logger.error(f"[monitoring] Failed to load baseline: {e}")
            return None

    @staticmethod
    async def _get_model_name(model_id: Optional[int]) -> str:
        if model_id is None:
            return "All models"
        try:
            from sqlmodel import Session
            from core.database import engine
            from core.models import LLMModel

            with Session(engine) as session:
                m = session.get(LLMModel, model_id)
                return m.name if m else f"Model {model_id}"
        except Exception:
            return f"Model {model_id}"

    @staticmethod
    def _empty_report(model_id, model_name, window_hours) -> MonitoringReport:
        empty_nist = [
            NISTDimensionScore(dim, 0.5, "warning", "No telemetry data in window")
            for dim in ["functionality_drift", "operational_reliability", "human_factors",
                        "security_posture", "fairness_bias", "societal_impact"]
        ]
        return MonitoringReport(
            model_id=model_id, model_name=model_name, window_hours=window_hours,
            n_inferences=0, generated_at=datetime.now(UTC).isoformat(),
            nist_scores=empty_nist, overall_health=0.5, health_status="unknown",
            avg_score=None, avg_latency_ms=0.0, error_rate=0.0,
            safety_flag_rate=0.0, refusal_rate=0.0, score_trend="unknown",
            score_volatility=0.0, drift_alerts=[], baseline_comparison=None,
            judge_coverage=0.0, judge_validity_warning="No telemetry data available for this window.",
        )
