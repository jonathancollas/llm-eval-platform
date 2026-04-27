"""Persistent backing for the coevolution strategy memory.

Lives in its own module so importing the in-memory ``StrategyMemory``
does not pull in SQLModel / DB dependencies for callers who only need
the algorithmic class.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class RedRoomStrategyMemoryRow(SQLModel, table=True):
    """One row per (tenant, strategy name) pair."""

    __tablename__ = "redroom_strategy_memory"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_strategy_tenant_name"),
    )

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(index=True)
    name: str = Field(index=True)
    template: str = Field(default="")
    n_tried: int = Field(default=0)
    sum_score: float = Field(default=0.0)
    last_used: int = Field(default=0)
    notes: str = Field(default="")
    # Optional pointer to the most recent trace that updated this row.
    # Soft FK — the trace store is append-only and we don't enforce
    # RDBMS-level FK to keep schema migrations independent.
    last_trace_id: int | None = Field(default=None, nullable=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), nullable=False
    )
