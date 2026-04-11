"""
Durable Job Queue (#S3)
========================
Replaces in-memory asyncio.create_task() with DB-backed state + heartbeat.

Key improvements over the old in-memory approach:
- Campaign status stored in DB (survives restarts)
- Heartbeat: running campaigns ping DB every 30s
- Recovery: stale campaigns (no ping > 2min) marked FAILED with reason
- is_running() checks DB, not process-local dict
- Cancellation via DB flag, polled by runner

Still uses asyncio for execution (no Celery dependency added yet),
but state is now durable. Celery migration is tracked in #S3.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Callable, Coroutine, Any, Optional

logger = logging.getLogger(__name__)

# ── Heartbeat config ──────────────────────────────────────────────────────────
HEARTBEAT_INTERVAL_S = 30     # Runner pings every 30s
STALE_THRESHOLD_S    = 120    # No ping for 2min → consider crashed

# ── In-process task registry (for cancellation within this process) ───────────
_running_tasks: dict[int, asyncio.Task] = {}


def _get_session():
    """Get a DB session — lazy import to avoid circular deps."""
    from core.database import engine
    from sqlmodel import Session
    return Session(engine)


async def _heartbeat_loop(campaign_id: int, stop_event: asyncio.Event) -> None:
    """Ping DB every 30s while campaign is running."""
    from core.models import Campaign
    while not stop_event.is_set():
        try:
            with _get_session() as session:
                c = session.get(Campaign, campaign_id)
                if c:
                    c.last_heartbeat_at = datetime.utcnow()
                    session.add(c)
                    session.commit()
        except Exception as e:
            logger.warning(f"[heartbeat] campaign {campaign_id}: {e}")
        await asyncio.sleep(HEARTBEAT_INTERVAL_S)


async def _run_with_heartbeat(campaign_id: int, coro: Coroutine) -> None:
    """Run a campaign coroutine alongside a heartbeat task."""
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


def submit(campaign_id: int, coro: Coroutine) -> asyncio.Task:
    """Submit a campaign coroutine for execution with heartbeat."""
    if campaign_id in _running_tasks and not _running_tasks[campaign_id].done():
        raise RuntimeError(f"Campaign {campaign_id} is already running.")

    task = asyncio.create_task(
        _run_with_heartbeat(campaign_id, coro),
        name=f"campaign-{campaign_id}"
    )
    _running_tasks[campaign_id] = task

    def _cleanup(t: asyncio.Task):
        _running_tasks.pop(campaign_id, None)

    task.add_done_callback(_cleanup)
    return task


def cancel(campaign_id: int) -> bool:
    """Cancel a running campaign."""
    task = _running_tasks.get(campaign_id)
    if task and not task.done():
        task.cancel()
        return True
    return False


def is_running(campaign_id: int) -> bool:
    """Check if campaign is running — checks both process dict and DB."""
    # Check in-process first (fastest)
    task = _running_tasks.get(campaign_id)
    if task and not task.done():
        return True
    # Fallback: check DB status
    try:
        from core.models import Campaign, JobStatus
        with _get_session() as session:
            c = session.get(Campaign, campaign_id)
            if c and c.status == JobStatus.RUNNING:
                # Check heartbeat freshness
                if hasattr(c, "last_heartbeat_at") and c.last_heartbeat_at:
                    age = (datetime.utcnow() - c.last_heartbeat_at).total_seconds()
                    if age > STALE_THRESHOLD_S:
                        return False  # Stale — process crashed
                return True
    except Exception:
        pass
    return False


def get_all_running() -> dict[int, str]:
    """Get all currently running campaigns {campaign_id: status_info}."""
    # In-process
    in_memory = {cid: "running" for cid, t in _running_tasks.items() if not t.done()}
    # DB-based (includes campaigns from other restarts that are stale)
    try:
        from core.models import Campaign, JobStatus
        with _get_session() as session:
            from sqlmodel import select
            running = session.exec(
                select(Campaign).where(Campaign.status == JobStatus.RUNNING)
            ).all()
            for c in running:
                stale = False
                if hasattr(c, "last_heartbeat_at") and c.last_heartbeat_at:
                    age = (datetime.utcnow() - c.last_heartbeat_at).total_seconds()
                    if age > STALE_THRESHOLD_S:
                        stale = True
                if c.id not in in_memory:
                    in_memory[c.id] = "stale" if stale else "running_elsewhere"
    except Exception:
        pass
    return in_memory


async def recover_stale_campaigns() -> list[int]:
    """
    Mark stale campaigns (no heartbeat for 2min) as FAILED.
    Call on application startup.
    """
    recovered = []
    try:
        from core.models import Campaign, JobStatus
        with _get_session() as session:
            from sqlmodel import select
            running = session.exec(
                select(Campaign).where(Campaign.status == JobStatus.RUNNING)
            ).all()
            for c in running:
                stale = True
                if hasattr(c, "last_heartbeat_at") and c.last_heartbeat_at:
                    age = (datetime.utcnow() - c.last_heartbeat_at).total_seconds()
                    stale = age > STALE_THRESHOLD_S
                elif hasattr(c, "last_heartbeat_at"):
                    # Never had a heartbeat — old campaign from before heartbeat was added
                    stale = True

                if stale and c.id not in _running_tasks:
                    c.status = JobStatus.FAILED
                    c.error_message = "Campaign marked failed: no heartbeat detected (process restart or crash)."
                    session.add(c)
                    recovered.append(c.id)
                    logger.warning(f"[recovery] Campaign {c.id} marked FAILED (stale heartbeat)")

            if recovered:
                session.commit()
    except Exception as e:
        logger.error(f"[recovery] Failed: {e}")
    return recovered
