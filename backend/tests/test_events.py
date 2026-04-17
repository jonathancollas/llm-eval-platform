"""Tests for api/routers/events.py"""
import asyncio
import importlib.util
import json
import os
import secrets
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

_spec = importlib.util.spec_from_file_location(
    "events_router_module",
    Path(__file__).parent.parent / "api" / "routers" / "events.py",
)
mod = importlib.util.module_from_spec(_spec)
sys.modules["events_router_module"] = mod
_spec.loader.exec_module(mod)


@pytest.fixture(scope="module")
def db_engine(tmp_path_factory):
    db = tmp_path_factory.mktemp("events_test") / "test.db"
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
def seeded_events(db_engine):
    """Seed EvalEventRecord rows. Campaign needs to exist first."""
    from core.models import Campaign, EvalEventRecord, JobStatus
    import uuid

    with Session(db_engine) as session:
        # We need a Campaign to satisfy FK
        campaign = Campaign(
            name="Event Test Campaign",
            description="",
            model_ids="[]",
            benchmark_ids="[]",
        )
        session.add(campaign)
        session.commit()
        session.refresh(campaign)
        campaign_id = campaign.id

        events = [
            EvalEventRecord(
                event_id=str(uuid.uuid4()),
                event_type="campaign.started",
                campaign_id=campaign_id,
                sequence=1,
                payload_json=json.dumps({}),
            ),
            EvalEventRecord(
                event_id=str(uuid.uuid4()),
                event_type="run.started",
                campaign_id=campaign_id,
                sequence=2,
                payload_json=json.dumps({"model_name": "GPT-4", "benchmark_name": "MMLU"}),
            ),
            EvalEventRecord(
                event_id=str(uuid.uuid4()),
                event_type="run.completed",
                campaign_id=campaign_id,
                sequence=3,
                payload_json=json.dumps({"score": 0.85}),
            ),
            EvalEventRecord(
                event_id=str(uuid.uuid4()),
                event_type="campaign.completed",
                campaign_id=campaign_id,
                sequence=4,
                payload_json=json.dumps({}),
            ),
        ]
        for e in events:
            session.add(e)
        session.commit()
        return campaign_id


# ── GET /events/campaign/{id} ─────────────────────────────────────────────────

def test_get_campaign_events_empty(client):
    resp = client.get("/events/campaign/99999")
    assert resp.status_code == 200
    data = resp.json()
    assert data["campaign_id"] == 99999
    assert data["total_events"] == 0
    assert data["events"] == []


