"""Tests for PersistentStrategyMemory and its alembic migration."""
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
    CoevolutionConfig,
    PersistentStrategyMemory,
    Strategy,
    run_coevolution,
)
from eval_engine.redroom.coevolution._db_models import (  # noqa: E402
    RedRoomStrategyMemoryRow,
)
from eval_engine.redroom.coevolution.engine import default_strategy_set  # noqa: E402

# ════════════════════════════════════════════════════════════════════
#  Migration
# ════════════════════════════════════════════════════════════════════


def _bootstrap_to_pre_redroom_strategy_memory(db_path: Path) -> Config:
    """Bootstrap a DB at revision 20260427_0001 (parent of the strategy
    memory migration) so we test only the new revision.
    """
    import core.models  # noqa: F401  — registers SQLModels with metadata

    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)
    engine.dispose()

    backend_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.stamp(cfg, "20260427_0001")
    return cfg


class TestMigration:
    def test_upgrade_creates_table_and_indexes(self, tmp_path):
        db_path = tmp_path / "strategy_migrate.db"
        cfg = _bootstrap_to_pre_redroom_strategy_memory(db_path)
        command.upgrade(cfg, "head")

        with sqlite3.connect(db_path) as conn:
            tables = {
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "redroom_strategy_memory" in tables

            columns = {
                r[1] for r in conn.execute(
                    "PRAGMA table_info(redroom_strategy_memory)"
                ).fetchall()
            }
            for col in (
                "id", "tenant_id", "name", "template", "n_tried",
                "sum_score", "last_used", "notes", "last_trace_id",
                "created_at", "updated_at",
            ):
                assert col in columns, f"missing column {col!r}"

            indexes = {
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='index' AND tbl_name='redroom_strategy_memory'"
                ).fetchall()
            }
            assert "ix_redroom_strategy_memory_tenant_id" in indexes
            assert "ix_redroom_strategy_memory_name" in indexes

    def test_upgrade_is_idempotent(self, tmp_path):
        db_path = tmp_path / "strategy_idempotent.db"
        cfg = _bootstrap_to_pre_redroom_strategy_memory(db_path)
        command.upgrade(cfg, "head")
        command.upgrade(cfg, "head")  # no-op

    def test_unique_constraint_on_tenant_name(self, tmp_path):
        db_path = tmp_path / "strategy_unique.db"
        cfg = _bootstrap_to_pre_redroom_strategy_memory(db_path)
        command.upgrade(cfg, "head")

        # Insert via the SQLModel so all NOT NULL defaults are applied.
        from sqlalchemy.exc import IntegrityError as SAIntegrityError
        engine = create_engine(f"sqlite:///{db_path}")
        with Session(engine) as session:
            session.add(
                RedRoomStrategyMemoryRow(tenant_id=1, name="role_play")
            )
            session.commit()

            session.add(
                RedRoomStrategyMemoryRow(tenant_id=1, name="role_play")
            )
            with pytest.raises(SAIntegrityError):
                session.commit()

    def test_downgrade_drops_table(self, tmp_path):
        db_path = tmp_path / "strategy_downgrade.db"
        cfg = _bootstrap_to_pre_redroom_strategy_memory(db_path)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "20260427_0001")

        with sqlite3.connect(db_path) as conn:
            tables = {
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "redroom_strategy_memory" not in tables
            assert "redroom_traces" in tables  # earlier table preserved


# ════════════════════════════════════════════════════════════════════
#  Persistent class — fixtures
# ════════════════════════════════════════════════════════════════════


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


# ════════════════════════════════════════════════════════════════════
#  Construction / seeding
# ════════════════════════════════════════════════════════════════════


class TestSeeding:
    def test_seed_inserts_strategies(self, session):
        m = PersistentStrategyMemory(session, tenant_id=1)
        m.seed(list(default_strategy_set()))
        names = m.names()
        assert len(names) == len(default_strategy_set())

    def test_seed_is_idempotent(self, session):
        m = PersistentStrategyMemory(session, tenant_id=1)
        m.seed(list(default_strategy_set()))
        # Re-seed: existing rows preserved, no duplicate.
        m.seed(list(default_strategy_set()))
        assert len(m) == len(default_strategy_set())

    def test_invalid_tenant_id_rejected(self, session):
        with pytest.raises(ValueError):
            PersistentStrategyMemory(session, tenant_id=0)

    def test_add_duplicate_raises(self, session):
        m = PersistentStrategyMemory(session, tenant_id=1)
        m.add(Strategy(name="x", template="t"))
        with pytest.raises(ValueError, match="already in memory"):
            m.add(Strategy(name="x", template="t2"))


# ════════════════════════════════════════════════════════════════════
#  Tenant isolation
# ════════════════════════════════════════════════════════════════════


class TestTenantIsolation:
    def test_two_tenants_have_independent_memories(self, session):
        m1 = PersistentStrategyMemory(session, tenant_id=1)
        m2 = PersistentStrategyMemory(session, tenant_id=2)
        m1.add(Strategy(name="role_play", template="t1"))
        m2.add(Strategy(name="hypothetical", template="t2"))

        assert "role_play" in m1
        assert "role_play" not in m2
        assert "hypothetical" in m2
        assert "hypothetical" not in m1

    def test_record_for_one_tenant_does_not_leak(self, session):
        m1 = PersistentStrategyMemory(session, tenant_id=1)
        m2 = PersistentStrategyMemory(session, tenant_id=2)
        m1.add(Strategy(name="x", template="t"))
        m2.add(Strategy(name="x", template="t"))

        m1.record("x", 1.0)

        assert m1.get("x").n_tried == 1
        assert m2.get("x").n_tried == 0


# ════════════════════════════════════════════════════════════════════
#  Selection
# ════════════════════════════════════════════════════════════════════


class TestSelection:
    def test_empty_memory_select_raises(self, session):
        m = PersistentStrategyMemory(session, tenant_id=1)
        with pytest.raises(LookupError):
            m.select()

    def test_greedy_picks_highest_posterior(self, session):
        import random as rnd
        m = PersistentStrategyMemory(session, tenant_id=1)
        m.add(Strategy(name="a", template="t"))
        m.add(Strategy(name="b", template="t"))
        m.record("a", 1.0)
        m.record("a", 1.0)
        m.record("b", 0.0)

        rng = rnd.Random(42)
        seen = {m.select(epsilon=0.0, rng=rng).name for _ in range(20)}
        assert seen == {"a"}

    def test_record_unknown_raises(self, session):
        m = PersistentStrategyMemory(session, tenant_id=1)
        with pytest.raises(KeyError):
            m.record("ghost", 0.5)

    def test_record_updates_last_used_monotonically(self, session):
        m = PersistentStrategyMemory(session, tenant_id=1)
        m.add(Strategy(name="a", template="t"))
        m.add(Strategy(name="b", template="t"))
        m.record("a", 0.5)
        m.record("b", 0.5)
        m.record("a", 0.5)
        assert m.get("a").last_used > m.get("b").last_used


# ════════════════════════════════════════════════════════════════════
#  Top-N
# ════════════════════════════════════════════════════════════════════


class TestTopN:
    def test_top_n_zero_returns_empty(self, session):
        m = PersistentStrategyMemory(session, tenant_id=1)
        assert m.top_n(0) == ()

    def test_top_n_orders_by_posterior(self, session):
        m = PersistentStrategyMemory(session, tenant_id=1)
        for n in ("a", "b", "c"):
            m.add(Strategy(name=n, template="t"))
        m.record("c", 1.0)
        m.record("a", 0.5)
        m.record("b", 0.0)
        top = m.top_n(2)
        assert [s.name for s in top] == ["c", "a"]


# ════════════════════════════════════════════════════════════════════
#  Trace linkage
# ════════════════════════════════════════════════════════════════════


class TestTraceLinkage:
    def test_record_with_trace_id_persists(self, session):
        m = PersistentStrategyMemory(session, tenant_id=1)
        m.add(Strategy(name="a", template="t"))
        m.record("a", 0.5, last_trace_id=42)

        from sqlmodel import select
        row = session.exec(
            select(RedRoomStrategyMemoryRow).where(
                RedRoomStrategyMemoryRow.name == "a"
            )
        ).first()
        assert row is not None
        assert row.last_trace_id == 42


# ════════════════════════════════════════════════════════════════════
#  End-to-end: persistent memory drives run_coevolution
# ════════════════════════════════════════════════════════════════════


class TestEngineWithPersistentMemory:
    def test_engine_records_into_persistent_store(self, session):
        import asyncio

        async def target(_p):
            return "ok"

        async def attacker(_x):
            return "p"

        async def perfect(_p, _r):
            return 1.0

        m = PersistentStrategyMemory(session, tenant_id=42)
        m.seed(list(default_strategy_set()))

        out = asyncio.run(
            run_coevolution(
                target=target,
                attacker=attacker,
                judge=perfect,
                memory=m,
                config=CoevolutionConfig(
                    objective="x", max_rounds=2, success_threshold=0.5
                ),
            )
        )
        assert out.success is True
        used = out.rounds[0].strategy_name
        assert m.get(used).n_tried >= 1


# ════════════════════════════════════════════════════════════════════
#  P0-4 — record() must be atomic under concurrency
# ════════════════════════════════════════════════════════════════════


import threading                                   # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402


class TestConcurrentRecord:
    """``record()`` must not lose updates when two coevolution runs hit
    the same tenant simultaneously.

    Historical bug (audit P0-4): the implementation read ``n_tried`` into
    Python, incremented, and wrote back. Two workers seeing the same
    pre-value both wrote the same post-value, losing one round's
    contribution. The fix issues a SQL ``UPDATE ... SET n_tried = n_tried + 1``
    that the database evaluates atomically per row.
    """

    @pytest.fixture
    def shared_db_url(self, tmp_path):
        import core.models  # noqa: F401 — registers metadata

        db_file = tmp_path / "memory_concurrent.db"
        boot = create_engine(f"sqlite:///{db_file}")
        SQLModel.metadata.create_all(boot)
        boot.dispose()
        return f"sqlite:///{db_file}"

    def test_concurrent_records_same_strategy_no_lost_updates(self, shared_db_url):
        """50 threads each call record() once — final n_tried must be 50."""
        # Seed once.
        seed_eng = create_engine(shared_db_url)
        try:
            with Session(seed_eng) as s:
                PersistentStrategyMemory(s, tenant_id=7).seed(
                    [Strategy(name="x", template="t")]
                )
        finally:
            seed_eng.dispose()

        n_writers = 50
        barrier = threading.Barrier(n_writers)

        def _writer(i: int) -> None:
            barrier.wait()
            engine = create_engine(shared_db_url)
            try:
                with Session(engine) as s:
                    PersistentStrategyMemory(s, tenant_id=7).record(
                        "x", 0.5, last_trace_id=i
                    )
            finally:
                engine.dispose()

        with ThreadPoolExecutor(max_workers=n_writers) as ex:
            futures = [ex.submit(_writer, i) for i in range(n_writers)]
            for f in futures:
                f.result(timeout=30)

        # Verify the row holds exactly the expected aggregate.
        verify_eng = create_engine(shared_db_url)
        try:
            with Session(verify_eng) as s:
                row = PersistentStrategyMemory(s, tenant_id=7).get("x")
                assert row.n_tried == n_writers, (
                    f"lost updates detected: n_tried={row.n_tried} "
                    f"(expected {n_writers})"
                )
                # sum_score = n_writers * 0.5 — each record contributes 0.5.
                assert abs(row.sum_score - (n_writers * 0.5)) < 1e-6, (
                    f"sum_score drifted: {row.sum_score}"
                )
        finally:
            verify_eng.dispose()

    def test_concurrent_records_different_tenants_independent(self, shared_db_url):
        """Two tenants recording in parallel must not contaminate each other."""
        for tenant_id in (10, 20):
            seed_eng = create_engine(shared_db_url)
            try:
                with Session(seed_eng) as s:
                    PersistentStrategyMemory(s, tenant_id=tenant_id).seed(
                        [Strategy(name="strat", template="t")]
                    )
            finally:
                seed_eng.dispose()

        n_per = 20
        barrier = threading.Barrier(n_per * 2)

        def _writer(tenant_id: int, i: int) -> None:
            barrier.wait()
            engine = create_engine(shared_db_url)
            try:
                with Session(engine) as s:
                    PersistentStrategyMemory(s, tenant_id=tenant_id).record(
                        "strat", 1.0, last_trace_id=i
                    )
            finally:
                engine.dispose()

        with ThreadPoolExecutor(max_workers=n_per * 2) as ex:
            futures = []
            for i in range(n_per):
                futures.append(ex.submit(_writer, 10, i))
                futures.append(ex.submit(_writer, 20, i))
            for f in futures:
                f.result(timeout=30)

        verify_eng = create_engine(shared_db_url)
        try:
            with Session(verify_eng) as s:
                a = PersistentStrategyMemory(s, tenant_id=10).get("strat")
                b = PersistentStrategyMemory(s, tenant_id=20).get("strat")
                assert a.n_tried == n_per
                assert b.n_tried == n_per
        finally:
            verify_eng.dispose()
