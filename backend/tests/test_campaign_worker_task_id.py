"""Regression: Campaign.worker_task_id must persist so cancel can revoke the worker.

The DB column was added via alembic / _migrate_add_columns, but the SQLModel
omitted the field. submit_campaign then raised ValueError after the job was
already enqueued, so POST /campaigns/{id}/run returned 500 while the worker
kept running. Cancel could not read the task id either.

SQLite also strips tzinfo from last_heartbeat_at; comparing it to
datetime.now(UTC) TypeError'd and crashed startup recovery.
"""
import os
import secrets
import sys
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

from core.models import Campaign, JobStatus
from core.utils import as_utc


@pytest.fixture()
def shared_engine(tmp_path, monkeypatch):
    db_path = tmp_path / "worker_task.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    import core.database as core_database

    monkeypatch.setattr(core_database, "engine", engine)
    monkeypatch.setattr(core_database.settings, "database_url", f"sqlite:///{db_path}")
    return engine


def _insert_campaign(engine, **kwargs) -> int:
    defaults = {"name": "enqueue-test", "status": JobStatus.RUNNING}
    defaults.update(kwargs)
    with Session(engine) as session:
        campaign = Campaign(**defaults)
        session.add(campaign)
        session.commit()
        session.refresh(campaign)
        return campaign.id


def test_worker_task_id_round_trips_across_sessions(shared_engine):
    campaign_id = _insert_campaign(shared_engine)
    with Session(shared_engine) as session:
        campaign = session.get(Campaign, campaign_id)
        campaign.worker_task_id = "celery-task-abc"
        session.add(campaign)
        session.commit()

    with Session(shared_engine) as session:
        campaign = session.get(Campaign, campaign_id)
        assert campaign.worker_task_id == "celery-task-abc"


def test_submit_campaign_persists_worker_task_id(shared_engine, monkeypatch):
    import core.job_queue as job_queue

    campaign_id = _insert_campaign(shared_engine, status=JobStatus.PENDING)
    monkeypatch.setattr(
        job_queue.execute_campaign_task,
        "delay",
        lambda cid: SimpleNamespace(id=f"task-for-{cid}"),
    )

    task_id = job_queue.submit_campaign(campaign_id)
    assert task_id == f"task-for-{campaign_id}"

    with Session(shared_engine) as session:
        campaign = session.get(Campaign, campaign_id)
        assert campaign.worker_task_id == task_id
        assert campaign.last_heartbeat_at is not None


def test_cancel_campaign_revokes_persisted_task_id(shared_engine, monkeypatch):
    import core.job_queue as job_queue

    campaign_id = _insert_campaign(shared_engine, worker_task_id="revoke-me")
    revoked = []

    monkeypatch.setattr(
        job_queue.celery_app.control,
        "revoke",
        lambda task_id, terminate=False: revoked.append((task_id, terminate)),
    )

    assert job_queue.cancel_campaign(campaign_id) is True
    assert revoked == [("revoke-me", True)]


def test_as_utc_coerces_naive_sqlite_datetime():
    naive = datetime(2026, 8, 30, 11, 0, 0)
    aware = as_utc(naive)
    assert aware is not None
    assert aware.tzinfo is not None
    assert (datetime.now(UTC) - aware).total_seconds() > 0
    assert as_utc(None) is None


def test_reset_stuck_campaigns_survives_naive_heartbeat(shared_engine):
    from core.database import _reset_stuck_campaigns

    stale = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=10)
    fresh = datetime.now(UTC).replace(tzinfo=None)

    stale_id = _insert_campaign(shared_engine, name="stale", last_heartbeat_at=stale)
    fresh_id = _insert_campaign(shared_engine, name="fresh", last_heartbeat_at=fresh)

    _reset_stuck_campaigns()

    with Session(shared_engine) as session:
        assert session.get(Campaign, stale_id).status == JobStatus.FAILED
        assert session.get(Campaign, fresh_id).status == JobStatus.RUNNING


def test_is_running_survives_naive_heartbeat(shared_engine):
    import core.job_queue as job_queue

    fresh = datetime.now(UTC).replace(tzinfo=None)
    campaign_id = _insert_campaign(shared_engine, last_heartbeat_at=fresh)
    assert job_queue.is_running(campaign_id) is True
