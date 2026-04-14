"""
Durable campaign job queue via Celery + Redis.
"""
import asyncio
import logging
import threading
from dataclasses import dataclass
from queue import SimpleQueue
from datetime import datetime
from typing import Optional
from uuid import uuid4

from celery import Celery
from sqlalchemy.exc import SQLAlchemyError

from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

HEARTBEAT_INTERVAL_S = 30
STALE_THRESHOLD_S    = 120
DEFAULT_REDIS_URL = "redis://redis:6379/0"


@dataclass
class _LocalTaskHandle:
    task_id: str
    thread: Optional[threading.Thread] = None
    loop: Optional[asyncio.AbstractEventLoop] = None
    task: Optional[asyncio.Task] = None


_local_tasks_lock = threading.Lock()
_local_tasks_by_campaign: dict[int, _LocalTaskHandle] = {}
_local_campaign_by_task_id: dict[str, int] = {}


def _get_session():
    from core.database import engine
    from sqlmodel import Session
    return Session(engine)


def _mark_heartbeat(campaign_id: int) -> None:
    from core.models import Campaign
    with _get_session() as session:
        c = session.get(Campaign, campaign_id)
        if c:
            c.last_heartbeat_at = datetime.utcnow()
            session.add(c)
            session.commit()
        else:
            logger.warning(f"[heartbeat] Campaign {campaign_id} not found while updating heartbeat")


async def _heartbeat_loop(campaign_id: int, stop_event: asyncio.Event) -> None:
    """Ping Campaign.last_heartbeat_at every 30s while campaign runs."""
    while not stop_event.is_set():
        try:
            _mark_heartbeat(campaign_id)
        except OSError as e:
            logger.warning(f"[heartbeat] DB IO error for campaign {campaign_id}: {e}")
        except SQLAlchemyError as e:
            logger.warning(f"[heartbeat] SQLAlchemy error for campaign {campaign_id}: {e}")
        except RuntimeError as e:
            logger.warning(f"[heartbeat] Runtime error for campaign {campaign_id}: {e}")
        await asyncio.sleep(HEARTBEAT_INTERVAL_S)


async def _run_with_heartbeat(campaign_id: int) -> None:
    from eval_engine.runner import execute_campaign

    stop_event = asyncio.Event()
    heartbeat = asyncio.create_task(
        _heartbeat_loop(campaign_id, stop_event),
        name=f"heartbeat-{campaign_id}"
    )
    try:
        _mark_heartbeat(campaign_id)
        await execute_campaign(campaign_id)
    finally:
        stop_event.set()
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass


redis_url = settings.redis_url or DEFAULT_REDIS_URL
celery_app = Celery("llm_eval_platform", broker=redis_url, backend=None)
celery_app.conf.update(
    task_track_started=False,
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_serializer="json",
    accept_content=["json"],
)


