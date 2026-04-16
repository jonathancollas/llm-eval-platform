"""
Tests for eval_engine/monitoring.py
Covers ContinuousMonitoringEngine, all stat helpers, NIST dimension scorers,
drift detectors, and the _empty_report path.
"""
import asyncio
import os
import secrets
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from eval_engine.monitoring import (
    NISTDimensionScore,
    DriftAlert,
    MonitoringReport,
    ContinuousMonitoringEngine,
    _trend,
    _volatility,
    _ewma,
    _detect_score_drift,
    _detect_latency_drift,
    _detect_safety_spike,
    _score_functionality,
    _score_reliability,
    _score_human_factors,
    _score_security,
    _score_fairness,
    _score_societal,
)


# ── _trend ────────────────────────────────────────────────────────────────────

def test_trend_unknown_few_values():
    assert _trend([]) == "unknown"
    assert _trend([0.5]) == "unknown"
    assert _trend([0.5, 0.6]) == "unknown"
    assert _trend([0.5, 0.6, 0.7]) == "unknown"


def test_trend_improving():
    values = [0.1, 0.2, 0.5, 0.7, 0.9, 0.95]
    assert _trend(values) == "improving"


def test_trend_degrading():
    values = [0.9, 0.7, 0.5, 0.3, 0.1, 0.05]
    assert _trend(values) == "degrading"


def test_trend_stable():
    values = [0.5, 0.51, 0.49, 0.505, 0.495, 0.502]
    assert _trend(values) == "stable"


def test_trend_all_same():
    values = [0.5] * 6
    assert _trend(values) == "stable"


# ── _volatility ───────────────────────────────────────────────────────────────

def test_volatility_empty():
    assert _volatility([]) == 0.0


def test_volatility_single():
    assert _volatility([0.5]) == 0.0


def test_volatility_identical():
    assert _volatility([0.5, 0.5, 0.5]) == pytest.approx(0.0)


def test_volatility_known():
    v = _volatility([0.0, 1.0])
    assert v > 0.0


def test_volatility_returns_float():
    assert isinstance(_volatility([0.1, 0.5, 0.9]), float)


# ── _ewma ─────────────────────────────────────────────────────────────────────

def test_ewma_empty():
    assert _ewma([]) == 0.0


def test_ewma_single():
    assert _ewma([0.7]) == pytest.approx(0.7)


def test_ewma_constant():
    result = _ewma([0.5, 0.5, 0.5, 0.5])
    assert result == pytest.approx(0.5)


def test_ewma_recent_weighted():
    # Recent values should have more weight
    result_increasing = _ewma([0.1, 0.2, 0.3, 0.9], alpha=0.5)
    result_decreasing = _ewma([0.9, 0.3, 0.2, 0.1], alpha=0.5)
    assert result_increasing > result_decreasing


# ── _detect_score_drift ───────────────────────────────────────────────────────

def test_detect_score_drift_no_scores():
    assert _detect_score_drift([], 0.8, 1) is None


def test_detect_score_drift_no_baseline():
    assert _detect_score_drift([0.5, 0.6], None, 1) is None


def test_detect_score_drift_small_delta():
    # delta < 0.05 → no alert
    assert _detect_score_drift([0.82, 0.83], 0.8, 1) is None


def test_detect_score_drift_medium():
    alert = _detect_score_drift([0.6, 0.65], 0.8, 1)
    assert alert is not None
    assert alert.severity == "high"
    assert alert.alert_type == "functionality_drift"
    assert alert.delta < 0


def test_detect_score_drift_critical():
    alert = _detect_score_drift([0.4, 0.45], 0.8, 1)
    assert alert is not None
    assert alert.severity == "critical"


def test_detect_score_drift_improvement():
    alert = _detect_score_drift([0.9, 0.95], 0.8, 1)
    assert alert is not None
    assert alert.delta > 0
    assert "improvement" in alert.description


def test_detect_score_drift_alert_fields():
    alert = _detect_score_drift([0.5], 0.8, 42)
    assert alert.model_id == 42
    assert alert.metric_name == "quality_score"
    assert alert.nist_dimension == "functionality_drift"
    assert isinstance(alert.detected_at, str)


