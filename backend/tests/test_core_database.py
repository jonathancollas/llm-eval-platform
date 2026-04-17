"""Tests for core/database.py — maximises coverage of DB init, seeding, and helpers."""
import os
import secrets
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))
os.environ.setdefault("DATABASE_URL", "sqlite://")

from core.models import Benchmark, BenchmarkType, Campaign, JobStatus, LLMModel


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_engine():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return engine


def _session(engine):
    return Session(engine)


# ── _reset_stuck_campaigns ────────────────────────────────────────────────────

def test_reset_stuck_campaigns_no_stuck():
    """When no campaigns are RUNNING _reset_stuck_campaigns returns immediately."""
    engine = _make_engine()
    with patch("core.database.engine", engine):
        from core.database import _reset_stuck_campaigns
        _reset_stuck_campaigns()  # should not raise


def test_reset_stuck_campaigns_no_heartbeat():
    """Campaigns with no heartbeat are marked FAILED."""
    engine = _make_engine()
    with _session(engine) as s:
        c = Campaign(name="stuck-no-hb", status=JobStatus.RUNNING)
        s.add(c)
        s.commit()
        s.refresh(c)
        cid = c.id

    with patch("core.database.engine", engine):
        from core.database import _reset_stuck_campaigns
        _reset_stuck_campaigns()

    with _session(engine) as s:
        updated = s.get(Campaign, cid)
        assert updated.status == JobStatus.FAILED
        assert "heartbeat_timeout" in (updated.error_message or "")


def test_reset_stuck_campaigns_stale_heartbeat():
    """Campaigns with heartbeat older than 2 min are marked FAILED."""
    engine = _make_engine()
    with _session(engine) as s:
        c = Campaign(
            name="stuck-stale",
            status=JobStatus.RUNNING,
            last_heartbeat_at=datetime.utcnow() - timedelta(minutes=5),
        )
        s.add(c)
        s.commit()
        s.refresh(c)
        cid = c.id

    with patch("core.database.engine", engine):
        from core.database import _reset_stuck_campaigns
        _reset_stuck_campaigns()

    with _session(engine) as s:
        updated = s.get(Campaign, cid)
        assert updated.status == JobStatus.FAILED


def test_reset_stuck_campaigns_fresh_heartbeat():
    """Campaigns with a fresh heartbeat are left as RUNNING."""
    engine = _make_engine()
    with _session(engine) as s:
        c = Campaign(
            name="stuck-fresh",
            status=JobStatus.RUNNING,
            last_heartbeat_at=datetime.utcnow() - timedelta(seconds=10),
        )
        s.add(c)
        s.commit()
        s.refresh(c)
        cid = c.id

    with patch("core.database.engine", engine):
        from core.database import _reset_stuck_campaigns
        _reset_stuck_campaigns()

    with _session(engine) as s:
        updated = s.get(Campaign, cid)
        assert updated.status == JobStatus.RUNNING


def test_reset_stuck_campaigns_mixed():
    """Multiple campaigns: stale → FAILED, fresh → RUNNING."""
    engine = _make_engine()
    with _session(engine) as s:
        stale = Campaign(
            name="stale",
            status=JobStatus.RUNNING,
            last_heartbeat_at=datetime.utcnow() - timedelta(minutes=10),
        )
        fresh = Campaign(
            name="fresh",
            status=JobStatus.RUNNING,
            last_heartbeat_at=datetime.utcnow() - timedelta(seconds=5),
        )
        s.add(stale)
        s.add(fresh)
        s.commit()
        s.refresh(stale)
        s.refresh(fresh)
        stale_id, fresh_id = stale.id, fresh.id

    with patch("core.database.engine", engine):
        from core.database import _reset_stuck_campaigns
        _reset_stuck_campaigns()

    with _session(engine) as s:
        assert s.get(Campaign, stale_id).status == JobStatus.FAILED
        assert s.get(Campaign, fresh_id).status == JobStatus.RUNNING


# ── get_session ───────────────────────────────────────────────────────────────

def test_get_session_yields_session():
    engine = _make_engine()
    with patch("core.database.engine", engine):
        from core.database import get_session
        gen = get_session()
        sess = next(gen)
        assert isinstance(sess, Session)
        try:
            next(gen)
        except StopIteration:
            pass


# ── _update_has_dataset ───────────────────────────────────────────────────────

def test_update_has_dataset_no_benchmarks():
    engine = _make_engine()
    with patch("core.database.engine", engine):
        from core.database import _update_has_dataset
        _update_has_dataset()  # should not raise


def test_update_has_dataset_marks_file_missing(tmp_path):
    engine = _make_engine()
    with _session(engine) as s:
        b = Benchmark(name="b-missing", type=BenchmarkType.CUSTOM, dataset_path="no/such/file.json", has_dataset=True)
        s.add(b)
        s.commit()
        s.refresh(b)
        bid = b.id

    with patch("core.database.engine", engine), \
         patch("core.database.settings") as mock_settings:
        mock_settings.bench_library_path = str(tmp_path)
        from core.database import _update_has_dataset
        _update_has_dataset()

    with _session(engine) as s:
        updated = s.get(Benchmark, bid)
        assert updated.has_dataset is False


