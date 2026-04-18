"""add task_registry table

Revision ID: 20260418_0001
Revises: 20260413_0001
Create Date: 2026-04-18

Creates the task_registry table for the canonical benchmark task registry
introduced in M2-P1.  Each row represents one evaluation task with a
canonical ID (namespace:benchmark:task_id) and rich metadata.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection


revision = "20260418_0001"
down_revision = "20260413_0001"
branch_labels = None
depends_on = None


def _table_exists(conn: Connection, table_name: str) -> bool:
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    conn = op.get_bind()

    if not _table_exists(conn, "task_registry"):
        op.create_table(
            "task_registry",
            sa.Column("canonical_id", sa.Text(), primary_key=True, nullable=False),
            sa.Column("name", sa.Text(), nullable=False, server_default=""),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("domain", sa.Text(), nullable=False, server_default=""),
            sa.Column("capability_tags", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("difficulty", sa.Text(), nullable=False, server_default="medium"),
            sa.Column("benchmark_name", sa.Text(), nullable=False, server_default=""),
            sa.Column("namespace", sa.Text(), nullable=False, server_default="public"),
            sa.Column("source_url", sa.Text(), nullable=False, server_default=""),
            sa.Column("paper_url", sa.Text(), nullable=False, server_default=""),
            sa.Column("year", sa.Integer(), nullable=True),
            sa.Column("license", sa.Text(), nullable=False, server_default="unknown"),
            sa.Column("provenance", sa.Text(), nullable=False, server_default=""),
            sa.Column("contamination_risk", sa.Text(), nullable=False, server_default="low"),
            sa.Column("known_contamination_notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("required_environment", sa.Text(), nullable=False, server_default="none"),
            sa.Column("dependencies", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    op.create_index("idx_task_registry_domain",      "task_registry", ["domain"],      unique=False, if_not_exists=True)
    op.create_index("idx_task_registry_difficulty",  "task_registry", ["difficulty"],  unique=False, if_not_exists=True)
    op.create_index("idx_task_registry_namespace",   "task_registry", ["namespace"],   unique=False, if_not_exists=True)
    op.create_index("idx_task_registry_benchmark",   "task_registry", ["benchmark_name"], unique=False, if_not_exists=True)
    op.create_index("idx_task_registry_contamination", "task_registry", ["contamination_risk"], unique=False, if_not_exists=True)
    op.create_index("idx_task_registry_name",        "task_registry", ["name"],        unique=False, if_not_exists=True)


def downgrade() -> None:
    op.drop_table("task_registry")
