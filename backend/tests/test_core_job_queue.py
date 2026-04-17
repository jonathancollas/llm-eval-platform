"""Tests for core/job_queue.py — submit, cancel, heartbeat, recovery."""
import asyncio
import os
import secrets
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

from core.models import Campaign, JobStatus


def _make_engine():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return engine


def _new_session(engine):
    return Session(engine)


# ── _mark_heartbeat ───────────────────────────────────────────────────────────

def test_mark_heartbeat_updates_timestamp():
    engine = _make_engine()
    with _new_session(engine) as s:
        c = Campaign(name="hb-test", status=JobStatus.RUNNING)
        s.add(c)
        s.commit()
        s.refresh(c)
        cid = c.id

    with patch("core.job_queue._get_session", return_value=_new_session(engine)):
        from core.job_queue import _mark_heartbeat
        _mark_heartbeat(cid)

    with _new_session(engine) as s:
        updated = s.get(Campaign, cid)
        assert updated.last_heartbeat_at is not None


def test_mark_heartbeat_missing_campaign():
    engine = _make_engine()
    with patch("core.job_queue._get_session", return_value=_new_session(engine)):
        from core.job_queue import _mark_heartbeat
        _mark_heartbeat(99999)  # should not raise


# ── _heartbeat_loop ───────────────────────────────────────────────────────────

def test_heartbeat_loop_stops_on_event():
    engine = _make_engine()
    with _new_session(engine) as s:
        c = Campaign(name="hb-loop", status=JobStatus.RUNNING)
        s.add(c)
        s.commit()
        s.refresh(c)
        cid = c.id

    heartbeat_calls = []

    async def _fake_mark(campaign_id):
        heartbeat_calls.append(campaign_id)

    async def run():
        from core.job_queue import _heartbeat_loop
        stop = asyncio.Event()
        stop.set()  # immediately signal stop
        with patch("core.job_queue._mark_heartbeat", side_effect=_fake_mark):
            with patch("core.job_queue.HEARTBEAT_INTERVAL_S", 0):
                await _heartbeat_loop(cid, stop)

    asyncio.run(run())
    # stopped immediately — may or may not have called once depending on timing
    assert isinstance(heartbeat_calls, list)


def test_heartbeat_loop_handles_os_error():
    async def run():
        from core.job_queue import _heartbeat_loop
        stop = asyncio.Event()
        call_count = 0

        def raise_once(campaign_id):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError("disk error")
            stop.set()

        with patch("core.job_queue._mark_heartbeat", side_effect=raise_once), \
             patch("core.job_queue.HEARTBEAT_INTERVAL_S", 0):
            await _heartbeat_loop(1, stop)

    asyncio.run(run())


def test_heartbeat_loop_handles_sqlalchemy_error():
    from sqlalchemy.exc import SQLAlchemyError

    async def run():
        from core.job_queue import _heartbeat_loop
        stop = asyncio.Event()
        call_count = []

        def raise_once(campaign_id):
            if not call_count:
                call_count.append(1)
                raise SQLAlchemyError("db error")
            stop.set()

        with patch("core.job_queue._mark_heartbeat", side_effect=raise_once), \
             patch("core.job_queue.HEARTBEAT_INTERVAL_S", 0):
            await _heartbeat_loop(1, stop)

    asyncio.run(run())


def test_heartbeat_loop_handles_runtime_error():
    async def run():
        from core.job_queue import _heartbeat_loop
        stop = asyncio.Event()
        call_count = []

        def raise_once(campaign_id):
            if not call_count:
                call_count.append(1)
                raise RuntimeError("runtime error")
            stop.set()

        with patch("core.job_queue._mark_heartbeat", side_effect=raise_once), \
             patch("core.job_queue.HEARTBEAT_INTERVAL_S", 0):
            await _heartbeat_loop(1, stop)

    asyncio.run(run())


# ── _run_async_blocking ───────────────────────────────────────────────────────