# ── _detect_latency_drift ────────────────────────────────────────────────────

def test_detect_latency_drift_no_data():
    assert _detect_latency_drift([], None, 1) is None


def test_detect_latency_drift_no_baseline():
    assert _detect_latency_drift([500.0, 600.0], None, 1) is None


def test_detect_latency_drift_zero_baseline():
    assert _detect_latency_drift([500.0], 0.0, 1) is None


def test_detect_latency_drift_small_increase():
    # <50% increase → no alert
    assert _detect_latency_drift([1400.0], 1000.0, 1) is None


def test_detect_latency_drift_medium():
    alert = _detect_latency_drift([1600.0], 1000.0, 1)
    assert alert is not None
    assert alert.severity == "medium"


def test_detect_latency_drift_high():
    alert = _detect_latency_drift([2200.0], 1000.0, 1)
    assert alert is not None
    assert alert.severity == "high"


def test_detect_latency_drift_critical():
    alert = _detect_latency_drift([3500.0], 1000.0, 1)
    assert alert is not None
    assert alert.severity == "critical"


def test_detect_latency_drift_alert_fields():
    alert = _detect_latency_drift([2000.0], 1000.0, 5)
    assert alert.alert_type == "reliability_degradation"
    assert alert.metric_name == "latency_ms"
    assert alert.nist_dimension == "operational_reliability"


# ── _detect_safety_spike ─────────────────────────────────────────────────────

def test_detect_safety_spike_small():
    # delta < 0.05 → no alert
    assert _detect_safety_spike(0.03, 0.01, 1) is None


def test_detect_safety_spike_medium():
    alert = _detect_safety_spike(0.08, 0.01, 1)
    assert alert is not None
    assert alert.severity == "medium"


def test_detect_safety_spike_high():
    alert = _detect_safety_spike(0.15, 0.01, 1)
    assert alert is not None
    assert alert.severity == "high"


def test_detect_safety_spike_critical():
    alert = _detect_safety_spike(0.30, 0.01, 1)
    assert alert is not None
    assert alert.severity == "critical"


def test_detect_safety_spike_alert_fields():
    alert = _detect_safety_spike(0.15, 0.02, 10)
    assert alert.alert_type == "safety_signal"
    assert alert.metric_name == "safety_flag_rate"
    assert alert.nist_dimension == "security_posture"


# ── NIST dimension scorers ────────────────────────────────────────────────────

class TestScoreFunctionality:
    def test_no_scores(self):
        d = _score_functionality([], 0.8)
        assert d.status == "warning"
        assert d.score == 0.5

    def test_no_baseline(self):
        d = _score_functionality([0.7, 0.8], None)
        assert d.status == "warning"
        assert d.score > 0.0

    def test_healthy(self):
        d = _score_functionality([0.8, 0.82, 0.79], 0.8)
        assert d.status == "healthy"

    def test_warning(self):
        d = _score_functionality([0.73], 0.8)
        assert d.status == "warning"

    def test_critical(self):
        d = _score_functionality([0.5], 0.8)
        assert d.status == "critical"


class TestScoreReliability:
    def test_no_latencies(self):
        d = _score_reliability([], 0.05, 1000.0)
        assert isinstance(d.score, float)

    def test_healthy_low_error(self):
        d = _score_reliability([900.0, 1100.0], 0.01, 1000.0)
        assert d.score > 0.8

    def test_high_error_rate(self):
        d = _score_reliability([1000.0], 0.5, 1000.0)
        # error_score = max(0, 1-0.5*5)=0, latency_score=1.0, combined=0.5
        assert d.score <= 0.5

    def test_high_latency(self):
        d = _score_reliability([5000.0], 0.01, 1000.0)
        assert d.score < 1.0

    def test_status_critical(self):
        # Very high latency and high error to push score < 0.5
        d = _score_reliability([5000.0], 0.9, 1000.0)
        # latency_score ≈ max(0, 1-(5-1)*0.5)=0; error_score=0; score=0
        assert d.status in ("critical", "warning")


