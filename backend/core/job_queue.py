"""
Lightweight async job queue — no Redis, no Celery.
State persisted in SQLite; in-memory tasks for active execution.

Key design decisions:
- _running_tasks tracks active asyncio.Task objects (lost on restart)
- DB status is the source of truth for historical state
- cancel() checks both memory and DB to handle post-restart scenarios
"""
import asyncio
import logging
from typing import Dict

logger = logging.getLogger(__name__)

_running_tasks: Dict[int, asyncio.Task] = {}


def submit_campaign(campaign_id: int, coro) -> None:
    """Submit a campaign coroutine as a background asyncio task."""
    if campaign_id in _running_tasks and not _running_tasks[campaign_id].done():
        logger.warning(f"Campaign {campaign_id} already has a running task — skipping.")
        return

    task = asyncio.create_task(coro, name=f"campaign-{campaign_id}")
    _running_tasks[campaign_id] = task

    def _on_done(t: asyncio.Task) -> None:
        _running_tasks.pop(campaign_id, None)
        if t.cancelled():
            logger.info(f"Campaign {campaign_id} task cancelled.")
        elif exc := t.exception():
            # Should not happen — execute_campaign has its own top-level handler
            logger.error(f"Campaign {campaign_id} task raised unhandled: {exc}", exc_info=exc)
            # Last-resort: mark as failed in DB
            try:
                from sqlmodel import Session
                from core.database import engine
                from core.models import Campaign, JobStatus
                from datetime import datetime
                with Session(engine) as session:
                    c = session.get(Campaign, campaign_id)
                    if c and c.status == JobStatus.RUNNING:
                        c.status = JobStatus.FAILED
                        c.error_message = f"Unhandled task exception: {str(exc)[:300]}"
                        c.completed_at = datetime.utcnow()
                        session.add(c)
                        session.commit()
            except Exception as db_err:
                logger.error(f"Could not persist failure for campaign {campaign_id}: {db_err}")
        else:
            logger.info(f"Campaign {campaign_id} task completed.")

    task.add_done_callback(_on_done)
    logger.info(f"Campaign {campaign_id} submitted as background task.")


def cancel_campaign(campaign_id: int) -> bool:
    """
    Cancel a running campaign.
    Returns True if cancellation was initiated (task found in memory).
    Callers should also check DB status for post-restart scenarios.
    """
    task = _running_tasks.get(campaign_id)
    if task and not task.done():
        task.cancel()
        logger.info(f"Campaign {campaign_id} cancellation requested.")
        return True
    return False


def is_running(campaign_id: int) -> bool:
    task = _running_tasks.get(campaign_id)
    return task is not None and not task.done()