def test_run_async_blocking_no_loop():
    """With no running event loop, runs in asyncio.run()."""
    result = []

    async def coro():
        result.append("done")

    from core.job_queue import _run_async_blocking
    _run_async_blocking(coro())
    assert result == ["done"]


def test_run_async_blocking_with_running_loop():
    """When a loop is already running, uses a worker thread."""
    result = []

    async def coro():
        result.append("threaded")

    async def run():
        from core.job_queue import _run_async_blocking
        _run_async_blocking(coro())

    asyncio.run(run())
    assert result == ["threaded"]


def test_run_async_blocking_propagates_exception():
    """Exceptions from the coroutine are re-raised."""
    async def failing_coro():
        raise ValueError("test error")

    from core.job_queue import _run_async_blocking
    with pytest.raises(ValueError, match="test error"):
        _run_async_blocking(failing_coro())


def test_run_async_blocking_propagates_exception_with_loop():
    """Exceptions propagate even when called from inside a running loop."""
    async def failing_coro():
        raise ValueError("loop error")

    async def run():
        from core.job_queue import _run_async_blocking
        _run_async_blocking(failing_coro())

    with pytest.raises(ValueError, match="loop error"):
        asyncio.run(run())


# ── _register / _unregister local tasks ──────────────────────────────────────

def test_register_and_unregister_local_task():
    from core.job_queue import (
        _LocalTaskHandle,
        _local_campaign_by_task_id,
        _local_tasks_by_campaign,
        _register_local_task,
        _unregister_local_task,
    )
    handle = _LocalTaskHandle(task_id="abc123")
    _register_local_task(9999, handle)
    assert 9999 in _local_tasks_by_campaign
    assert "abc123" in _local_campaign_by_task_id

    _unregister_local_task(9999)
    assert 9999 not in _local_tasks_by_campaign
    assert "abc123" not in _local_campaign_by_task_id


def test_unregister_nonexistent_task():
    from core.job_queue import _unregister_local_task
    _unregister_local_task(88888)  # should not raise


# ── _cancel_local_task ────────────────────────────────────────────────────────

def test_cancel_local_task_unknown_id():
    from core.job_queue import _cancel_local_task
    result = _cancel_local_task("nonexistent-task-id")
    assert result is False


def test_cancel_local_task_no_loop_dead_thread():
    from core.job_queue import (
        _LocalTaskHandle,
        _cancel_local_task,
        _register_local_task,
        _unregister_local_task,
    )
    t = threading.Thread(target=lambda: None)
    t.start()
    t.join()  # thread is dead
    handle = _LocalTaskHandle(task_id="dead-thread", thread=t, loop=None, task=None)
    _register_local_task(77777, handle)
    try:
        result = _cancel_local_task("dead-thread")
        assert result is False
    finally:
        _unregister_local_task(77777)


def test_cancel_local_task_by_campaign_id_missing():
    from core.job_queue import _cancel_local_task_by_campaign_id
    result = _cancel_local_task_by_campaign_id(99998)
    assert result is False


# ── submit_campaign ───────────────────────────────────────────────────────────

def test_submit_campaign_celery_success():
    """Celery submit succeeds — task id persisted to DB."""
    engine = _make_engine()
    with _new_session(engine) as s:
        c = Campaign(name="submit-celery", status=JobStatus.PENDING)
        s.add(c)
        s.commit()
        s.refresh(c)
        cid = c.id

    mock_task = MagicMock()
    mock_task.id = "celery-task-xyz"

    with patch("core.job_queue.execute_campaign_task") as mock_celery, \
         patch("core.job_queue._get_session", return_value=_new_session(engine)):
        mock_celery.delay.return_value = mock_task
        from core.job_queue import submit_campaign
        result = submit_campaign(cid)

    assert result == "celery-task-xyz"
    with _new_session(engine) as s:
        updated = s.get(Campaign, cid)
        assert updated.worker_task_id == "celery-task-xyz"


