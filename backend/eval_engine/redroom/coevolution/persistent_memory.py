"""
PersistentStrategyMemory — DB-backed implementation of StrategyMemory.

The in-memory ``StrategyMemory`` is fine for single-process tests but
loses everything across restarts and can't be shared between workers.
This class is API-compatible (same ``select`` / ``record`` / ``top_n``)
but reads from / writes to ``redroom_strategy_memory`` per tenant.

Concurrency: each method takes one open ``Session`` and commits at the
end. SQLAlchemy session-level isolation is enough because:
  - ``record()`` does a SELECT-then-UPDATE on a single row, idempotent
    if retried.
  - ``select()`` is a pure read; concurrent selects can return different
    rows but that's by design (ε-greedy).
  - The ``(tenant_id, name)`` UNIQUE constraint prevents racy ``seed()``
    inserts.

For workers that need stronger guarantees (e.g. exactly-once update),
wrap calls in their own DB transaction.
"""
from __future__ import annotations

import random
from datetime import UTC, datetime

from sqlmodel import Session, select

from eval_engine.redroom.coevolution._db_models import RedRoomStrategyMemoryRow
from eval_engine.redroom.coevolution.strategy_memory import Strategy


class PersistentStrategyMemory:
    """DB-backed memory scoped to one tenant.

    Construct once per tenant per session; pass it to ``run_coevolution``
    in place of ``StrategyMemory``. The two classes share the same
    public surface, so the engine doesn't care which it gets.
    """

    def __init__(self, session: Session, tenant_id: int):
        if tenant_id <= 0:
            raise ValueError("tenant_id must be a positive integer")
        self._session = session
        self._tenant_id = tenant_id

    # ── Construction / seeding ──────────────────────────────────────

    def seed(self, strategies: list[Strategy]) -> None:
        """Insert each strategy if (tenant_id, name) not already present.

        Existing rows are preserved untouched — so re-seeding never
        wipes accumulated stats.
        """
        for s in strategies:
            existing = self._row_by_name(s.name)
            if existing is None:
                row = RedRoomStrategyMemoryRow(
                    tenant_id=self._tenant_id,
                    name=s.name,
                    template=s.template,
                    n_tried=s.n_tried,
                    sum_score=s.sum_score,
                    last_used=s.last_used,
                    notes=s.notes,
                )
                self._session.add(row)
        self._session.commit()

    def add(self, strategy: Strategy) -> None:
        """Add one strategy. Raises if already present (mirrors in-memory)."""
        if not strategy.name or not isinstance(strategy.name, str):
            raise ValueError("strategy.name must be a non-empty string")
        if self._row_by_name(strategy.name) is not None:
            raise ValueError(f"strategy {strategy.name!r} already in memory")
        row = RedRoomStrategyMemoryRow(
            tenant_id=self._tenant_id,
            name=strategy.name,
            template=strategy.template,
            n_tried=strategy.n_tried,
            sum_score=strategy.sum_score,
            last_used=strategy.last_used,
            notes=strategy.notes,
        )
        self._session.add(row)
        self._session.commit()

    # ── Read API ────────────────────────────────────────────────────

    def names(self) -> tuple[str, ...]:
        rows = self._all_rows()
        return tuple(sorted(r.name for r in rows))

    def get(self, name: str) -> Strategy:
        row = self._row_by_name(name)
        if row is None:
            raise KeyError(name)
        return _to_strategy(row)

    def __contains__(self, name: str) -> bool:
        return self._row_by_name(name) is not None

    def __len__(self) -> int:
        return len(self._all_rows())

    # ── Selection ───────────────────────────────────────────────────

    def select(
        self,
        *,
        epsilon: float = 0.1,
        recency_bias: float = 0.0,
        rng=None,
    ) -> Strategy:
        rows = self._all_rows()
        if not rows:
            raise LookupError("PersistentStrategyMemory is empty")
        if epsilon < 0.0 or epsilon > 1.0:
            raise ValueError("epsilon must be in [0,1]")

        rng = rng or random.Random()

        if rng.random() < epsilon:
            sorted_rows = sorted(rows, key=lambda r: r.name)
            return _to_strategy(rng.choice(sorted_rows))

        clock = max((r.last_used for r in rows), default=1)
        denom = max(1, clock)
        ranked = sorted(
            rows,
            key=lambda r: (
                -(_posterior(r) + recency_bias * (r.last_used / denom)),
                r.name,
            ),
        )
        return _to_strategy(ranked[0])

    # ── Record / mutate ─────────────────────────────────────────────

    def record(
        self, name: str, score: float, *, last_trace_id: int | None = None
    ) -> None:
        """Atomically merge one round's outcome into the named strategy.

        Increments the per-tenant clock so the new ``last_used`` is
        strictly greater than any prior row's.
        """
        s = max(0.0, min(1.0, float(score)))
        row = self._row_by_name(name)
        if row is None:
            raise KeyError(name)
        new_clock = self._next_clock()
        row.n_tried = row.n_tried + 1
        row.sum_score = row.sum_score + s
        row.last_used = new_clock
        row.updated_at = datetime.now(UTC)
        if last_trace_id is not None:
            row.last_trace_id = int(last_trace_id)
        self._session.add(row)
        self._session.commit()

    # ── Inspection ──────────────────────────────────────────────────

    def top_n(self, n: int = 3) -> tuple[Strategy, ...]:
        if n <= 0:
            return ()
        rows = self._all_rows()
        ranked = sorted(rows, key=lambda r: (-_posterior(r), r.name))
        return tuple(_to_strategy(r) for r in ranked[:n])

    # ── Internals ───────────────────────────────────────────────────

    def _all_rows(self) -> list[RedRoomStrategyMemoryRow]:
        return list(
            self._session.exec(
                select(RedRoomStrategyMemoryRow).where(
                    RedRoomStrategyMemoryRow.tenant_id == self._tenant_id
                )
            )
        )

    def _row_by_name(self, name: str) -> RedRoomStrategyMemoryRow | None:
        return self._session.exec(
            select(RedRoomStrategyMemoryRow)
            .where(
                RedRoomStrategyMemoryRow.tenant_id == self._tenant_id,
                RedRoomStrategyMemoryRow.name == name,
            )
            .limit(1)
        ).first()

    def _next_clock(self) -> int:
        rows = self._all_rows()
        return (max((r.last_used for r in rows), default=0) or 0) + 1


# ────────────────────────────────────────────────────────────────────
#  Helpers
# ────────────────────────────────────────────────────────────────────


def _to_strategy(row: RedRoomStrategyMemoryRow) -> Strategy:
    return Strategy(
        name=row.name,
        template=row.template,
        n_tried=row.n_tried,
        sum_score=row.sum_score,
        last_used=row.last_used,
        notes=row.notes,
    )


def _posterior(row: RedRoomStrategyMemoryRow) -> float:
    """Same Beta(1,1)-prior posterior as the in-memory class."""
    return (row.sum_score + 1.0) / (row.n_tried + 2.0)
