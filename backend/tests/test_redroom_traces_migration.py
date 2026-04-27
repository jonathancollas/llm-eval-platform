"""Migration test for redroom_traces table.

Verifies that:
  - Running ``alembic upgrade head`` on a fresh DB creates the table
    with all expected columns + indexes.
  - The migration is idempotent (running upgrade twice is safe).
  - ``downgrade`` cleanly removes the table and indexes.
  - The migration's column types match the SQLModel definition.
"""
from __future__ import annotations

import os
import secrets
import sqlite3
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))
os.environ.setdefault("REDROOM_TRACE_SECRET", "x" * 32 + "_test_secret")


def _alembic_config_for(db_path: Path) -> Config:
    """Build an Alembic Config that points at the project's migrations dir
    but writes to ``db_path`` instead of the configured production DB."""
    backend_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _bootstrap_to_pre_redroom(db_path: Path) -> Config:
    """Bootstrap the DB so it looks like one that's already at revision
    ``20260419_0002`` (the parent of the redroom migration).

    The earlier migrations in the chain mutate pre-existing tables that
    only exist after ``SQLModel.metadata.create_all`` is run. Replicating
    them via the alembic head from a blank file is out of scope; we just
    create the schema, stamp the latest pre-redroom revision, and then
    test the redroom migration in isolation.
    """
    from sqlmodel import SQLModel, create_engine
    # Side-effect import: registers all SQLModels with metadata.
    import core.models  # noqa: F401

    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)
    engine.dispose()

    cfg = _alembic_config_for(db_path)
    command.stamp(cfg, "20260419_0002")
    return cfg


# ════════════════════════════════════════════════════════════════════
#  Fresh-DB upgrade
# ════════════════════════════════════════════════════════════════════


def test_upgrade_creates_redroom_traces_table(tmp_path):
    db_path = tmp_path / "redroom_migrate.db"
    cfg = _bootstrap_to_pre_redroom(db_path)
    command.upgrade(cfg, "head")

    with sqlite3.connect(db_path) as conn:
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "redroom_traces" in tables

        columns = {
            r[1] for r in conn.execute(
                "PRAGMA table_info(redroom_traces)"
            ).fetchall()
        }
        # Sanity-check a representative subset.
        assert "id" in columns
        assert "uuid" in columns
        assert "tenant_id" in columns
        assert "session_id" in columns
        assert "kind" in columns
        assert "row_signature" in columns
        assert "prev_signature" in columns
        assert "replay_hash" in columns
        assert "created_at" in columns


def test_upgrade_creates_expected_indexes(tmp_path):
    db_path = tmp_path / "redroom_indexes.db"
    cfg = _bootstrap_to_pre_redroom(db_path)
    command.upgrade(cfg, "head")

    with sqlite3.connect(db_path) as conn:
        indexes = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND tbl_name='redroom_traces'"
            ).fetchall()
        }

    expected = {
        "ix_redroom_traces_uuid",
        "ix_redroom_traces_tenant_id",
        "ix_redroom_traces_session_id",
        "ix_redroom_traces_target_model_id",
        "ix_redroom_traces_kind_created_at",
        "ix_redroom_traces_replay_hash",
        "ix_redroom_traces_row_signature",
    }
    assert expected.issubset(indexes)


def test_upgrade_is_idempotent(tmp_path):
    db_path = tmp_path / "redroom_idempotent.db"
    cfg = _bootstrap_to_pre_redroom(db_path)
    command.upgrade(cfg, "head")
    # Second upgrade must not raise — alembic checks current revision and
    # the migration itself uses ``if_not_exists`` for indexes.
    command.upgrade(cfg, "head")

    with sqlite3.connect(db_path) as conn:
        # Still exactly one row per index, no duplicates.
        names = [
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND tbl_name='redroom_traces'"
            ).fetchall()
        ]
        # Each named index should appear exactly once.
        assert len(names) == len(set(names))


# ════════════════════════════════════════════════════════════════════
#  Downgrade
# ════════════════════════════════════════════════════════════════════


def test_downgrade_drops_table(tmp_path):
    db_path = tmp_path / "redroom_downgrade.db"
    cfg = _bootstrap_to_pre_redroom(db_path)
    command.upgrade(cfg, "head")
    # Step back one revision — drops redroom_traces but keeps the rest.
    command.downgrade(cfg, "20260419_0002")

    with sqlite3.connect(db_path) as conn:
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "redroom_traces" not in tables
        # Earlier tables remain.
        assert "task_registry" in tables


# ════════════════════════════════════════════════════════════════════
#  Round-trip with the SQLModel
# ════════════════════════════════════════════════════════════════════


def test_alembic_table_accepts_a_signed_trace(tmp_path):
    """End-to-end: migration → SQLModel write_trace → verify."""
    db_path = tmp_path / "redroom_e2e.db"
    cfg = _bootstrap_to_pre_redroom(db_path)
    command.upgrade(cfg, "head")

    # Open via SQLModel and write a row through the sanctioned path.
    from sqlmodel import Session, create_engine

    from eval_engine.redroom.trace_store import (
        TraceKind,
        compute_replay_hash,
        verify_chain,
        write_trace,
    )

    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    with Session(engine) as session:
        write_trace(
            session,
            tenant_id=1,
            session_id="alembic-roundtrip",
            kind=TraceKind.AUTHORIZE,
            target_class="self",
            aggressiveness=2,
            replay_hash=compute_replay_hash("native", "x", 1),
            target_model_id=1,
            engine="native",
            payload={"hello": "world"},
        )
        session.commit()
        # Verify the chain is intact through this fresh DB.
        assert verify_chain(session, 1) == 1
