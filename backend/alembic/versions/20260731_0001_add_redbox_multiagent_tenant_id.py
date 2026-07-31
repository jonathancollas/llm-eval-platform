"""Add tenant_id to redbox/multiagent tables for multi-tenant isolation.

Revision ID: 20260731_0001
Revises: 20260427_0003
Create Date: 2026-07-31

Idempotent: columns are added only when missing so the migration is safe
against fresh databases (where SQLModel.metadata.create_all already
created the schema) and existing ones.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection

revision = "20260731_0001"
down_revision = "20260427_0003"
branch_labels = None
depends_on = None


_TABLES = (
    "redbox_exploits",
    "multi_agent_simulations",
    "sandbagging_reports",
)


def _existing_columns(conn: Connection, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def _existing_tables(conn: Connection) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def upgrade() -> None:
    conn = op.get_bind()
    tables = _existing_tables(conn)
    for table in _TABLES:
        if table not in tables:
            continue
        if "tenant_id" in _existing_columns(conn, table):
            continue
        op.add_column(
            table,
            sa.Column("tenant_id", sa.Integer(), nullable=True),
        )
        index_name = f"ix_{table}_tenant_id"
        try:
            op.create_index(index_name, table, ["tenant_id"])
        except Exception:
            # Index may already exist on some dialects / recreate paths.
            pass


def downgrade() -> None:
    conn = op.get_bind()
    tables = _existing_tables(conn)
    for table in _TABLES:
        if table not in tables:
            continue
        if "tenant_id" not in _existing_columns(conn, table):
            continue
        index_name = f"ix_{table}_tenant_id"
        try:
            op.drop_index(index_name, table_name=table)
        except Exception:
            pass
        op.drop_column(table, "tenant_id")
