"""Tests for RedRoomSystem, AgentStack.fingerprint(), and register_system."""
from __future__ import annotations

import os
import secrets
import sqlite3
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlmodel import Session, SQLModel, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))
os.environ.setdefault("REDROOM_TRACE_SECRET", "x" * 32 + "_test_secret")

from eval_engine.redroom import (  # noqa: E402
    AgentStack,
    lookup_system_by_id,
    register_system,
)


def _bootstrap_to_pre_e2(db_path: Path) -> Config:
    """Bootstrap a DB at revision 20260427_0002 (parent of redroom_systems)."""
    import core.models  # noqa: F401

    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)
    engine.dispose()

    backend_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.stamp(cfg, "20260427_0002")
    return cfg


# ════════════════════════════════════════════════════════════════════
#  Migration
# ════════════════════════════════════════════════════════════════════


class TestMigration:
    def test_upgrade_creates_system_table(self, tmp_path):
        db_path = tmp_path / "system_migrate.db"
        cfg = _bootstrap_to_pre_e2(db_path)
        command.upgrade(cfg, "head")

        with sqlite3.connect(db_path) as conn:
            tables = {
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "redroom_systems" in tables

    def test_upgrade_adds_system_id_column_to_traces(self, tmp_path):
        db_path = tmp_path / "system_alters_trace.db"
        cfg = _bootstrap_to_pre_e2(db_path)
        command.upgrade(cfg, "head")

        with sqlite3.connect(db_path) as conn:
            columns = {
                r[1] for r in conn.execute(
                    "PRAGMA table_info(redroom_traces)"
                ).fetchall()
            }
            assert "system_id" in columns

    def test_upgrade_is_idempotent(self, tmp_path):
        db_path = tmp_path / "system_idem.db"
        cfg = _bootstrap_to_pre_e2(db_path)
        command.upgrade(cfg, "head")
        command.upgrade(cfg, "head")  # no-op

    def test_downgrade_drops_table_and_column(self, tmp_path):
        db_path = tmp_path / "system_down.db"
        cfg = _bootstrap_to_pre_e2(db_path)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "20260427_0002")

        with sqlite3.connect(db_path) as conn:
            tables = {
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "redroom_systems" not in tables
            columns = {
                r[1] for r in conn.execute(
                    "PRAGMA table_info(redroom_traces)"
                ).fetchall()
            }
            assert "system_id" not in columns


# ════════════════════════════════════════════════════════════════════
#  AgentStack.fingerprint
# ════════════════════════════════════════════════════════════════════


def _make_stack(*names: str) -> AgentStack:
    async def _f(_p):
        return ""
    return AgentStack(components={n: _f for n in names})


class TestFingerprint:
    def test_same_components_same_fingerprint(self):
        s1 = _make_stack("model", "tool", "memory")
        s2 = _make_stack("model", "tool", "memory")
        assert s1.fingerprint() == s2.fingerprint()

    def test_different_components_different_fingerprint(self):
        s1 = _make_stack("model", "tool")
        s2 = _make_stack("model", "rag")
        assert s1.fingerprint() != s2.fingerprint()

    def test_order_does_not_matter(self):
        s1 = _make_stack("a", "b", "c")
        s2 = _make_stack("c", "b", "a")
        assert s1.fingerprint() == s2.fingerprint()

    def test_fingerprint_length_is_64(self):
        assert len(_make_stack("a").fingerprint()) == 64

    def test_component_names_are_sorted(self):
        s = _make_stack("z", "a", "m")
        assert s.component_names() == ["a", "m", "z"]


# ════════════════════════════════════════════════════════════════════
#  register_system
# ════════════════════════════════════════════════════════════════════


@pytest.fixture
def session():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        yield s


class TestRegisterSystem:
    def test_first_call_creates_a_row(self, session):
        s = _make_stack("model", "tool")
        row = register_system(
            session, tenant_id=1, name="my_agent", stack=s
        )
        session.commit()
        assert row.id is not None
        assert row.tenant_id == 1
        assert row.fingerprint == s.fingerprint()

    def test_second_call_returns_same_row(self, session):
        s = _make_stack("model", "tool")
        a = register_system(
            session, tenant_id=1, name="my_agent", stack=s
        )
        session.commit()
        b = register_system(
            session, tenant_id=1, name="renamed", stack=s
        )
        session.commit()
        assert a.id == b.id
        # First-write wins: rename was ignored.
        assert b.name == "my_agent"

    def test_tenant_isolation(self, session):
        s = _make_stack("model")
        a = register_system(
            session, tenant_id=1, name="x", stack=s
        )
        b = register_system(
            session, tenant_id=2, name="x", stack=s
        )
        session.commit()
        # Same fingerprint but different tenants → different rows.
        assert a.id != b.id
        assert a.fingerprint == b.fingerprint

    def test_lookup_by_id_respects_tenant(self, session):
        s = _make_stack("a")
        row = register_system(session, tenant_id=1, name="x", stack=s)
        session.commit()

        # Same tenant: returns row.
        assert lookup_system_by_id(
            session, system_id=row.id, tenant_id=1
        ) is not None
        # Wrong tenant: refuses.
        assert lookup_system_by_id(
            session, system_id=row.id, tenant_id=2
        ) is None
        # No tenant scope: still returns.
        assert lookup_system_by_id(
            session, system_id=row.id
        ) is not None

    def test_invalid_tenant_id_rejected(self, session):
        s = _make_stack("a")
        with pytest.raises(ValueError):
            register_system(session, tenant_id=0, name="x", stack=s)

    def test_empty_name_rejected(self, session):
        s = _make_stack("a")
        with pytest.raises(ValueError):
            register_system(session, tenant_id=1, name="", stack=s)


# ════════════════════════════════════════════════════════════════════
#  trace_store: write_trace accepts system_id
# ════════════════════════════════════════════════════════════════════


class TestTraceWithSystemId:
    def test_system_id_persists_through_write_trace(self, session):
        from eval_engine.redroom.trace_store import (
            TraceKind,
            compute_replay_hash,
            verify_chain,
            write_trace,
        )

        # Create a system row first.
        s = _make_stack("a", "b")
        row = register_system(session, tenant_id=1, name="x", stack=s)
        session.commit()

        write_trace(
            session,
            tenant_id=1,
            session_id="sess-with-system",
            kind=TraceKind.AUTHORIZE,
            target_class="self",
            aggressiveness=2,
            replay_hash=compute_replay_hash("native", "x", 1),
            target_model_id=1,
            engine="native",
            payload={"hello": "world"},
            system_id=row.id,
        )
        session.commit()

        # Chain integrity not affected by the new field.
        assert verify_chain(session, 1) == 1

        # The trace persists the link.
        from sqlmodel import select

        from eval_engine.redroom.trace_store import RedRoomTrace
        traces = list(session.exec(select(RedRoomTrace)))
        assert len(traces) == 1
        assert traces[0].system_id == row.id