@celery_app.task(
    name="campaign.execute",
    bind=True,
    autoretry_for=(OSError, SQLAlchemyError),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def execute_campaign_task(self, campaign_id: int) -> None:
    _run_async_blocking(_run_with_heartbeat(campaign_id))


def _run_async_blocking(coro) -> None:
    """Run async coroutine safely from sync worker context."""
    try:
        asyncio.get_running_loop()
        has_running_loop = True
    except RuntimeError:
        has_running_loop = False

    if not has_running_loop:
        asyncio.run(coro)
        return

    errors: SimpleQueue[BaseException] = SimpleQueue()

    def _runner() -> None:
        try:
            asyncio.run(coro)
        except BaseException as exc:
            errors.put(exc)

    worker = threading.Thread(target=_runner)
    worker.start()
    worker.join()
    if not errors.empty():
        raise errors.get()


def _register_local_task(campaign_id: int, handle: _LocalTaskHandle) -> None:
    with _local_tasks_lock:
        _local_tasks_by_campaign[campaign_id] = handle
        _local_campaign_by_task_id[handle.task_id] = campaign_id


def _unregister_local_task(campaign_id: int) -> None:
    with _local_tasks_lock:
        handle = _local_tasks_by_campaign.pop(campaign_id, None)
        if handle:
            _local_campaign_by_task_id.pop(handle.task_id, None)


def _submit_campaign_local(campaign_id: int) -> str:
    task_id = uuid4().hex
    handle = _LocalTaskHandle(task_id=task_id)

    def _runner() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            with _local_tasks_lock:
                current = _local_tasks_by_campaign.get(campaign_id)
                if current and current.task_id == task_id:
                    current.loop = loop
            task = loop.create_task(_run_with_heartbeat(campaign_id))
            with _local_tasks_lock:
                current = _local_tasks_by_campaign.get(campaign_id)
                if current and current.task_id == task_id:
                    current.task = task
            try:
                loop.run_until_complete(task)
            except asyncio.CancelledError:
                logger.info(f"[job_queue] Local campaign task {campaign_id} cancelled")
            except Exception:
                logger.exception(f"[job_queue] Local campaign task {campaign_id} failed")
        finally:
            _unregister_local_task(campaign_id)
            loop.close()

    thread = threading.Thread(
        target=_runner,
        name=f"local-campaign-{campaign_id}-{task_id[:8]}",
        daemon=True,
    )
    handle.thread = thread
    _register_local_task(campaign_id, handle)
    thread.start()
    return task_id


def _cancel_local_task(task_id: str) -> bool:
    with _local_tasks_lock:
        campaign_id = _local_campaign_by_task_id.get(task_id)
        if campaign_id is None:
            return False
        handle = _local_tasks_by_campaign.get(campaign_id)
        if not handle:
            return False
        loop = handle.loop
        task = handle.task
        is_alive = handle.thread.is_alive() if handle.thread else False

    if loop and task and not task.done():
        loop.call_soon_threadsafe(task.cancel)
        return True
    return is_alive


def submit_campaign(campaign_id: int) -> str:
    """Submit a campaign for durable execution on Celery workers."""
    using_celery = True
    try:
        task_id = execute_campaign_task.delay(campaign_id).id
    except Exception as e:
        using_celery = False
        logger.warning(
            f"[job_queue] Celery enqueue failed for campaign {campaign_id}; "
            f"falling back to local execution: {e}"
        )
        task_id = _submit_campaign_local(campaign_id)
    try:
        from core.models import Campaign
        with _get_session() as session:
            c = session.get(Campaign, campaign_id)
            if c:
                c.worker_task_id = task_id
                c.last_heartbeat_at = datetime.utcnow()
                session.add(c)
                session.commit()
    except (OSError, SQLAlchemyError) as e:
        if using_celery:
            try:
                celery_app.control.revoke(task_id, terminate=True)
            except Exception as revoke_error:
                logger.warning(f"[job_queue] Failed to revoke orphan task {task_id}: {revoke_error}")
        else:
            _cancel_local_task(task_id)
        logger.warning(f"[job_queue] Could not persist worker task ID for campaign {campaign_id}: {e}")
        raise RuntimeError("Failed to persist worker task metadata.") from e
    return task_id


def cancel_campaign(campaign_id: int) -> bool:
    """Revoke a queued/running campaign task by stored worker task id."""
    task_id: Optional[str] = None
    try:
        from core.models import Campaign
        with _get_session() as session:
            c = session.get(Campaign, campaign_id)
            if c:
                task_id = c.worker_task_id
    except (OSError, SQLAlchemyError):
        logger.warning(f"[job_queue] Could not load task ID for campaign {campaign_id}")
        return False

    if not task_id:
        return False

    try:
        celery_app.control.revoke(task_id, terminate=True)
        return True
    except Exception as e:
        logger.warning(f"[job_queue] Celery revoke failed for campaign {campaign_id}: {e}")
        return _cancel_local_task(task_id)


def is_running(campaign_id: int) -> bool:
    """
    Check if campaign is running based on durable DB state + heartbeat freshness.
    """
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
    """Return a summary dict consumed by the /api/health endpoint."""
    running = get_all_running()
    return {
        "mode": "celery",
        "in_memory_tasks": len([s for s in running.values() if s == "running"]),
        "stale_tasks": len([s for s in running.values() if s == "stale"]),
        "total_tracked": len(running),
    }


def get_all_running() -> dict[int, str]:
    """Get all running campaigns {campaign_id: status}. Non-async read."""
    states: dict[int, str] = {}
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
                states[c.id] = "stale" if stale else "running"
    except (OSError, SQLAlchemyError) as e:
        logger.warning(f"[job_queue] DB read error in get_all_running: {e}")
    return states


def recover_stale_campaigns() -> list[int]:
    """Mark stale RUNNING campaigns FAILED when heartbeat is older than threshold."""
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
                if stale:
                    c.status = JobStatus.FAILED
                    c.error_message = (
                        f"heartbeat_timeout: campaign heartbeat stale (last: {heartbeat or 'never'})."
                    )
                    session.add(c)
                    recovered.append(c.id)
                    logger.warning(f"[recovery] Campaign {c.id} marked FAILED")
            if recovered:
                session.commit()
    except (OSError, SQLAlchemyError) as e:
        logger.error(f"[recovery] DB error: {e}")
    except RuntimeError as e:
        logger.error(f"[recovery] Runtime error: {e}")
    return recovered
