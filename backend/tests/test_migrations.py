import os
import secrets
import sqlite3
import sys

import pytest
from sqlmodel import SQLModel, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

from core import database as core_database


def test_migrate_add_columns_is_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "migration_idempotent.db"
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)

    monkeypatch.setattr(core_database.settings, "database_url", f"sqlite:///{db_path}")
    monkeypatch.setattr(core_database, "_is_sqlite", True)

    core_database._migrate_add_columns()
    core_database._migrate_add_columns()

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(campaigns)").fetchall()}
    assert "current_item_index" in columns
    assert "system_prompt_hash" in columns


def test_migrate_add_columns_adds_missing_columns(tmp_path, monkeypatch):
    """Verify _migrate_add_columns adds columns to an existing DB that was created without them."""
    db_path = tmp_path / "migration_missing.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE campaigns (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE eval_runs (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE benchmarks (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE llm_models (id INTEGER PRIMARY KEY)")
        conn.commit()

    monkeypatch.setattr(core_database.settings, "database_url", f"sqlite:///{db_path}")
    monkeypatch.setattr(core_database, "_is_sqlite", True)

    core_database._migrate_add_columns()

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(campaigns)").fetchall()}
    assert "current_item_index" in columns
    assert "system_prompt_hash" in columns
    assert "worker_task_id" in columns


def test_run_alembic_migrations_no_config(tmp_path, monkeypatch):
    """_run_alembic_migrations should skip gracefully when alembic config is absent."""
    db_path = tmp_path / "alembic_skip.db"
    monkeypatch.setattr(core_database.settings, "database_url", f"sqlite:///{db_path}")
    # Patch Path.exists to simulate missing alembic config
    original_exists = core_database.Path.exists

    def patched_exists(self):
        if self.name in ("alembic.ini", "alembic"):
            return False
        return original_exists(self)

    monkeypatch.setattr(core_database.Path, "exists", patched_exists)
    # Should not raise even with no alembic.ini
    core_database._run_alembic_migrations()


def test_migration_changes_can_be_rolled_back(tmp_path):
    db_path = tmp_path / "migration_rollback.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE campaigns (id INTEGER PRIMARY KEY, name TEXT)")
        conn.commit()

        conn.execute("BEGIN")
        conn.execute("ALTER TABLE campaigns ADD COLUMN rollback_probe TEXT")
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("ALTER TABLE missing_table ADD COLUMN will_fail TEXT")
        conn.rollback()

        columns = {row[1] for row in conn.execute("PRAGMA table_info(campaigns)").fetchall()}
        assert "rollback_probe" not in columns
