"""Model timestamps must be timezone-aware so inserts succeed.

SQLModel >= 0.0.45 maps ``datetime`` columns to UTCDateTime and rejects
naive values. ``datetime.utcnow()`` defaults made every new Campaign
(and benchmark seed, task row, run start) raise ValueError on commit.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-aware-timestamps-32")
os.environ.setdefault("MERCURY_DEV_MODE", "true")

from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel

from core.models import Benchmark, BenchmarkType, Campaign, JobStatus


def test_campaign_and_benchmark_insert_with_default_timestamps():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        campaign = Campaign(name="aware-ts")
        bench = Benchmark(name="MMLU (subset)", type=BenchmarkType.ACADEMIC, metric="accuracy")
        assert campaign.created_at.tzinfo is not None
        assert bench.created_at.tzinfo is not None
        session.add(campaign)
        session.add(bench)
        session.commit()
        session.refresh(campaign)

        campaign.status = JobStatus.RUNNING
        campaign.started_at = datetime.now(UTC)
        session.add(campaign)
        session.commit()
        session.refresh(campaign)

    assert campaign.id is not None
    assert campaign.started_at is not None
    assert campaign.started_at.tzinfo is not None