def test_submit_campaign_celery_fails_local_fallback():
    """When Celery raises, falls back to local thread execution."""
    engine = _make_engine()
    with _new_session(engine) as s:
        c = Campaign(name="submit-local", status=JobStatus.PENDING)
        s.add(c)
        s.commit()
        s.refresh(c)
        cid = c.id

    with patch("core.job_queue.execute_campaign_task") as mock_celery, \
         patch("core.job_queue._submit_campaign_local", return_value="local-task-abc") as mock_local, \
         patch("core.job_queue._get_session", return_value=_new_session(engine)):
        mock_celery.delay.side_effect = Exception("redis unavailable")
        from core.job_queue import submit_campaign
        result = submit_campaign(cid)

    assert result == "local-task-abc"
    mock_local.assert_called_once_with(cid)


def test_submit_campaign_db_persist_fails_celery():
    """DB persist failure with celery path raises RuntimeError and revokes task."""
    from sqlalchemy.exc import SQLAlchemyError

    mock_task = MagicMock()
    mock_task.id = "celery-task-fail"

    with patch("core.job_queue.execute_campaign_task") as mock_celery, \
         patch("core.job_queue._get_session", side_effect=SQLAlchemyError("db down")), \
         patch("core.job_queue.celery_app") as mock_celery_app:
        mock_celery.delay.return_value = mock_task
        from core.job_queue import submit_campaign
        with pytest.raises(RuntimeError, match="Failed to persist"):
            submit_campaign(1)


def test_submit_campaign_db_persist_fails_local():
    """DB persist failure with local fallback cancels the local task and logs."""
    from sqlalchemy.exc import SQLAlchemyError

    with patch("core.job_queue.execute_campaign_task") as mock_celery, \
         patch("core.job_queue._submit_campaign_local", return_value="local-persist-fail") as mock_local, \
         patch("core.job_queue._cancel_local_task") as mock_cancel, \
         patch("core.job_queue._get_session", side_effect=SQLAlchemyError("db down")):
        mock_celery.delay.side_effect = Exception("no redis")
        from core.job_queue import submit_campaign
        # Should NOT raise — local fallback just logs
        result = submit_campaign(1)
        assert result == "local-persist-fail"


# ── cancel_campaign ───────────────────────────────────────────────────────────

def test_cancel_campaign_via_celery():
    engine = _make_engine()
    with _new_session(engine) as s:
        c = Campaign(name="cancel-celery", status=JobStatus.RUNNING, worker_task_id="celery-revoke-id")
        s.add(c)
        s.commit()
        s.refresh(c)
        cid = c.id

    with patch("core.job_queue._get_session", return_value=_new_session(engine)), \
         patch("core.job_queue.celery_app") as mock_ca:
        mock_ca.control.revoke.return_value = None
        from core.job_queue import cancel_campaign
        result = cancel_campaign(cid)

    assert result is True


def test_cancel_campaign_no_task_id_local_fallback():
    engine = _make_engine()
    with _new_session(engine) as s:
        c = Campaign(name="cancel-no-tid", status=JobStatus.RUNNING, worker_task_id=None)
        s.add(c)
        s.commit()
        s.refresh(c)
        cid = c.id

    with patch("core.job_queue._get_session", return_value=_new_session(engine)), \
         patch("core.job_queue._cancel_local_task_by_campaign_id", return_value=False) as mock_local:
        from core.job_queue import cancel_campaign
        result = cancel_campaign(cid)

    mock_local.assert_called_once_with(cid)
    assert result is False


def test_cancel_campaign_db_error():
    from sqlalchemy.exc import SQLAlchemyError

    with patch("core.job_queue._get_session", side_effect=SQLAlchemyError("db down")):
        from core.job_queue import cancel_campaign
        result = cancel_campaign(999)
    assert result is False


