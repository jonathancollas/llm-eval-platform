"""add eval_results.human_verdict for persisted human review labels

Revision ID: 20260824_0001
Revises: 20260427_0003
Create Date: 2026-08-24

The dashboard failed-items panel and PATCH /results/{id}/human-review
read and write EvalResult.human_verdict, but the column was never added
to the table. Existing databases therefore crash GET failed-items
(AttributeError) and silently drop human-review writes.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection


revision = "20260824_0001"
down_revision = "20260427_0003"
branch_labels = None
depends_on = None


def _column_exists(conn: Connection, table: str, column: str) -> bool:
    insp = sa.inspect(conn)
    if table not in insp.get_table_names():
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    conn = op.get_bind()
    if _column_exists(conn, "eval_results", "human_verdict"):
        return
    op.add_column(
        "eval_results",
        sa.Column("human_verdict", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, "eval_results", "human_verdict"):
        return
    op.drop_column("eval_results", "human_verdict")
