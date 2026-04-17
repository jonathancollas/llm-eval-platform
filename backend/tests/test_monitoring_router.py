"""
Tests for api/routers/monitoring.py
Covers: telemetry ingest (single/batch/langfuse/otel), stats, telemetry feed,
        report endpoint (mocked), dashboard (mocked), integration setup.
"""
import importlib.util
import json
import os
import secrets
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

_spec = importlib.util.spec_from_file_location(
    "monitoring_router",
    Path(__file__).parent.parent / "api" / "routers" / "monitoring.py",
)
mod = importlib.util.module_from_spec(_spec)
sys.modules["monitoring_router"] = mod
_spec.loader.exec_module(mod)

from core.models import TelemetryEvent, LLMModel, ModelProvider


@pytest.fixture(scope="module")
def db_engine(tmp_path_factory):
    db = tmp_path_factory.mktemp("monitoring_tests") / "monitoring.db"
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="module")
def app(db_engine):
    def _get_session():
        with Session(db_engine) as s:
            yield s

    test_app = FastAPI()
    test_app.include_router(mod.router)
    test_app.dependency_overrides[mod.get_session] = _get_session
    return test_app


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def seeded_model(db_engine):
    with Session(db_engine) as s:
        model = LLMModel(
            name="MonitoredModel",
            provider=ModelProvider.OPENAI,
            model_id="mon/model-1",
        )
        s.add(model)
        s.commit()
        return model.id


@pytest.fixture(scope="module")
def seeded_events(db_engine, seeded_model):
    """Seed telemetry events for stats/feed tests."""
    now = datetime.utcnow()
    with Session(db_engine) as s:
        for i in range(10):
            e = TelemetryEvent(
                model_id=seeded_model,
                event_type="inference" if i < 8 else "error",
                latency_ms=150 + i * 20,
                score=0.6 + i * 0.02 if i < 8 else None,
                safety_flag="refusal" if i == 5 else None,
                deployment_context="production",
                timestamp=now - timedelta(minutes=i * 30),
            )
            s.add(e)
        s.commit()
    return seeded_model


# ── single ingest ─────────────────────────────────────────────────────────────

def test_ingest_telemetry_basic(client):
    with patch("monitoring_router.classify_runtime_safety", new=AsyncMock(return_value=(None, None))):
        resp = client.post("/monitoring/ingest", json={
            "event_type": "inference",
            "prompt": "Hello world",
            "response": "Hi there",
            "latency_ms": 300,
            "score": 0.85,
            "safety_flag": None,
        })
    assert resp.status_code == 201
    data = resp.json()
    assert "event_id" in data
    assert data["status"] == "ingested"


def test_ingest_with_existing_safety_flag(client):
    """If safety_flag is already set, skip auto-classify."""
    with patch("monitoring_router.classify_runtime_safety", new=AsyncMock(return_value=(None, None))) as mock_cls:
        resp = client.post("/monitoring/ingest", json={
            "event_type": "safety_flag",
            "safety_flag": "refusal",
            "confidence": 0.9,
            "latency_ms": 100,
        })
    assert resp.status_code == 201


def test_ingest_auto_classify(client):
    """Auto-classify fires when no safety_flag and no score."""
    with patch("monitoring_router.classify_runtime_safety",
               new=AsyncMock(return_value=("hallucination", 0.7))):
        resp = client.post("/monitoring/ingest", json={
            "event_type": "inference",
            "prompt": "Dangerous prompt",
            "response": "Risky response",
            "latency_ms": 200,
        })
    assert resp.status_code == 201


def test_ingest_with_model_id(client, seeded_model):
    with patch("monitoring_router.classify_runtime_safety", new=AsyncMock(return_value=(None, None))):
        resp = client.post("/monitoring/ingest", json={
            "model_id": seeded_model,
            "event_type": "inference",
            "latency_ms": 250,
            "score": 0.7,
        })
    assert resp.status_code == 201


def test_ingest_with_tools(client):
    with patch("monitoring_router.classify_runtime_safety", new=AsyncMock(return_value=(None, None))):
        resp = client.post("/monitoring/ingest", json={
            "event_type": "inference",
            "tool_names": ["calculator", "web_search"],
            "latency_ms": 400,
        })
    assert resp.status_code == 201


# ── batch ingest ──────────────────────────────────────────────────────────────

def test_ingest_batch(client):
    with patch("monitoring_router.classify_runtime_safety", new=AsyncMock(return_value=(None, None))):
        resp = client.post("/monitoring/ingest/batch", json={
            "events": [
                {"event_type": "inference", "latency_ms": 100, "score": 0.8},
                {"event_type": "error", "latency_ms": 0},
                {"event_type": "inference", "safety_flag": "refusal", "latency_ms": 50},
            ]
        })
    assert resp.status_code == 201
    assert resp.json()["ingested"] == 3


