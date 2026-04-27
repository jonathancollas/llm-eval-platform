"""add redroom_strategy_memory table

Revision ID: 20260427_0002
Revises: 20260427_0001
Create Date: 2026-04-27

Persists the D5 coevolution strategy memory. Each row holds running
stats for one named strategy within one tenant. Selection /
record-update logic lives in
``backend/eval_engine/redroom/coevolution/persistent_memory.py``.

The pair (tenant_id, name) is unique per the table constraint.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection


revision = "20260427_0002"
down_revision = "20260427_0001"
branch_labels = None
depends_on = None


def _table_exists(conn: Connection, table_name: str) -> bool:
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    conn = op.get_bind()

    if not _table_exists(conn, "redroom_strategy_memory"):
        op.create_table(
            "redroom_strategy_memory",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("template", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "n_tried", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column(
                "sum_score", sa.Float(), nullable=False, server_default="0"
            ),
            sa.Column(
                "last_used", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("last_trace_id", sa.Integer(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.UniqueConstraint(
                "tenant_id", "name", name="uq_strategy_tenant_name"
            ),
        )

    op.create_index(
        "ix_redroom_strategy_memory_tenant_id",
        "redroom_strategy_memory",
        ["tenant_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_redroom_strategy_memory_name",
        "redroom_strategy_memory",
        ["name"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_redroom_strategy_memory_name", table_name="redroom_strategy_memory"
    )
    op.drop_index(
        "ix_redroom_strategy_memory_tenant_id",
        table_name="redroom_strategy_memory",
    )
    op.drop_table("redroom_strategy_memory")
