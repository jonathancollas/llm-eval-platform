"""
Lightweight async job queue — no Redis, no Celery.
Uses asyncio.create_task() for concurrency; state is persisted in SQLite.
"""
import asyncio
import logging
from typing import Callable, Awaitable, Dict, Optional

logger = logging.getLogger(__name__)

# Active tasks: campaign_id -> asyncio.Task
_running_tasks: Dict[int, asyncio.Task] = {}


def submit_campaign(
    campaign_id: int,
    coro: Awaitable,
) -> None:
    """Submit a campaign coroutine as a background asyncio task."""
    if campaign_id in _running_tasks and not _running_tasks[campaign_id].done():
        logger.warning(f"Campaign {campaign_id} is already running.")
        return

    task = asyncio.create_task(coro, name=f"campaign-{campaign_id}")
    _running_tasks[campaign_id] = task

    def _on_done(t: asyncio.Task) -> None:
        if exc := t.exception():
            logger.error(f"Campaign {campaign_id} failed: {exc}", exc_info=exc)
        else:
            logger.info(f"Campaign {campaign_id} completed.")
        _running_tasks.pop(campaign_id, None)

    task.add_done_callback(_on_done)
    logger.info(f"Campaign {campaign_id} submitted.")


def cancel_campaign(campaign_id: int) -> bool:
    """Cancel a running campaign task. Returns True if cancelled."""
    task = _running_tasks.get(campaign_id)
    if task and not task.done():
        task.cancel()
        return True
    return False


def is_running(campaign_id: int) -> bool:
    task = _running_tasks.get(campaign_id)
    return task is not None and not task.done()
