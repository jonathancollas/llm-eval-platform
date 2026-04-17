"""
Tests for eval_engine/event_pipeline.py
Covers: EventType enum, EvalEvent.create/to_dict, EventBus (subscribe/unsubscribe/emit),
        CampaignState.apply (all event types), CampaignState.diff, CampaignState.summary,
        RunState, get_bus singleton, get_replay_engine.
"""
import asyncio
import os
import secrets
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

from eval_engine.event_pipeline import (
    EventType,
    EvalEvent,
    EventBus,
    CampaignState,
    RunState,
    get_bus,
    get_replay_engine,
    ReplayEngine,
    register_default_subscribers,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _event(event_type: EventType, campaign_id: int = 1, sequence: int = 1,
           payload: dict = None, run_id=None, model_id=None, benchmark_id=None):
    return EvalEvent.create(
        event_type=event_type,
        campaign_id=campaign_id,
        sequence=sequence,
        payload=payload or {},
        run_id=run_id,
        model_id=model_id,
        benchmark_id=benchmark_id,
    )


# ══════════════════════════════════════════════════════════════════════════════
# EventType enum
# ══════════════════════════════════════════════════════════════════════════════

def test_event_type_values_are_strings():
    assert EventType.CAMPAIGN_STARTED == "campaign.started"
    assert EventType.RUN_COMPLETED == "run.completed"
    assert EventType.ITEM_FAILED == "item.failed"


def test_event_type_all_members_present():
    expected = {
        "CAMPAIGN_STARTED", "CAMPAIGN_COMPLETED", "CAMPAIGN_FAILED",
        "CAMPAIGN_CANCELLED", "CAMPAIGN_PROGRESS",
        "RUN_STARTED", "RUN_COMPLETED", "RUN_FAILED",
        "ITEM_STARTED", "ITEM_COMPLETED", "ITEM_FAILED",
        "GENOME_COMPUTED", "JUDGE_COMPLETED", "CONTAMINATION_FLAG",
        "SANDBAGGING_SIGNAL", "AGENT_STEP", "INJECTION_DETECTED", "GOAL_DRIFT_DETECTED",
    }
    actual = {e.name for e in EventType}
    assert expected.issubset(actual)


# ══════════════════════════════════════════════════════════════════════════════
# EvalEvent
# ══════════════════════════════════════════════════════════════════════════════

def test_eval_event_create_returns_frozen():
    ev = _event(EventType.CAMPAIGN_STARTED)
    # Frozen dataclass — mutation should raise
    with pytest.raises(Exception):
        ev.campaign_id = 99


def test_eval_event_create_has_uuid():
    import uuid
    ev = _event(EventType.CAMPAIGN_STARTED)
    uuid.UUID(ev.event_id)  # raises if not a valid UUID


def test_eval_event_create_timestamp_is_iso():
    from datetime import datetime
    ev = _event(EventType.CAMPAIGN_STARTED)
    # Should parse without error
    datetime.fromisoformat(ev.timestamp)


def test_eval_event_create_unique_ids():
    ev1 = _event(EventType.CAMPAIGN_STARTED, sequence=1)
    ev2 = _event(EventType.CAMPAIGN_STARTED, sequence=2)
    assert ev1.event_id != ev2.event_id


def test_eval_event_to_dict_keys():
    ev = _event(EventType.RUN_STARTED, campaign_id=5, sequence=3,
                run_id=10, model_id=2, benchmark_id=3)
    d = ev.to_dict()
    for key in ("event_id", "event_type", "campaign_id", "timestamp",
                "sequence", "payload", "run_id", "model_id", "benchmark_id"):
        assert key in d


def test_eval_event_to_dict_event_type_is_string():
    ev = _event(EventType.RUN_COMPLETED)
    d = ev.to_dict()
    assert d["event_type"] == "run.completed"


def test_eval_event_payload_preserved():
    payload = {"score": 0.87, "num_items": 42}
    ev = _event(EventType.RUN_COMPLETED, payload=payload)
    assert ev.to_dict()["payload"] == payload


# ══════════════════════════════════════════════════════════════════════════════
# EventBus
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def bus():
    """Fresh EventBus for each test (avoids state leakage)."""
    return EventBus()


def test_bus_subscribe_and_receive(bus):
    received = []

    async def handler(event: EvalEvent):
        received.append(event)

    bus.subscribe(handler)

    async def run():
        await bus.emit(EventType.CAMPAIGN_STARTED, campaign_id=1, payload={})

    # Monkeypatch _persist to be a no-op
    async def _noop_persist(event):
        pass
    bus._persist = _noop_persist

    asyncio.run(run())
    assert len(received) == 1
    assert received[0].event_type == EventType.CAMPAIGN_STARTED


def test_bus_subscribe_typed_event_only(bus):
    received = []

    async def handler(event: EvalEvent):
        received.append(event)

    bus.subscribe(handler, EventType.RUN_COMPLETED)

    async def _noop_persist(event):
        pass
    bus._persist = _noop_persist

    async def run():
        await bus.emit(EventType.CAMPAIGN_STARTED, campaign_id=1, payload={})
        await bus.emit(EventType.RUN_COMPLETED, campaign_id=1, payload={"score": 0.9})

    asyncio.run(run())
    assert len(received) == 1
    assert received[0].event_type == EventType.RUN_COMPLETED


def test_bus_unsubscribe_stops_delivery(bus):
    received = []

    async def handler(event: EvalEvent):
        received.append(event)

    bus.subscribe(handler)
    bus.unsubscribe(handler)

    async def _noop_persist(event):
        pass
    bus._persist = _noop_persist

    async def run():
        await bus.emit(EventType.CAMPAIGN_STARTED, campaign_id=1, payload={})

    asyncio.run(run())
    assert received == []


def test_bus_sequence_monotonic_per_campaign(bus):
    sequences = []

    async def handler(event: EvalEvent):
        sequences.append(event.sequence)

    bus.subscribe(handler)

    async def _noop_persist(event):
        pass
    bus._persist = _noop_persist

    async def run():
        for _ in range(5):
            await bus.emit(EventType.CAMPAIGN_PROGRESS, campaign_id=7, payload={})

    asyncio.run(run())
    assert sequences == [1, 2, 3, 4, 5]


def test_bus_sequences_independent_per_campaign(bus):
    seqs = {1: [], 2: []}

    async def handler(event: EvalEvent):
        seqs[event.campaign_id].append(event.sequence)

    bus.subscribe(handler)

    async def _noop_persist(event):
        pass
    bus._persist = _noop_persist

    async def run():
        await bus.emit(EventType.CAMPAIGN_STARTED, campaign_id=1, payload={})
        await bus.emit(EventType.CAMPAIGN_STARTED, campaign_id=2, payload={})
        await bus.emit(EventType.CAMPAIGN_PROGRESS, campaign_id=1, payload={})

    asyncio.run(run())
    assert seqs[1] == [1, 2]
    assert seqs[2] == [1]


def test_bus_subscriber_error_does_not_propagate(bus):
    async def bad_handler(event: EvalEvent):
        raise RuntimeError("subscriber explodes")

    bus.subscribe(bad_handler)

    async def _noop_persist(event):
        pass
    bus._persist = _noop_persist

    async def run():
        # Should not raise
        await bus.emit(EventType.CAMPAIGN_STARTED, campaign_id=1, payload={})

    asyncio.run(run())  # no exception


def test_bus_emit_returns_event(bus):
    async def _noop_persist(event):
        pass
    bus._persist = _noop_persist

    async def run():
        return await bus.emit(EventType.RUN_STARTED, campaign_id=1, payload={}, run_id=5)

    event = asyncio.run(run())
    assert isinstance(event, EvalEvent)
    assert event.run_id == 5


# ══════════════════════════════════════════════════════════════════════════════
# CampaignState.apply — all event branches
# ══════════════════════════════════════════════════════════════════════════════

def test_state_apply_campaign_started():
    state = CampaignState(campaign_id=1)
    state.apply(_event(EventType.CAMPAIGN_STARTED))
    assert state.status == "running"
    assert state.events_applied == 1


def test_state_apply_campaign_completed():
    state = CampaignState(campaign_id=1)
    state.apply(_event(EventType.CAMPAIGN_COMPLETED))
    assert state.status == "completed"
    assert state.progress == 100.0


def test_state_apply_campaign_failed():
    state = CampaignState(campaign_id=1)
    state.apply(_event(EventType.CAMPAIGN_FAILED, payload={"error": "boom"}))
    assert state.status == "failed"
    assert state.error == "boom"


def test_state_apply_campaign_cancelled():
    state = CampaignState(campaign_id=1)
    state.apply(_event(EventType.CAMPAIGN_CANCELLED))
    assert state.status == "cancelled"


def test_state_apply_campaign_progress():
    state = CampaignState(campaign_id=1)
    state.apply(_event(EventType.CAMPAIGN_PROGRESS, payload={"progress": 42.5}))
    assert state.progress == 42.5


def test_state_apply_run_started():
    state = CampaignState(campaign_id=1)
    state.apply(_event(EventType.RUN_STARTED, run_id=10, model_id=2, benchmark_id=3))
    assert 10 in state.runs
    run = state.runs[10]
    assert run.status == "running"
    assert run.model_id == 2


def test_state_apply_run_completed():
    state = CampaignState(campaign_id=1)
    state.apply(_event(EventType.RUN_STARTED, run_id=10, model_id=2, benchmark_id=3))
    state.apply(_event(EventType.RUN_COMPLETED, run_id=10,
                       payload={"score": 0.9, "total_cost_usd": 0.01, "total_latency_ms": 500}))
    run = state.runs[10]
    assert run.status == "completed"
    assert run.score == 0.9
    assert state.total_cost_usd == 0.01


def test_state_apply_run_failed():
    state = CampaignState(campaign_id=1)
    state.apply(_event(EventType.RUN_STARTED, run_id=11, model_id=1, benchmark_id=1))
    state.apply(_event(EventType.RUN_FAILED, run_id=11, payload={"error": "timeout"}))
    assert state.runs[11].status == "failed"
    assert state.runs[11].error == "timeout"


def test_state_apply_item_completed():
    state = CampaignState(campaign_id=1)
    state.apply(_event(EventType.RUN_STARTED, run_id=5, model_id=1, benchmark_id=1))
    state.apply(_event(EventType.ITEM_COMPLETED, run_id=5, payload={"item_index": 2}))
    assert state.completed_items == 1
    assert state.runs[5].items_completed == 1


def test_state_apply_item_failed():
    state = CampaignState(campaign_id=1)
    state.apply(_event(EventType.RUN_STARTED, run_id=5, model_id=1, benchmark_id=1))
    state.apply(_event(EventType.ITEM_FAILED, run_id=5, payload={}))
    assert state.failed_items == 1
    assert state.runs[5].items_failed == 1


def test_state_apply_genome_computed():
    state = CampaignState(campaign_id=1)
    state.apply(_event(EventType.GENOME_COMPUTED))
    assert state.genome_computed is True


def test_state_apply_judge_completed():
    state = CampaignState(campaign_id=1)
    state.apply(_event(EventType.JUDGE_COMPLETED))
    assert state.judge_completed is True


def test_state_apply_sandbagging_signal():
    state = CampaignState(campaign_id=1)
    sig = {"model": "gpt-4", "score": 0.3}
    state.apply(_event(EventType.SANDBAGGING_SIGNAL, payload=sig))
    assert len(state.sandbagging_signals) == 1
    assert state.sandbagging_signals[0] == sig


def test_state_last_event_sequence_updated():
    state = CampaignState(campaign_id=1)
    state.apply(_event(EventType.CAMPAIGN_STARTED, sequence=7))
    assert state.last_event_sequence == 7


# ══════════════════════════════════════════════════════════════════════════════
# CampaignState.diff
# ══════════════════════════════════════════════════════════════════════════════

def test_state_diff_status_change():
    a = CampaignState(campaign_id=1, status="running")
    b = CampaignState(campaign_id=1, status="completed")
    diff = a.diff(b)
    assert "status" in diff
    assert diff["status"] == {"from": "running", "to": "completed"}


def test_state_diff_no_change():
    a = CampaignState(campaign_id=1, status="running", progress=50.0)
    b = CampaignState(campaign_id=1, status="running", progress=50.0)
    diff = a.diff(b)
    assert diff == {}


def test_state_diff_progress_change():
    a = CampaignState(campaign_id=1, progress=20.0)
    b = CampaignState(campaign_id=1, progress=80.0)
    diff = a.diff(b)
    assert "progress" in diff


def test_state_diff_run_added():
    a = CampaignState(campaign_id=1)
    b = CampaignState(campaign_id=1)
    b.runs[42] = RunState(run_id=42, model_id=1, benchmark_id=1, status="running")
    diff = a.diff(b)
    assert "runs" in diff
    assert diff["runs"][42].get("added") is True


# ══════════════════════════════════════════════════════════════════════════════
# CampaignState.summary
# ══════════════════════════════════════════════════════════════════════════════

def test_state_summary_keys():
    state = CampaignState(campaign_id=1)
    s = state.summary
    for key in ("campaign_id", "status", "progress", "runs", "items",
                "total_cost_usd", "events_applied", "last_sequence",
                "genome_computed", "judge_completed", "sandbagging_signals"):
        assert key in s


def test_state_summary_counts_runs():
    state = CampaignState(campaign_id=1)
    state.runs[1] = RunState(1, 1, 1, status="completed")
    state.runs[2] = RunState(2, 1, 2, status="failed")
    state.runs[3] = RunState(3, 2, 1, status="running")
    s = state.summary
    assert s["runs"]["total"] == 3
    assert s["runs"]["completed"] == 1
    assert s["runs"]["failed"] == 1
    assert s["runs"]["running"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# Singletons
# ══════════════════════════════════════════════════════════════════════════════

def test_get_bus_returns_same_instance():
    b1 = get_bus()
    b2 = get_bus()
    assert b1 is b2


def test_get_replay_engine_returns_instance():
    engine = get_replay_engine()
    assert isinstance(engine, ReplayEngine)


def test_register_default_subscribers_does_not_raise():
    """Should be callable multiple times without error."""
    register_default_subscribers()
    register_default_subscribers()


# ══════════════════════════════════════════════════════════════════════════════
# ReplayEngine.replay / diff / _load_events (with mocked DB)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_replay_engine_replay_empty_returns_initial_state():
    """With no events, replay returns a default CampaignState."""
    engine = get_replay_engine()
    from unittest.mock import AsyncMock, patch
    with patch.object(engine.__class__, "_load_events", new=AsyncMock(return_value=[])):
        state = await engine.replay(campaign_id=999)
    assert state.campaign_id == 999
    assert state.status == "pending"


@pytest.mark.asyncio
async def test_replay_engine_replay_applies_events():
    """Replay applies loaded events to reconstruct state."""
    engine = get_replay_engine()
    ev = _event(EventType.CAMPAIGN_STARTED, campaign_id=1, sequence=1,
                payload={"model_ids": [1, 2], "benchmark_ids": [3]})

    from unittest.mock import AsyncMock, patch
    with patch.object(engine.__class__, "_load_events", new=AsyncMock(return_value=[ev])):
        state = await engine.replay(campaign_id=1)
    assert state.status == "running"


@pytest.mark.asyncio
async def test_replay_engine_replay_with_up_to_sequence():
    """up_to_sequence is passed to _load_events."""
    engine = get_replay_engine()
    ev_start = _event(EventType.CAMPAIGN_STARTED, campaign_id=2, sequence=1, payload={})
    ev_done = _event(EventType.CAMPAIGN_COMPLETED, campaign_id=2, sequence=5, payload={"score": 0.9})

    from unittest.mock import AsyncMock, patch

    # Replay only up to sequence 1 → status=running
    async def load_up_to_1(campaign_id, up_to_sequence):
        events = [ev_start, ev_done]
        if up_to_sequence is not None:
            events = [e for e in events if e.sequence <= up_to_sequence]
        return events

    with patch.object(engine.__class__, "_load_events", new=AsyncMock(side_effect=load_up_to_1)):
        state = await engine.replay(campaign_id=2, up_to_sequence=1)
    assert state.status == "running"


@pytest.mark.asyncio
async def test_replay_engine_diff():
    """diff returns state changes between two sequence points."""
    engine = get_replay_engine()
    ev_start = _event(EventType.CAMPAIGN_STARTED, campaign_id=3, sequence=1, payload={})
    ev_complete = _event(EventType.CAMPAIGN_COMPLETED, campaign_id=3, sequence=2,
                         payload={"score": 0.8})

    from unittest.mock import AsyncMock, patch

    async def load_events(campaign_id, up_to_sequence):
        events = [ev_start, ev_complete]
        if up_to_sequence is not None:
            events = [e for e in events if e.sequence <= up_to_sequence]
        return events

    with patch.object(engine.__class__, "_load_events", new=AsyncMock(side_effect=load_events)):
        diff = await engine.diff(campaign_id=3, sequence_a=1, sequence_b=2)
    assert "status" in diff


@pytest.mark.asyncio
async def test_replay_engine_load_events_db_error_returns_empty():
    """When DB raises, _load_events returns [] gracefully."""
    from unittest.mock import patch
    with patch("eval_engine.event_pipeline.Session", side_effect=RuntimeError("DB down")):
        events = await ReplayEngine._load_events(campaign_id=1, up_to_sequence=None)
    assert events == []


# ══════════════════════════════════════════════════════════════════════════════
# _live_telemetry_subscriber
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_live_telemetry_subscriber_ignores_irrelevant_events():
    """Events not in the watch-list return early without DB access."""
    from eval_engine.event_pipeline import _live_telemetry_subscriber
    from unittest.mock import patch

    with patch("eval_engine.event_pipeline.Session") as mock_session_cls:
        ev = _event(EventType.RUN_STARTED, campaign_id=1, payload={})
        await _live_telemetry_subscriber(ev)
    # Session should not be called for non-progress events
    mock_session_cls.assert_not_called()


@pytest.mark.asyncio
async def test_live_telemetry_subscriber_progress_updates_campaign():
    """CAMPAIGN_PROGRESS event updates campaign fields in DB."""
    from eval_engine.event_pipeline import _live_telemetry_subscriber
    from unittest.mock import MagicMock, patch

    mock_campaign = MagicMock()
    mock_campaign.progress = 0.0

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.get = MagicMock(return_value=mock_campaign)

    with patch("eval_engine.event_pipeline.Session", return_value=mock_session), \
         patch("eval_engine.event_pipeline.engine", MagicMock()):
        ev = _event(EventType.CAMPAIGN_PROGRESS, campaign_id=1,
                    payload={"progress": 50.0, "current_item_index": 5,
                             "current_item_total": 10, "current_item_label": "bench1"})
        await _live_telemetry_subscriber(ev)

    assert mock_campaign.progress == 50.0


@pytest.mark.asyncio
async def test_live_telemetry_subscriber_completed_sets_completed_at():
    """CAMPAIGN_COMPLETED event sets completed_at on the campaign."""
    from eval_engine.event_pipeline import _live_telemetry_subscriber
    from unittest.mock import MagicMock, patch

    mock_campaign = MagicMock()
    mock_campaign.completed_at = None

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.get = MagicMock(return_value=mock_campaign)

    with patch("eval_engine.event_pipeline.Session", return_value=mock_session), \
         patch("eval_engine.event_pipeline.engine", MagicMock()):
        ev = _event(EventType.CAMPAIGN_COMPLETED, campaign_id=1, payload={})
        await _live_telemetry_subscriber(ev)

    assert mock_campaign.completed_at is not None


@pytest.mark.asyncio
async def test_live_telemetry_subscriber_campaign_not_found():
    """When campaign not in DB, returns without error."""
    from eval_engine.event_pipeline import _live_telemetry_subscriber
    from unittest.mock import MagicMock, patch

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.get = MagicMock(return_value=None)

    with patch("eval_engine.event_pipeline.Session", return_value=mock_session), \
         patch("eval_engine.event_pipeline.engine", MagicMock()):
        ev = _event(EventType.CAMPAIGN_PROGRESS, campaign_id=999, payload={"progress": 10.0})
        await _live_telemetry_subscriber(ev)  # no error


@pytest.mark.asyncio
async def test_live_telemetry_subscriber_db_error_is_swallowed():
    """DB errors are swallowed (logged as debug)."""
    from eval_engine.event_pipeline import _live_telemetry_subscriber
    from unittest.mock import patch

    with patch("eval_engine.event_pipeline.Session", side_effect=RuntimeError("DB down")), \
         patch("eval_engine.event_pipeline.engine", MagicMock()):
        ev = _event(EventType.CAMPAIGN_COMPLETED, campaign_id=1, payload={})
        await _live_telemetry_subscriber(ev)  # must not raise


@pytest.mark.asyncio
async def test_live_telemetry_subscriber_item_completed_no_error():
    """ITEM_COMPLETED events don't update campaign fields but don't crash."""
    from eval_engine.event_pipeline import _live_telemetry_subscriber
    from unittest.mock import MagicMock, patch

    mock_campaign = MagicMock()
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.get = MagicMock(return_value=mock_campaign)

    with patch("eval_engine.event_pipeline.Session", return_value=mock_session), \
         patch("eval_engine.event_pipeline.engine", MagicMock()):
        ev = _event(EventType.ITEM_COMPLETED, campaign_id=1, payload={"score": 1.0})
        await _live_telemetry_subscriber(ev)  # no error
