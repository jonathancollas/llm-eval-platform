"""
Job queue — supports two modes:
- In-memory asyncio tasks (default, dev/single-worker)
- Redis-backed queue (production, multi-worker)

Mode is auto-detected from REDIS_URL config.
"""
import asyncio
import logging
from typing import Dict

logger = logging.getLogger(__name__)

_running_tasks: Dict[int, asyncio.Task] = {}
_redis_client = None


def _get_redis():
    """Lazy init Redis client."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        from core.config import get_settings
        settings = get_settings()
        if not settings.redis_url:
            return None
        import redis
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        _redis_client.ping()
        logger.info(f"Redis connected: {settings.redis_url}")
        return _redis_client
    except ImportError:
        logger.debug("redis package not installed — using in-memory queue")
        return None
    except Exception as e:
        logger.warning(f"Redis unavailable, falling back to in-memory: {e}")
        return None


def submit_campaign(campaign_id: int, coro) -> None:
    """Submit a campaign for execution."""
    r = _get_redis()

    if r:
        # Redis mode: store job metadata + still run locally via asyncio
        # (True distributed queue requires a worker process — this is the bridge)
        try:
            r.hset(f"campaign:{campaign_id}", mapping={
                "status": "running",
                "worker": "main",
            })
            r.expire(f"campaign:{campaign_id}", 3600)
        except Exception as e:
            logger.warning(f"Redis hset failed (non-blocking): {e}")

    # Always use asyncio task for actual execution
    if campaign_id in _running_tasks and not _running_tasks[campaign_id].done():
        logger.warning(f"Campaign {campaign_id} already has a running task — skipping.")
        return

    task = asyncio.create_task(coro, name=f"campaign-{campaign_id}")
    _running_tasks[campaign_id] = task

    def _on_done(t: asyncio.Task) -> None:
        _running_tasks.pop(campaign_id, None)

        # Clean Redis
        if r:
            try:
                r.delete(f"campaign:{campaign_id}")
            except Exception:
                pass

        if t.cancelled():
            logger.info(f"Campaign {campaign_id} task cancelled.")
        elif exc := t.exception():
            logger.error(f"Campaign {campaign_id} task raised unhandled: {exc}", exc_info=exc)
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
    logger.info(f"Campaign {campaign_id} submitted (redis={'yes' if r else 'no'}).")


def cancel_campaign(campaign_id: int) -> bool:
    """Cancel a running campaign."""
    task = _running_tasks.get(campaign_id)
    if task and not task.done():
        task.cancel()
        r = _get_redis()
        if r:
            try:
                r.delete(f"campaign:{campaign_id}")
            except Exception:
                pass
        logger.info(f"Campaign {campaign_id} cancellation requested.")
        return True
    return False


def is_running(campaign_id: int) -> bool:
    task = _running_tasks.get(campaign_id)
    return task is not None and not task.done()


def get_queue_status() -> dict:
    """Get queue status for monitoring."""
    r = _get_redis()
    in_memory = {cid: not t.done() for cid, t in _running_tasks.items()}

    redis_campaigns = {}
    if r:
        try:
            for key in r.scan_iter("campaign:*"):
                cid = key.split(":")[1]
                redis_campaigns[cid] = r.hgetall(key)
        except Exception:
            pass

    return {
        "mode": "redis" if r else "in_memory",
        "in_memory_tasks": len([v for v in in_memory.values() if v]),
        "redis_tracked": len(redis_campaigns),
        "campaigns": in_memory,
    }