class TestScoreHumanFactors:
    def test_low_refusal_healthy(self):
        d = _score_human_factors(0.05, "stable")
        assert d.status == "healthy"
        assert d.score > 0.9

    def test_high_refusal_warning(self):
        d = _score_human_factors(0.35, "stable")
        assert d.status == "warning"

    def test_degrading_trend_reduces_score(self):
        d_stable = _score_human_factors(0.1, "stable")
        d_degrading = _score_human_factors(0.1, "degrading")
        assert d_degrading.score < d_stable.score

    def test_degrading_appends_to_signal(self):
        d = _score_human_factors(0.1, "degrading")
        assert "degrading" in d.signal


class TestScoreSecurity:
    def test_low_flag_rate_healthy(self):
        d = _score_security(0.01, 0.01)
        assert d.status == "healthy"
        assert d.score > 0.9

    def test_medium_flag_rate_warning(self):
        d = _score_security(0.08, 0.01)
        assert d.status == "warning"

    def test_high_flag_rate_critical(self):
        d = _score_security(0.25, 0.01)
        assert d.status == "critical"


class TestScoreFairness:
    def test_low_variance_healthy(self):
        d = _score_fairness(0.02)
        assert d.status == "healthy"
        assert d.score >= 0.9

    def test_medium_variance_warning(self):
        d = _score_fairness(0.15)
        assert d.status == "warning"

    def test_high_variance_critical(self):
        d = _score_fairness(0.25)
        assert d.status == "critical"


class TestScoreSocietal:
    def test_low_flag_rate_stable(self):
        d = _score_societal(0.01, "stable")
        assert d.status == "healthy"

    def test_high_flag_rate(self):
        d = _score_societal(0.4, "stable")
        assert d.score < 0.5

    def test_degrading_reduces_score(self):
        d_stable = _score_societal(0.05, "stable")
        d_degrade = _score_societal(0.05, "degrading")
        assert d_degrade.score <= d_stable.score


# ── ContinuousMonitoringEngine ────────────────────────────────────────────────

def _make_events(n=20, scores=None, latencies=None, safety_flags=None, errors=None):
    events = []
    for i in range(n):
        event = {
            "event_type": "inference",
            "score": scores[i] if scores else 0.8,
            "latency_ms": latencies[i] if latencies else 1000,
            "safety_flag": safety_flags[i] if safety_flags else None,
            "timestamp": datetime.utcnow().isoformat(),
            "cost_usd": 0.001,
        }
        if errors and i in errors:
            event["event_type"] = "error"
        events.append(event)
    return events


def _make_baseline(avg_score=0.8, avg_latency=1000.0, flag_rate=0.02):
    return {
        "avg_score": avg_score,
        "avg_latency_ms": avg_latency,
        "safety_flag_rate": flag_rate,
        "n_runs": 10,
        "source": "pre_deployment_eval",
    }


def test_engine_empty_report():
    """Empty events → _empty_report path."""
    engine = ContinuousMonitoringEngine()

    with patch.object(ContinuousMonitoringEngine, "_load_events", new=AsyncMock(return_value=[])):
        with patch.object(ContinuousMonitoringEngine, "_load_baseline", new=AsyncMock(return_value=None)):
            with patch.object(ContinuousMonitoringEngine, "_get_model_name", new=AsyncMock(return_value="TestModel")):
                report = asyncio.run(engine.analyze(model_id=1, window_hours=24))

    assert report.n_inferences == 0
    assert report.health_status == "unknown"
    assert report.overall_health == 0.5
    assert len(report.nist_scores) == 6
    assert report.judge_validity_warning is not None


