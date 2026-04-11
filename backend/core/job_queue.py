"""
Durable Job Queue (#S3)
========================
DB-backed heartbeat state + asyncio.Lock for thread-safe task dict.

Security/reliability fixes:
  - asyncio.Lock() for _running_tasks (#Medium race condition)
  - Specific exception types instead of broad except Exception (#Medium)
  - Heartbeat: running campaigns ping DB every 30s
  - Stale campaigns (no ping >2min) recovered on startup
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Coroutine, Optional

from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_S = 30
STALE_THRESHOLD_S    = 120

# ── Thread-safe task registry ─────────────────────────────────────────────────
_running_tasks: dict[int, asyncio.Task] = {}
_tasks_lock = asyncio.Lock()


def _get_session():
    from core.database import engine
    from sqlmodel import Session
    return Session(engine)


async def _heartbeat_loop(campaign_id: int, stop_event: asyncio.Event) -> None:
    """Ping Campaign.last_heartbeat_at every 30s while campaign runs."""
    from core.models import Campaign
    while not stop_event.is_set():
        try:
            with _get_session() as session:
                c = session.get(Campaign, campaign_id)
                if c:
                    c.last_heartbeat_at = datetime.utcnow()
                    session.add(c)
                    session.commit()
        except OSError as e:
            logger.warning(f"[heartbeat] DB IO error for campaign {campaign_id}: {e}")
        except RuntimeError as e:
            logger.warning(f"[heartbeat] Runtime error for campaign {campaign_id}: {e}")
        await asyncio.sleep(HEARTBEAT_INTERVAL_S)


async def _run_with_heartbeat(campaign_id: int, coro: Coroutine) -> None:
    stop_event = asyncio.Event()
    heartbeat = asyncio.create_task(
        _heartbeat_loop(campaign_id, stop_event),
        name=f"heartbeat-{campaign_id}"
    )
    try:
        await coro
    finally:
        stop_event.set()
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass


async def submit(campaign_id: int, coro: Coroutine) -> asyncio.Task:
    """Submit a campaign coroutine for execution. Thread-safe via asyncio.Lock."""
    async with _tasks_lock:
        existing = _running_tasks.get(campaign_id)
        if existing and not existing.done():
            raise RuntimeError(f"Campaign {campaign_id} is already running.")

        task = asyncio.create_task(
            _run_with_heartbeat(campaign_id, coro),
            name=f"campaign-{campaign_id}"
        )
        _running_tasks[campaign_id] = task

    async def _cleanup(t: asyncio.Task):
        async with _tasks_lock:
            _running_tasks.pop(campaign_id, None)

    task.add_done_callback(lambda t: asyncio.ensure_future(_cleanup(t)))
    return task


async def cancel(campaign_id: int) -> bool:
    """Cancel a running campaign. Thread-safe."""
    async with _tasks_lock:
        task = _running_tasks.get(campaign_id)
        if task and not task.done():
            task.cancel()
            return True
    return False


def is_running(campaign_id: int) -> bool:
    """
    Check if campaign is running.
    Checks process-local dict first, then DB heartbeat freshness.
    Not async — safe to call from sync context (reads only).
    """
    task = _running_tasks.get(campaign_id)
    if task and not task.done():
        return True
    try:
        from core.models import Campaign, JobStatus
        with _get_session() as session:
            c = session.get(Campaign, campaign_id)
            if c and c.status == JobStatus.RUNNING:
                heartbeat = getattr(c, "last_heartbeat_at", None)
                if heartbeat is None:
                    return False  # Pre-heartbeat campaign
                age = (datetime.utcnow() - heartbeat).total_seconds()
                return age <= STALE_THRESHOLD_S
    except (OSError, SQLAlchemyError):
        pass
    return False


def get_queue_status() -> dict:
    """Return queue status summary for the health endpoint."""
    in_memory = {cid for cid, t in _running_tasks.items() if not t.done()}
    return {
        "mode": "in_memory",
        "in_memory_tasks": len(in_memory),
    }


def get_all_running() -> dict[int, str]:
    """Get all running campaigns {campaign_id: status}. Non-async read."""
    in_memory = {cid: "running" for cid, t in _running_tasks.items() if not t.done()}
    try:
        from core.models import Campaign, JobStatus
        with _get_session() as session:
            from sqlmodel import select
            running = session.exec(
                select(Campaign).where(Campaign.status == JobStatus.RUNNING)
            ).all()
            for c in running:
                if c.id in in_memory:
                    continue
                heartbeat = getattr(c, "last_heartbeat_at", None)
                stale = (heartbeat is None or
                         (datetime.utcnow() - heartbeat).total_seconds() > STALE_THRESHOLD_S)
                in_memory[c.id] = "stale" if stale else "running_elsewhere"
    except OSError as e:
        logger.warning(f"[job_queue] DB read error in get_all_running: {e}")
    return in_memory


async def recover_stale_campaigns() -> list[int]:
    """Mark stale campaigns FAILED. Call on application startup."""
    recovered = []
    try:
        from core.models import Campaign, JobStatus
        with _get_session() as session:
            from sqlmodel import select
            running = session.exec(
                select(Campaign).where(Campaign.status == JobStatus.RUNNING)
            ).all()
            for c in running:
                heartbeat = getattr(c, "last_heartbeat_at", None)
                stale = (heartbeat is None or
                         (datetime.utcnow() - heartbeat).total_seconds() > STALE_THRESHOLD_S)
                if stale and c.id not in _running_tasks:
                    c.status = JobStatus.FAILED
                    c.error_message = (
                        f"Campaign failed: heartbeat lost (last: {heartbeat or 'never'}). "
                        "Process restarted. Please re-run."
                    )
                    session.add(c)
                    recovered.append(c.id)
                    logger.warning(f"[recovery] Campaign {c.id} marked FAILED")
            if recovered:
                session.commit()
    except OSError as e:
        logger.error(f"[recovery] DB error: {e}")
    except RuntimeError as e:
        logger.error(f"[recovery] Runtime error: {e}")
    return recovered