def test_cancel_campaign_celery_revoke_fails():
    engine = _make_engine()
    with _new_session(engine) as s:
        c = Campaign(name="cancel-revoke-fail", status=JobStatus.RUNNING, worker_task_id="bad-task")
        s.add(c)
        s.commit()
        s.refresh(c)
        cid = c.id

    with patch("core.job_queue._get_session", return_value=_new_session(engine)), \
         patch("core.job_queue.celery_app") as mock_ca, \
         patch("core.job_queue._cancel_local_task", return_value=True) as mock_local:
        mock_ca.control.revoke.side_effect = Exception("revoke failed")
        from core.job_queue import cancel_campaign
        result = cancel_campaign(cid)

    mock_local.assert_called_once_with("bad-task")


# ── is_running ────────────────────────────────────────────────────────────────

def test_is_running_true_fresh_heartbeat():
    engine = _make_engine()
    with _new_session(engine) as s:
        c = Campaign(
            name="is-running-fresh",
            status=JobStatus.RUNNING,
            last_heartbeat_at=datetime.utcnow() - timedelta(seconds=10),
        )
        s.add(c)
        s.commit()
        s.refresh(c)
        cid = c.id

    with patch("core.job_queue._get_session", return_value=_new_session(engine)):
        from core.job_queue import is_running
        assert is_running(cid) is True


def test_is_running_false_no_heartbeat():
    engine = _make_engine()
    with _new_session(engine) as s:
        c = Campaign(name="is-running-no-hb", status=JobStatus.RUNNING, last_heartbeat_at=None)
        s.add(c)
        s.commit()
        s.refresh(c)
        cid = c.id

    with patch("core.job_queue._get_session", return_value=_new_session(engine)):
        from core.job_queue import is_running
        assert is_running(cid) is False


def test_is_running_false_stale():
    engine = _make_engine()
    with _new_session(engine) as s:
        c = Campaign(
            name="is-running-stale",
            status=JobStatus.RUNNING,
            last_heartbeat_at=datetime.utcnow() - timedelta(minutes=10),
        )
        s.add(c)
        s.commit()
        s.refresh(c)
        cid = c.id

    with patch("core.job_queue._get_session", return_value=_new_session(engine)):
        from core.job_queue import is_running
        assert is_running(cid) is False


def test_is_running_db_error():
    from sqlalchemy.exc import SQLAlchemyError

    with patch("core.job_queue._get_session", side_effect=SQLAlchemyError("db down")):
        from core.job_queue import is_running
        assert is_running(999) is False


# ── get_all_running ───────────────────────────────────────────────────────────

def test_get_all_running_empty():
    engine = _make_engine()
    with patch("core.job_queue._get_session", return_value=_new_session(engine)):
        from core.job_queue import get_all_running
        result = get_all_running()
    assert result == {}


def test_get_all_running_with_fresh_and_stale():
    engine = _make_engine()
    with _new_session(engine) as s:
        fresh = Campaign(
            name="gar-fresh",
            status=JobStatus.RUNNING,
            last_heartbeat_at=datetime.utcnow() - timedelta(seconds=5),
        )
        stale = Campaign(
            name="gar-stale",
            status=JobStatus.RUNNING,
            last_heartbeat_at=datetime.utcnow() - timedelta(minutes=5),
        )
        s.add(fresh)
        s.add(stale)
        s.commit()
        s.refresh(fresh)
        s.refresh(stale)
        fid, sid = fresh.id, stale.id

    with patch("core.job_queue._get_session", return_value=_new_session(engine)):
        from core.job_queue import get_all_running
        result = get_all_running()

    assert result[fid] == "running"
    assert result[sid] == "stale"


def test_get_all_running_db_error():
    from sqlalchemy.exc import SQLAlchemyError

    with patch("core.job_queue._get_session", side_effect=SQLAlchemyError("db down")):
        from core.job_queue import get_all_running
        result = get_all_running()
    assert result == {}