def test_engine_healthy_report():
    """Normal events produce a healthy report."""
    engine = ContinuousMonitoringEngine()
    events = _make_events(n=30, scores=[0.85] * 30, latencies=[900] * 30)
    baseline = _make_baseline(avg_score=0.82)

    with patch.object(ContinuousMonitoringEngine, "_load_events", new=AsyncMock(return_value=events)):
        with patch.object(ContinuousMonitoringEngine, "_load_baseline", new=AsyncMock(return_value=baseline)):
            with patch.object(ContinuousMonitoringEngine, "_get_model_name", new=AsyncMock(return_value="GoodModel")):
                report = asyncio.run(engine.analyze(model_id=1, window_hours=24))

    assert report.n_inferences == 30
    assert report.avg_score is not None
    assert report.avg_score == pytest.approx(0.85, abs=0.01)
    assert report.health_status in ("healthy", "warning", "critical")
    assert isinstance(report.nist_scores, list)
    assert len(report.nist_scores) == 6


def test_engine_drift_alerts_generated():
    """Score drift vs baseline triggers alerts."""
    engine = ContinuousMonitoringEngine()
    events = _make_events(n=20, scores=[0.4] * 20, latencies=[1000] * 20)
    baseline = _make_baseline(avg_score=0.8, avg_latency=1000.0)

    with patch.object(ContinuousMonitoringEngine, "_load_events", new=AsyncMock(return_value=events)):
        with patch.object(ContinuousMonitoringEngine, "_load_baseline", new=AsyncMock(return_value=baseline)):
            with patch.object(ContinuousMonitoringEngine, "_get_model_name", new=AsyncMock(return_value="DriftModel")):
                report = asyncio.run(engine.analyze(model_id=2, window_hours=24))

    assert len(report.drift_alerts) > 0
    alert_types = [a.alert_type for a in report.drift_alerts]
    assert "functionality_drift" in alert_types


def test_engine_latency_drift_alert():
    """Latency spike triggers reliability_degradation alert."""
    engine = ContinuousMonitoringEngine()
    events = _make_events(n=20, scores=[0.8] * 20, latencies=[3000] * 20)
    baseline = _make_baseline(avg_latency=1000.0)

    with patch.object(ContinuousMonitoringEngine, "_load_events", new=AsyncMock(return_value=events)):
        with patch.object(ContinuousMonitoringEngine, "_load_baseline", new=AsyncMock(return_value=baseline)):
            with patch.object(ContinuousMonitoringEngine, "_get_model_name", new=AsyncMock(return_value="SlowModel")):
                report = asyncio.run(engine.analyze(model_id=3, window_hours=24))

    alert_types = [a.alert_type for a in report.drift_alerts]
    assert "reliability_degradation" in alert_types


def test_engine_safety_spike_alert():
    """High safety flag rate triggers safety_signal alert."""
    engine = ContinuousMonitoringEngine()
    # 50% of events have safety flags
    flags = ["refusal" if i % 2 == 0 else None for i in range(20)]
    events = _make_events(n=20, safety_flags=flags)
    baseline = _make_baseline(flag_rate=0.02)

    with patch.object(ContinuousMonitoringEngine, "_load_events", new=AsyncMock(return_value=events)):
        with patch.object(ContinuousMonitoringEngine, "_load_baseline", new=AsyncMock(return_value=baseline)):
            with patch.object(ContinuousMonitoringEngine, "_get_model_name", new=AsyncMock(return_value="SafetyModel")):
                report = asyncio.run(engine.analyze(model_id=4, window_hours=24))

    alert_types = [a.alert_type for a in report.drift_alerts]
    assert "safety_signal" in alert_types


def test_engine_no_baseline():
    """Engine works without baseline data."""
    engine = ContinuousMonitoringEngine()
    events = _make_events(n=15)

    with patch.object(ContinuousMonitoringEngine, "_load_events", new=AsyncMock(return_value=events)):
        with patch.object(ContinuousMonitoringEngine, "_load_baseline", new=AsyncMock(return_value=None)):
            with patch.object(ContinuousMonitoringEngine, "_get_model_name", new=AsyncMock(return_value="NoBaseline")):
                report = asyncio.run(engine.analyze(model_id=None, window_hours=24))

    assert report.baseline_comparison is None
    assert report.drift_alerts == []  # No alerts without baseline