def test_get_campaign_events_with_data(client, seeded_events):
    campaign_id = seeded_events
    resp = client.get(f"/events/campaign/{campaign_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["campaign_id"] == campaign_id
    assert data["total_events"] >= 4
    assert len(data["events"]) >= 4
    first = data["events"][0]
    assert "event_id" in first
    assert "event_type" in first
    assert "sequence" in first
    assert "timestamp" in first
    assert "payload" in first


def test_get_campaign_events_with_event_type_filter(client, seeded_events):
    campaign_id = seeded_events
    resp = client.get(f"/events/campaign/{campaign_id}?event_type=campaign.started")
    assert resp.status_code == 200
    data = resp.json()
    assert all(e["event_type"] == "campaign.started" for e in data["events"])


def test_get_campaign_events_with_limit_offset(client, seeded_events):
    campaign_id = seeded_events
    resp = client.get(f"/events/campaign/{campaign_id}?limit=2&offset=1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["events"]) <= 2


def test_get_campaign_events_limit_max(client, seeded_events):
    """limit > 1000 should be rejected (422)."""
    resp = client.get(f"/events/campaign/{seeded_events}?limit=9999")
    assert resp.status_code == 422


# ── GET /events/campaign/{id}/state ──────────────────────────────────────────

def test_get_campaign_state(client, seeded_events):
    campaign_id = seeded_events
    mock_state = MagicMock()
    mock_state.summary = {"campaign_id": campaign_id, "status": "completed"}
    mock_engine = AsyncMock()
    mock_engine.replay = AsyncMock(return_value=mock_state)

    with patch.object(mod, "get_replay_engine", return_value=mock_engine):
        resp = client.get(f"/events/campaign/{campaign_id}/state")
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


def test_get_campaign_state_with_at_sequence(client, seeded_events):
    campaign_id = seeded_events
    mock_state = MagicMock()
    mock_state.summary = {"campaign_id": campaign_id, "status": "running"}
    mock_engine = AsyncMock()
    mock_engine.replay = AsyncMock(return_value=mock_state)

    with patch.object(mod, "get_replay_engine", return_value=mock_engine):
        resp = client.get(f"/events/campaign/{campaign_id}/state?at_sequence=2")
    assert resp.status_code == 200
    mock_engine.replay.assert_called_once_with(campaign_id, up_to_sequence=2)


# ── GET /events/campaign/{id}/diff ───────────────────────────────────────────

def test_get_campaign_diff(client, seeded_events):
    campaign_id = seeded_events
    mock_diff = {"added_runs": 1, "score_delta": 0.1}
    mock_engine = AsyncMock()
    mock_engine.diff = AsyncMock(return_value=mock_diff)

    with patch.object(mod, "get_replay_engine", return_value=mock_engine):
        resp = client.get(f"/events/campaign/{campaign_id}/diff?from_sequence=1&to_sequence=3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["from_sequence"] == 1
    assert data["to_sequence"] == 3
    assert data["changes"] == mock_diff


def test_get_campaign_diff_missing_params(client, seeded_events):
    """Missing required from_sequence/to_sequence → 422."""
    resp = client.get(f"/events/campaign/{seeded_events}/diff")
    assert resp.status_code == 422


# ── GET /events/campaign/{id}/timeline ───────────────────────────────────────

def test_get_campaign_timeline_empty(client):
    resp = client.get("/events/campaign/99999/timeline")
    assert resp.status_code == 200
    data = resp.json()
    assert data["milestones"] == []


def test_get_campaign_timeline_with_data(client, seeded_events):
    campaign_id = seeded_events
    resp = client.get(f"/events/campaign/{campaign_id}/timeline")
    assert resp.status_code == 200
    data = resp.json()
    assert "milestones" in data
    milestones = data["milestones"]
    assert len(milestones) >= 1
    for m in milestones:
        assert "sequence" in m
        assert "event_type" in m
        assert "summary" in m


# ── GET /events/types ────────────────────────────────────────────────────────

def test_list_event_types(client):
    resp = client.get("/events/types")
    assert resp.status_code == 200
    data = resp.json()
    assert "event_types" in data
    event_types = data["event_types"]
    assert len(event_types) > 0
    for et in event_types:
        assert "value" in et
        assert "name" in et


# ── _milestone_summary helper ─────────────────────────────────────────────────

def test_milestone_summary_all_branches():
    fn = mod._milestone_summary

    assert fn("campaign.started", {}) == "Campaign started"
    assert fn("campaign.completed", {}) == "Campaign completed"
    assert "Campaign failed" in fn("campaign.failed", {"error": "some error"})
    assert "Campaign failed" in fn("campaign.failed", {})

    s = fn("run.started", {"model_name": "GPT-4", "benchmark_name": "MMLU"})
    assert "GPT-4" in s

    s = fn("run.completed", {"score": 0.9})
    assert "0.9" in s

    s = fn("run.failed", {"error": "timeout"})
    assert "Run failed" in s

    assert fn("genome.computed", {}) == "Failure genome computed"

    s = fn("judge.completed", {"n_evaluated": 5})
    assert "5" in s

    s = fn("sandbagging.signal", {"risk_level": "high"})
    assert "high" in s

    s = fn("injection.detected", {"agent_name": "agent-1"})
    assert "agent-1" in s

    s = fn("goal_drift.detected", {"step": 42})
    assert "42" in s

    # Unknown event type → returns event_type itself
    assert fn("unknown.event", {}) == "unknown.event"
