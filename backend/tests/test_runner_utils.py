"""
Tests for eval_engine/runner.py
Covers: _format_eta (all branches), _mark_campaign (success + DB error),
        error classification logic tested through _mark_campaign, execute_campaign
        early-return paths.
"""
import asyncio
import os
import secrets
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import SQLModel, Session, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

from eval_engine.runner import _format_eta, _mark_campaign, execute_campaign
from core.models import Campaign, JobStatus


# ── DB fixture ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db_engine(tmp_path_factory):
    db = tmp_path_factory.mktemp("runner_tests") / "runner.db"
    from sqlmodel import create_engine as _ce
    engine = _ce(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


# ══════════════════════════════════════════════════════════════════════════════
# _format_eta
# ══════════════════════════════════════════════════════════════════════════════

def test_format_eta_seconds_only():
    assert _format_eta(0) == "0s"
    assert _format_eta(59) == "59s"
    assert _format_eta(30) == "30s"


def test_format_eta_minutes_and_seconds():
    assert _format_eta(60) == "1m 0s"
    assert _format_eta(90) == "1m 30s"
    assert _format_eta(3599) == "59m 59s"


def test_format_eta_hours_and_minutes():
    assert _format_eta(3600) == "1h 0m"
    assert _format_eta(3661) == "1h 1m"
    assert _format_eta(7200) == "2h 0m"
    assert _format_eta(7320) == "2h 2m"


def test_format_eta_boundary_at_60():
    # Exactly 60s should be "1m 0s"
    assert _format_eta(60) == "1m 0s"


def test_format_eta_boundary_at_3600():
    # Exactly 3600s should be "1h 0m"
    assert _format_eta(3600) == "1h 0m"


def test_format_eta_large_value():
    result = _format_eta(86400)  # 24 hours
    assert "h" in result


# ══════════════════════════════════════════════════════════════════════════════
# _mark_campaign
# ══════════════════════════════════════════════════════════════════════════════

def test_mark_campaign_sets_status(db_engine):
    with Session(db_engine) as s:
        campaign = Campaign(name="Test", status=JobStatus.RUNNING, progress=50.0)
        s.add(campaign)
        s.commit()
        cid = campaign.id

    # Patch the module-level engine to use the test DB
    import eval_engine.runner as runner_mod
    original_engine = runner_mod.engine
    try:
        runner_mod.engine = db_engine
        _mark_campaign(cid, JobStatus.COMPLETED)
    finally:
        runner_mod.engine = original_engine

    with Session(db_engine) as s:
        c = s.get(Campaign, cid)
        assert c.status == JobStatus.COMPLETED
        assert c.completed_at is not None


def test_mark_campaign_sets_error_message(db_engine):
    with Session(db_engine) as s:
        campaign = Campaign(name="Test Error", status=JobStatus.RUNNING, progress=0.0)
        s.add(campaign)
        s.commit()
        cid = campaign.id

    import eval_engine.runner as runner_mod
    original_engine = runner_mod.engine
    try:
        runner_mod.engine = db_engine
        _mark_campaign(cid, JobStatus.FAILED, "Something went wrong")
    finally:
        runner_mod.engine = original_engine

    with Session(db_engine) as s:
        c = s.get(Campaign, cid)
        assert c.status == JobStatus.FAILED
        assert "Something went wrong" in (c.error_message or "")


def test_mark_campaign_nonexistent_id_does_not_raise(db_engine):
    """Missing campaign_id should be handled gracefully (no exception)."""
    import eval_engine.runner as runner_mod
    original_engine = runner_mod.engine
    try:
        runner_mod.engine = db_engine
        _mark_campaign(99999, JobStatus.FAILED, "ghost")  # should not raise
    finally:
        runner_mod.engine = original_engine


def test_mark_campaign_db_error_does_not_propagate():
    """If DB is broken, _mark_campaign logs and swallows the error."""
    broken_engine = MagicMock()
    broken_engine.__enter__ = MagicMock(side_effect=RuntimeError("DB down"))
    broken_engine.__exit__ = MagicMock(return_value=False)

    import eval_engine.runner as runner_mod
    original_engine = runner_mod.engine

    # Patch Session to raise
    with patch("eval_engine.runner.Session") as MockSession:
        MockSession.side_effect = RuntimeError("DB down")
        try:
            runner_mod.engine = broken_engine
            _mark_campaign(1, JobStatus.FAILED)  # must not raise
        finally:
            runner_mod.engine = original_engine


# ══════════════════════════════════════════════════════════════════════════════
# execute_campaign — top-level error handling
# ══════════════════════════════════════════════════════════════════════════════

def test_execute_campaign_handles_nonexistent_campaign(db_engine):
    """execute_campaign with non-existent ID should complete without crashing."""
    import eval_engine.runner as runner_mod
    original_engine = runner_mod.engine
    try:
        runner_mod.engine = db_engine
        asyncio.run(execute_campaign(99999))
    finally:
        runner_mod.engine = original_engine


def test_execute_campaign_marks_failed_on_inner_crash(db_engine):
    """An inner crash should mark the campaign as FAILED."""
    with Session(db_engine) as s:
        campaign = Campaign(name="Crash Test", status=JobStatus.RUNNING, progress=0.0)
        s.add(campaign)
        s.commit()
        cid = campaign.id

    import eval_engine.runner as runner_mod
    original_engine = runner_mod.engine
    try:
        runner_mod.engine = db_engine
        # Simulate crash by patching _execute_campaign_inner
        async def _crash(campaign_id):
            raise RuntimeError("simulated crash")

        with patch("eval_engine.runner._execute_campaign_inner", _crash):
            asyncio.run(execute_campaign(cid))
    finally:
        runner_mod.engine = original_engine

    with Session(db_engine) as s:
        c = s.get(Campaign, cid)
        assert c.status == JobStatus.FAILED


def test_execute_campaign_empty_models_completes(db_engine):
    """A campaign with no models × benchmarks should complete immediately."""
    with Session(db_engine) as s:
        campaign = Campaign(name="Empty Campaign", status=JobStatus.RUNNING, progress=0.0)
        s.add(campaign)
        s.commit()
        cid = campaign.id

    import eval_engine.runner as runner_mod
    from core.relations import get_campaign_model_ids, get_campaign_benchmark_ids
    original_engine = runner_mod.engine
    try:
        runner_mod.engine = db_engine
        with patch("eval_engine.runner.get_campaign_model_ids", return_value=[]), \
             patch("eval_engine.runner.get_campaign_benchmark_ids", return_value=[]):
            asyncio.run(execute_campaign(cid))
    finally:
        runner_mod.engine = original_engine

    with Session(db_engine) as s:
        c = s.get(Campaign, cid)
        assert c.status == JobStatus.COMPLETED
        assert c.progress == 100.0