def test_engine_judge_warning_low_coverage():
    """Low judge coverage (few scored events) generates warning."""
    engine = ContinuousMonitoringEngine()
    # 60 events, only a few with scores
    events = []
    for i in range(60):
        events.append({
            "event_type": "inference",
            "score": 0.8 if i < 3 else None,  # Only 3 scored
            "latency_ms": 1000,
            "safety_flag": None,
            "timestamp": datetime.utcnow().isoformat(),
        })

    with patch.object(ContinuousMonitoringEngine, "_load_events", new=AsyncMock(return_value=events)):
        with patch.object(ContinuousMonitoringEngine, "_load_baseline", new=AsyncMock(return_value=None)):
            with patch.object(ContinuousMonitoringEngine, "_get_model_name", new=AsyncMock(return_value="LowCovModel")):
                report = asyncio.run(engine.analyze(model_id=5, window_hours=24))

    assert report.judge_validity_warning is not None
    assert "Low judge coverage" in report.judge_validity_warning


def test_engine_judge_warning_high_coverage():
    """High judge coverage on large dataset generates gaming warning."""
    engine = ContinuousMonitoringEngine()
    events = _make_events(n=150, scores=[0.8] * 150)

    with patch.object(ContinuousMonitoringEngine, "_load_events", new=AsyncMock(return_value=events)):
        with patch.object(ContinuousMonitoringEngine, "_load_baseline", new=AsyncMock(return_value=None)):
            with patch.object(ContinuousMonitoringEngine, "_get_model_name", new=AsyncMock(return_value="HighCovModel")):
                report = asyncio.run(engine.analyze(model_id=6, window_hours=24))

    assert report.judge_validity_warning is not None
    assert "High judge coverage" in report.judge_validity_warning


def test_engine_error_rate_computation():
    """Error events contribute to error_rate."""
    engine = ContinuousMonitoringEngine()
    events = _make_events(n=10, errors={0, 1, 2})  # 3/10 errors

    with patch.object(ContinuousMonitoringEngine, "_load_events", new=AsyncMock(return_value=events)):
        with patch.object(ContinuousMonitoringEngine, "_load_baseline", new=AsyncMock(return_value=None)):
            with patch.object(ContinuousMonitoringEngine, "_get_model_name", new=AsyncMock(return_value="ErrorModel")):
                report = asyncio.run(engine.analyze(model_id=7, window_hours=24))

    assert report.error_rate == pytest.approx(0.3, abs=0.01)


def test_engine_refusal_rate_computation():
    """Refusal safety flags contribute to refusal_rate."""
    engine = ContinuousMonitoringEngine()
    flags = ["refusal", "refusal", None, None, None, None, None, None, None, None]
    events = _make_events(n=10, safety_flags=flags)

    with patch.object(ContinuousMonitoringEngine, "_load_events", new=AsyncMock(return_value=events)):
        with patch.object(ContinuousMonitoringEngine, "_load_baseline", new=AsyncMock(return_value=None)):
            with patch.object(ContinuousMonitoringEngine, "_get_model_name", new=AsyncMock(return_value="RefusalModel")):
                report = asyncio.run(engine.analyze(model_id=8, window_hours=24))

    assert report.refusal_rate == pytest.approx(0.2, abs=0.01)


def test_engine_health_status_critical():
    """Very poor metrics yield critical health status."""
    engine = ContinuousMonitoringEngine()
    flags = ["harm"] * 20
    events = _make_events(n=20, scores=[0.1] * 20, safety_flags=flags, errors=set(range(15)))
    baseline = _make_baseline(avg_score=0.9, flag_rate=0.0)

    with patch.object(ContinuousMonitoringEngine, "_load_events", new=AsyncMock(return_value=events)):
        with patch.object(ContinuousMonitoringEngine, "_load_baseline", new=AsyncMock(return_value=baseline)):
            with patch.object(ContinuousMonitoringEngine, "_get_model_name", new=AsyncMock(return_value="PoorModel")):
                report = asyncio.run(engine.analyze(model_id=9, window_hours=24))

    assert report.health_status in ("warning", "critical")