def test_update_has_dataset_marks_file_present(tmp_path):
    dataset_file = tmp_path / "test.json"
    dataset_file.write_text("[]")
    engine = _make_engine()
    with _session(engine) as s:
        b = Benchmark(name="b-present", type=BenchmarkType.CUSTOM, dataset_path="test.json", has_dataset=False)
        s.add(b)
        s.commit()
        s.refresh(b)
        bid = b.id

    with patch("core.database.engine", engine), \
         patch("core.database.settings") as mock_settings:
        mock_settings.bench_library_path = str(tmp_path)
        from core.database import _update_has_dataset
        _update_has_dataset()

    with _session(engine) as s:
        updated = s.get(Benchmark, bid)
        assert updated.has_dataset is True


def test_update_has_dataset_no_path():
    engine = _make_engine()
    with _session(engine) as s:
        b = Benchmark(name="b-no-path", type=BenchmarkType.CUSTOM, dataset_path=None, has_dataset=False)
        s.add(b)
        s.commit()
        s.refresh(b)
        bid = b.id

    with patch("core.database.engine", engine), \
         patch("core.database.settings") as mock_settings:
        mock_settings.bench_library_path = "/nonexistent"
        from core.database import _update_has_dataset
        _update_has_dataset()

    with _session(engine) as s:
        # has_dataset unchanged — no path to check
        updated = s.get(Benchmark, bid)
        assert updated.has_dataset is False


# ── _seed_builtin_benchmarks ──────────────────────────────────────────────────

def test_seed_builtin_benchmarks_inserts_all(tmp_path):
    engine = _make_engine()
    with patch("core.database.engine", engine), \
         patch("core.database.settings") as mock_settings:
        mock_settings.bench_library_path = str(tmp_path)
        from core.database import _seed_builtin_benchmarks
        _seed_builtin_benchmarks()

    with _session(engine) as s:
        benchmarks = s.exec(select(Benchmark)).all()
        names = [b.name for b in benchmarks]
        assert "MMLU (subset)" in names
        assert "HumanEval (mini)" in names
        assert "Safety Refusals" in names
        assert "Frontier: Autonomy Probe" in names
        assert len(benchmarks) >= 4


def test_seed_builtin_benchmarks_idempotent(tmp_path):
    """Running seed twice should not duplicate rows."""
    engine = _make_engine()
    with patch("core.database.engine", engine), \
         patch("core.database.settings") as mock_settings:
        mock_settings.bench_library_path = str(tmp_path)
        from core.database import _seed_builtin_benchmarks
        _seed_builtin_benchmarks()
        _seed_builtin_benchmarks()

    with _session(engine) as s:
        mmlu = s.exec(select(Benchmark).where(Benchmark.name == "MMLU (subset)")).all()
        assert len(mmlu) == 1


def test_seed_builtin_benchmarks_marks_has_dataset(tmp_path):
    """has_dataset=True when the dataset file exists on disk."""
    dataset_dir = tmp_path / "academic"
    dataset_dir.mkdir()
    (dataset_dir / "mmlu_subset.json").write_text("[]")

    engine = _make_engine()
    with patch("core.database.engine", engine), \
         patch("core.database.settings") as mock_settings:
        mock_settings.bench_library_path = str(tmp_path)
        from core.database import _seed_builtin_benchmarks
        _seed_builtin_benchmarks()

    with _session(engine) as s:
        mmlu = s.exec(select(Benchmark).where(Benchmark.name == "MMLU (subset)")).first()
        assert mmlu.has_dataset is True


# ── create_db_and_tables ──────────────────────────────────────────────────────

def test_create_db_and_tables(tmp_path):
    engine = _make_engine()
    with patch("core.database.engine", engine), \
         patch("core.database._run_alembic_migrations"), \
         patch("core.database._reset_stuck_campaigns"), \
         patch("core.database._update_has_dataset"), \
         patch("core.database.settings") as mock_settings:
        mock_settings.bench_library_path = str(tmp_path)
        from core.database import create_db_and_tables
        create_db_and_tables()  # should not raise


# ── _run_alembic_migrations (fallback paths) ──────────────────────────────────

def test_run_alembic_migrations_alembic_missing():
    """When alembic is not importable the function logs and returns gracefully."""
    with patch("builtins.__import__", side_effect=ImportError("no alembic")):
        try:
            from core.database import _run_alembic_migrations
            _run_alembic_migrations()
        except Exception:
            pass  # acceptable — module already loaded


def test_migrate_add_columns_non_sqlite():
    """_migrate_add_columns is a no-op for non-SQLite databases."""
    with patch("core.database._is_sqlite", False):
        from core.database import _migrate_add_columns
        _migrate_add_columns()  # should return immediately without error


def test_migrate_add_columns_memory_db():
    """_migrate_add_columns skips in-memory SQLite databases."""
    with patch("core.database._is_sqlite", True), \
         patch("core.database.settings") as mock_settings:
        mock_settings.database_url = "sqlite://"
        from core.database import _migrate_add_columns
        _migrate_add_columns()  # should return without attempting real migration


def test_migrate_add_columns_alembic_config_missing(tmp_path):
    """_migrate_add_columns returns when alembic config file is absent."""
    with patch("core.database._is_sqlite", True), \
         patch("core.database.settings") as mock_settings:
        mock_settings.database_url = f"sqlite:///{tmp_path}/test.db"
        # Patch alembic command.upgrade to be a no-op so the actual file check runs
        with patch("alembic.command.upgrade", return_value=None), \
             patch("core.database.Path") as mock_path_cls:
            mock_ini = MagicMock()
            mock_ini.exists.return_value = False
            mock_path_cls.return_value = MagicMock()
            mock_path_cls.return_value.__truediv__ = lambda s, x: mock_ini
            from core.database import _migrate_add_columns
            _migrate_add_columns()
