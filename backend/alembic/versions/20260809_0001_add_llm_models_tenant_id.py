"""Add tenant_id to llm_models for private credential isolation.

Revision ID: 20260809_0001
Revises: 20260427_0003
Create Date: 2026-08-09

Shared catalog rows (OpenRouter / Ollama sync) keep tenant_id NULL.
Tenant-created models — especially those with api_key_encrypted — stamp
tenant_id so other tenants cannot invoke or mutate the credentials.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection

revision = "20260809_0001"
down_revision = "20260427_0003"
branch_labels = None
depends_on = None


def _existing_columns(conn: Connection, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def _existing_tables(conn: Connection) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def upgrade() -> None:
    conn = op.get_bind()
    if "llm_models" not in _existing_tables(conn):
        return
    if "tenant_id" in _existing_columns(conn, "llm_models"):
        return
    op.add_column(
        "llm_models",
        sa.Column("tenant_id", sa.Integer(), nullable=True),
    )
    try:
        op.create_index("ix_llm_models_tenant_id", "llm_models", ["tenant_id"])
    except Exception:
        # Index may already exist on some dialects / re-runs.
        pass


def downgrade() -> None:
    conn = op.get_bind()
    if "llm_models" not in _existing_tables(conn):
        return
    if "tenant_id" not in _existing_columns(conn, "llm_models"):
        return
    try:
        op.drop_index("ix_llm_models_tenant_id", table_name="llm_models")
    except Exception:
        pass
    op.drop_column("llm_models", "tenant_id")