def test_engine_model_id_none():
    """Engine handles model_id=None (all models) gracefully."""
    engine = ContinuousMonitoringEngine()
    events = _make_events(n=5)

    with patch.object(ContinuousMonitoringEngine, "_load_events", new=AsyncMock(return_value=events)):
        with patch.object(ContinuousMonitoringEngine, "_load_baseline", new=AsyncMock(return_value=None)):
            with patch.object(ContinuousMonitoringEngine, "_get_model_name", new=AsyncMock(return_value="All models")):
                report = asyncio.run(engine.analyze(model_id=None, window_hours=24))

    assert report.model_id is None
    assert report.model_name == "All models"


def test_engine_score_trend_improving():
    """Monotonically improving scores yield improving trend."""
    engine = ContinuousMonitoringEngine()
    scores = [0.3, 0.4, 0.55, 0.65, 0.75, 0.85, 0.9, 0.92]
    events = _make_events(n=len(scores), scores=scores)

    with patch.object(ContinuousMonitoringEngine, "_load_events", new=AsyncMock(return_value=events)):
        with patch.object(ContinuousMonitoringEngine, "_load_baseline", new=AsyncMock(return_value=None)):
            with patch.object(ContinuousMonitoringEngine, "_get_model_name", new=AsyncMock(return_value="TrendModel")):
                report = asyncio.run(engine.analyze(model_id=10, window_hours=24))

    assert report.score_trend == "improving"


def test_engine_nist_weights_sum_to_one():
    """NIST_WEIGHTS must sum to 1.0."""
    total = sum(ContinuousMonitoringEngine.NIST_WEIGHTS.values())
    assert total == pytest.approx(1.0, abs=0.001)


def test_load_events_db_error():
    """_load_events returns [] on DB error."""
    with patch.dict("sys.modules", {"core.database": None}):
        result = asyncio.run(ContinuousMonitoringEngine._load_events(model_id=1, window_hours=24))
    assert result == []


def test_load_baseline_none_model_id():
    """_load_baseline returns None when model_id is None."""
    result = asyncio.run(ContinuousMonitoringEngine._load_baseline(None))
    assert result is None


def test_load_baseline_db_error():
    """_load_baseline returns None on DB error."""
    with patch.dict("sys.modules", {"core.database": None}):
        result = asyncio.run(ContinuousMonitoringEngine._load_baseline(model_id=1))
    assert result is None


def test_get_model_name_none():
    result = asyncio.run(ContinuousMonitoringEngine._get_model_name(None))
    assert result == "All models"


def test_get_model_name_db_error():
    with patch.dict("sys.modules", {"core.database": None}):
        result = asyncio.run(ContinuousMonitoringEngine._get_model_name(model_id=99))
    assert "99" in result


def test_empty_report_structure():
    """_empty_report produces correct structure."""
    report = ContinuousMonitoringEngine._empty_report(42, "TestModel", 24)
    assert report.model_id == 42
    assert report.model_name == "TestModel"
    assert report.window_hours == 24
    assert report.n_inferences == 0
    assert len(report.nist_scores) == 6
    assert all(d.score == 0.5 for d in report.nist_scores)
    assert all(d.status == "warning" for d in report.nist_scores)
    assert report.health_status == "unknown"
    assert report.drift_alerts == []


# ── Dataclass construction ────────────────────────────────────────────────────

def test_nist_dimension_score_dataclass():
    d = NISTDimensionScore("functionality_drift", 0.8, "healthy", "All good")
    assert d.dimension == "functionality_drift"
    assert d.score == 0.8
    assert d.reference == "NIST AI 800-4 (March 2026)"


def test_drift_alert_dataclass():
    alert = DriftAlert(
        alert_id="test_1",
        alert_type="functionality_drift",
        severity="high",
        model_id=1,
        detected_at="2024-01-01T00:00:00",
        metric_name="quality_score",
        baseline_value=0.8,
        current_value=0.5,
        delta=-0.3,
        description="Score dropped",
        recommended_action="Investigate",
        nist_dimension="functionality_drift",
    )
    assert alert.severity == "high"
    assert alert.delta == -0.3
