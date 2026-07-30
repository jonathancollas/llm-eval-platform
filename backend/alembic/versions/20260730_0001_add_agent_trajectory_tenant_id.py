"""Add tenant_id to agent_trajectories for multi-tenant isolation.

Revision ID: 20260730_0001
Revises: 20260427_0003
Create Date: 2026-07-30

Idempotent: column is added only when missing so the migration is safe
against fresh databases (where SQLModel.metadata.create_all already
created the schema) and existing ones.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection

revision = "20260730_0001"
down_revision = "20260427_0003"
branch_labels = None
depends_on = None


def _existing_columns(conn: Connection, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def _existing_tables(conn: Connection) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def upgrade() -> None:
    conn = op.get_bind()
    if "agent_trajectories" not in _existing_tables(conn):
        return
    if "tenant_id" in _existing_columns(conn, "agent_trajectories"):
        return
    op.add_column(
        "agent_trajectories",
        sa.Column("tenant_id", sa.Integer(), nullable=True),
    )
    try:
        op.create_index(
            "ix_agent_trajectories_tenant_id",
            "agent_trajectories",
            ["tenant_id"],
        )
    except Exception:
        # Index may already exist on some dialects / recreate paths.
        pass


def downgrade() -> None:
    conn = op.get_bind()
    if "agent_trajectories" not in _existing_tables(conn):
        return
    if "tenant_id" not in _existing_columns(conn, "agent_trajectories"):
        return
    try:
        op.drop_index("ix_agent_trajectories_tenant_id", table_name="agent_trajectories")
    except Exception:
        pass
    op.drop_column("agent_trajectories", "tenant_id")
