"""
Helpers for upserting an :class:`AgentStack` into the persistent
``redroom_systems`` table.

The lookup key is ``(tenant_id, fingerprint)``. Two stacks with the
same component names produce the same fingerprint and resolve to the
same row, even if the underlying callables differ — which is exactly
what we want so trend reporting can group runs against an
"equivalent" system over time.
"""
from __future__ import annotations

import json

from sqlmodel import Session, select

from eval_engine.redroom.composition._db_models import RedRoomSystem
from eval_engine.redroom.composition.harness import AgentStack


def register_system(
    session: Session,
    *,
    tenant_id: int,
    name: str,
    stack: AgentStack,
) -> RedRoomSystem:
    """Find or create a ``RedRoomSystem`` row for ``stack``.

    Behavior:
      - If a row with the same (tenant_id, fingerprint) already exists,
        return it untouched (the existing ``name`` wins; we don't
        overwrite even if the caller passes a different name).
      - Otherwise insert a new row.

    Returns the row in either case. Caller decides whether to commit.
    """
    if tenant_id <= 0:
        raise ValueError("tenant_id must be a positive integer")
    if not name or not isinstance(name, str):
        raise ValueError("name must be a non-empty string")

    fp = stack.fingerprint()
    existing = session.exec(
        select(RedRoomSystem).where(
            RedRoomSystem.tenant_id == tenant_id,
            RedRoomSystem.fingerprint == fp,
        )
    ).first()
    if existing is not None:
        return existing

    row = RedRoomSystem(
        tenant_id=tenant_id,
        name=name,
        fingerprint=fp,
        components_json=json.dumps(stack.component_names(), sort_keys=False),
    )
    session.add(row)
    session.flush()
    return row


def lookup_system_by_id(
    session: Session, *, system_id: int, tenant_id: int | None = None
) -> RedRoomSystem | None:
    """Read-back helper. When ``tenant_id`` is provided, refuses to
    return a row that belongs to a different tenant — defense in depth
    against accidental cross-tenant audit reads."""
    row = session.get(RedRoomSystem, system_id)
    if row is None:
        return None
    if tenant_id is not None and row.tenant_id != tenant_id:
        return None
    return row
