"""Persistent representation of an AgentStack — the system under test.

Composition probes (D7) attack a system, not a single model. The
fingerprint is a stable hash of the stack's component names, so re-runs
against an "equivalent" system can be linked together for trend
analysis even when the underlying callables differ.

Schema is per-tenant; two tenants can register systems with the same
name without collision.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class RedRoomSystem(SQLModel, table=True):
    """One row per (tenant, name) describing an agentic stack.

    Fields:
        id:             primary key.
        tenant_id:      scopes the row.
        name:           human-readable identifier (caller-supplied).
        fingerprint:    sha256 hex of the canonical component-name list.
                        Stable across runs; matches AgentStack.fingerprint().
        components_json:JSON-encoded list of component names, sorted.
                        Audit-friendly representation of the stack shape.
        created_at:     row creation time.
    """

    __tablename__ = "redroom_systems"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "fingerprint", name="uq_redroom_system_tenant_fp"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(index=True)
    name: str = Field(index=True)
    fingerprint: str = Field(max_length=64, index=True)
    components_json: str = Field(default="[]")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), nullable=False
    )