def test_ingest_batch_too_large(client):
    resp = client.post("/monitoring/ingest/batch", json={
        "events": [{"event_type": "inference"}] * 1001
    })
    assert resp.status_code == 400


def test_ingest_batch_empty(client):
    with patch("monitoring_router.classify_runtime_safety", new=AsyncMock(return_value=(None, None))):
        resp = client.post("/monitoring/ingest/batch", json={"events": []})
    assert resp.status_code == 201
    assert resp.json()["ingested"] == 0


# ── Langfuse ingest ───────────────────────────────────────────────────────────

def test_ingest_langfuse_basic(client):
    resp = client.post("/monitoring/ingest/langfuse", json={
        "trace_id": "trace-abc-123",
        "session_id": "sess-001",
        "name": "chat",
        "input": "What is AI?",
        "output": "AI is artificial intelligence.",
        "latency_ms": 300,
        "prompt_tokens": 10,
        "completion_tokens": 20,
        "cost_usd": 0.001,
        "model": "gpt-4",
        "tags": ["production"],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "ingested"
    assert data["source"] == "langfuse"


def test_ingest_langfuse_no_model(client):
    resp = client.post("/monitoring/ingest/langfuse", json={
        "trace_id": "trace-xyz",
        "input": "hello",
        "output": "world",
    })
    assert resp.status_code == 201


def test_ingest_langfuse_model_resolution(client, seeded_model, db_engine):
    """Model lookup hits the DB path."""
    with Session(db_engine) as s:
        model = s.get(LLMModel, seeded_model)
        model_id_str = model.model_id

    resp = client.post("/monitoring/ingest/langfuse", json={
        "model": model_id_str,
        "input": "test",
        "output": "result",
    })
    assert resp.status_code == 201


# ── OTEL ingest ───────────────────────────────────────────────────────────────

def test_ingest_otel_basic(client):
    payload = {
        "resource_spans": [
            {
                "scope_spans": [
                    {
                        "spans": [
                            {
                                "name": "llm.generate",
                                "trace_id": "t1",
                                "span_id": "s1",
                                "start_time_unix_nano": 1_000_000_000,
                                "end_time_unix_nano": 1_300_000_000,
                                "attributes": {
                                    "gen_ai.request.model": "gpt-4",
                                    "gen_ai.usage.prompt_tokens": 15,
                                    "gen_ai.usage.completion_tokens": 30,
                                    "gen_ai.prompt": "Hello?",
                                    "gen_ai.completion": "Hi!",
                                },
                            }
                        ]
                    }
                ]
            }
        ]
    }
    resp = client.post("/monitoring/ingest/otel", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["ingested"] == 1
    assert data["source"] == "otel"


def test_ingest_otel_no_llm_spans(client):
    payload = {
        "resource_spans": [
            {
                "scope_spans": [
                    {
                        "spans": [
                            {
                                "name": "http.request",
                                "attributes": {},  # No gen_ai.request.model
                            }
                        ]
                    }
                ]
            }
        ]
    }
    resp = client.post("/monitoring/ingest/otel", json=payload)
    assert resp.status_code == 201
    assert resp.json()["ingested"] == 0


def test_ingest_otel_empty(client):
    resp = client.post("/monitoring/ingest/otel", json={"resource_spans": []})
    assert resp.status_code == 201
    assert resp.json()["ingested"] == 0


def test_ingest_otel_with_known_model(client, seeded_model, db_engine):
    """Model lookup in OTEL path."""
    with Session(db_engine) as s:
        model = s.get(LLMModel, seeded_model)
        model_id_str = model.model_id

    payload = {
        "resource_spans": [{
            "scope_spans": [{
                "spans": [{
                    "name": "llm.generate",
                    "start_time_unix_nano": 1_000_000_000,
                    "end_time_unix_nano": 1_500_000_000,
                    "attributes": {
                        "gen_ai.request.model": model_id_str,
                        "gen_ai.usage.prompt_tokens": 5,
                        "gen_ai.usage.completion_tokens": 10,
                    },
                }]
            }]
        }]
    }
    resp = client.post("/monitoring/ingest/otel", json=payload)
    assert resp.status_code == 201


# ── telemetry feed ────────────────────────────────────────────────────────────

def test_telemetry_feed_all(client, seeded_events):
    resp = client.get("/monitoring/telemetry?window_hours=24")
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert "total" in data
    assert data["total"] >= 0


def test_telemetry_feed_filtered_model(client, seeded_events):
    mid = seeded_events
    resp = client.get(f"/monitoring/telemetry?model_id={mid}&window_hours=24&limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data


def test_telemetry_feed_filtered_event_type(client, seeded_events):
    resp = client.get("/monitoring/telemetry?event_type=error&window_hours=24")
    assert resp.status_code == 200
    events = resp.json()["events"]
    for e in events:
        assert e["event_type"] == "error"


# ── stats ─────────────────────────────────────────────────────────────────────

def test_stats_no_events(client):
    """Very long window where no events exist."""
    resp = client.get("/monitoring/stats?model_id=99999&window_hours=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["n"] == 0


def test_stats_with_events(client, seeded_events):
    mid = seeded_events
    resp = client.get(f"/monitoring/stats?model_id={mid}&window_hours=720")
    assert resp.status_code == 200
    data = resp.json()
    assert data["n"] >= 1
    assert "scores" in data
    assert "latency" in data
    assert "safety" in data
    assert "error_rate" in data


def test_stats_all_models(client, seeded_events):
    resp = client.get("/monitoring/stats?window_hours=720")
    assert resp.status_code == 200
    data = resp.json()
    assert "n" in data


# ── monitoring report (mocked ContinuousMonitoringEngine) ────────────────────

def _make_mock_report(model_id=None):
    from eval_engine.monitoring import MonitoringReport, DriftAlert, NISTDimensionScore
    nist = NISTDimensionScore(
        dimension="functionality_drift",
        score=0.8,
        status="healthy",
        signal="stable",
        reference="NIST AI 800-4",
    )
    alert = DriftAlert(
        alert_id="ALT-001",
        alert_type="functionality_drift",
        severity="low",
        model_id=model_id,
        detected_at="2026-01-01T00:00:00",
        metric_name="avg_score",
        baseline_value=0.9,
        current_value=0.7,
        delta=-0.2,
        description="Score dropped slightly",
        recommended_action="Monitor",
        nist_dimension="functionality_drift",
    )
    return MonitoringReport(
        model_id=model_id,
        model_name="TestModel",
        window_hours=24,
        n_inferences=10,
        generated_at="2026-01-01T00:00:00",
        nist_scores=[nist],
        overall_health=0.8,
        health_status="healthy",
        avg_score=0.75,
        avg_latency_ms=200.0,
        error_rate=0.02,
        safety_flag_rate=0.05,
        refusal_rate=0.03,
        score_trend="stable",
        score_volatility=0.05,
        drift_alerts=[alert],
        baseline_comparison=None,
        judge_coverage=0.9,
        judge_validity_warning=None,
    )


def test_monitoring_report(client):
    mock_report = _make_mock_report(model_id=1)
    mock_engine = MagicMock()
    mock_engine.analyze = AsyncMock(return_value=mock_report)

    with patch("monitoring_router.ContinuousMonitoringEngine", return_value=mock_engine):
        resp = client.get("/monitoring/report?model_id=1&window_hours=24")

    assert resp.status_code == 200
    data = resp.json()
    assert "health" in data
    assert "nist_dimensions" in data
    assert "drift_alerts" in data
    assert data["health"]["status"] == "healthy"


def test_monitoring_report_no_model(client):
    mock_report = _make_mock_report()
    mock_engine = MagicMock()
    mock_engine.analyze = AsyncMock(return_value=mock_report)

    with patch("monitoring_router.ContinuousMonitoringEngine", return_value=mock_engine):
        resp = client.get("/monitoring/report")

    assert resp.status_code == 200


# ── fleet dashboard ───────────────────────────────────────────────────────────

def test_fleet_dashboard_no_active_models(client):
    """No recent telemetry → empty fleet."""
    resp = client.get("/monitoring/dashboard?window_hours=1")
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    assert "window_hours" in data


def test_fleet_dashboard_with_models(client, seeded_events, db_engine):
    """Seed recent events and mock the engine."""
    # Ensure there is a recent event
    with Session(db_engine) as s:
        s.add(TelemetryEvent(
            model_id=seeded_events,
            event_type="inference",
            latency_ms=100,
            timestamp=datetime.utcnow() - timedelta(minutes=5),
        ))
        s.commit()

    mock_report = _make_mock_report(model_id=seeded_events)
    mock_engine = MagicMock()
    mock_engine.analyze = AsyncMock(return_value=mock_report)

    with patch("monitoring_router.ContinuousMonitoringEngine", return_value=mock_engine):
        resp = client.get("/monitoring/dashboard?window_hours=1")

    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    assert "n_active_models" in data


# ── integration setup ─────────────────────────────────────────────────────────

def test_integration_setup(client):
    resp = client.get("/monitoring/integration/setup")
    assert resp.status_code == 200
    data = resp.json()
    assert "langfuse" in data
    assert "opentelemetry" in data
    assert "webhook_url" in data["langfuse"]
    assert "endpoint" in data["opentelemetry"]