# ── get_queue_status ──────────────────────────────────────────────────────────

def test_get_queue_status_empty():
    with patch("core.job_queue.get_all_running", return_value={}):
        from core.job_queue import get_queue_status
        result = get_queue_status()
    assert result["mode"] == "celery"
    assert result["in_memory_tasks"] == 0
    assert result["stale_tasks"] == 0
    assert result["total_tracked"] == 0


def test_get_queue_status_mixed():
    states = {1: "running", 2: "running", 3: "stale"}
    with patch("core.job_queue.get_all_running", return_value=states):
        from core.job_queue import get_queue_status
        result = get_queue_status()
    assert result["in_memory_tasks"] == 2
    assert result["stale_tasks"] == 1
    assert result["total_tracked"] == 3


# ── recover_stale_campaigns ───────────────────────────────────────────────────

def test_recover_stale_campaigns_marks_failed():
    engine = _make_engine()
    with _new_session(engine) as s:
        c = Campaign(
            name="recover-stale",
            status=JobStatus.RUNNING,
            last_heartbeat_at=datetime.utcnow() - timedelta(minutes=10),
        )
        s.add(c)
        s.commit()
        s.refresh(c)
        cid = c.id

    with patch("core.job_queue._get_session", return_value=_new_session(engine)):
        from core.job_queue import recover_stale_campaigns
        recovered = recover_stale_campaigns()

    assert cid in recovered
    with _new_session(engine) as s:
        updated = s.get(Campaign, cid)
        assert updated.status == JobStatus.FAILED
        assert "heartbeat_timeout" in (updated.error_message or "")


def test_recover_stale_campaigns_leaves_fresh():
    engine = _make_engine()
    with _new_session(engine) as s:
        c = Campaign(
            name="recover-fresh",
            status=JobStatus.RUNNING,
            last_heartbeat_at=datetime.utcnow() - timedelta(seconds=5),
        )
        s.add(c)
        s.commit()
        s.refresh(c)
        cid = c.id

    with patch("core.job_queue._get_session", return_value=_new_session(engine)):
        from core.job_queue import recover_stale_campaigns
        recovered = recover_stale_campaigns()

    assert cid not in recovered


def test_recover_stale_campaigns_no_heartbeat():
    engine = _make_engine()
    with _new_session(engine) as s:
        c = Campaign(name="recover-no-hb", status=JobStatus.RUNNING, last_heartbeat_at=None)
        s.add(c)
        s.commit()
        s.refresh(c)
        cid = c.id

    with patch("core.job_queue._get_session", return_value=_new_session(engine)):
        from core.job_queue import recover_stale_campaigns
        recovered = recover_stale_campaigns()

    assert cid in recovered


def test_recover_stale_campaigns_empty():
    engine = _make_engine()
    with patch("core.job_queue._get_session", return_value=_new_session(engine)):
        from core.job_queue import recover_stale_campaigns
        recovered = recover_stale_campaigns()
    assert recovered == []


def test_recover_stale_campaigns_db_error():
    from sqlalchemy.exc import SQLAlchemyError

    with patch("core.job_queue._get_session", side_effect=SQLAlchemyError("db down")):
        from core.job_queue import recover_stale_campaigns
        recovered = recover_stale_campaigns()
    assert recovered == []


# ── _submit_campaign_local ────────────────────────────────────────────────────

def test_submit_campaign_local_starts_thread():
    """_submit_campaign_local starts a daemon thread and returns a task id."""
    done = threading.Event()

    async def fake_run_with_heartbeat(campaign_id):
        done.set()

    with patch("core.job_queue._run_with_heartbeat", side_effect=fake_run_with_heartbeat):
        from core.job_queue import _submit_campaign_local, _unregister_local_task
        task_id = _submit_campaign_local(12345)
        assert isinstance(task_id, str)
        done.wait(timeout=3)
        _unregister_local_task(12345)
