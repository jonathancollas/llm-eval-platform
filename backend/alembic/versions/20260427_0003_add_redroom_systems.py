"""add redroom_systems table + system_id column on redroom_traces

Revision ID: 20260427_0003
Revises: 20260427_0002
Create Date: 2026-04-27

Persists D7's AgentStack composition. Each stack registers under a
fingerprint computed from its component names; subsequent runs against
the same stack hit the same fingerprint and link to the same row.

Also extends ``redroom_traces`` with an optional ``system_id`` column
so attack traces can be grouped by stack. The new column is NULLABLE
and intentionally NOT in the trace's signed payload — adding it to
the canonical signature would invalidate existing chains. A future
migration can elevate it once all deployed databases are caught up.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection


revision = "20260427_0003"
down_revision = "20260427_0002"
branch_labels = None
depends_on = None


def _table_exists(conn: Connection, table_name: str) -> bool:
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def _column_exists(conn: Connection, table: str, column: str) -> bool:
    insp = sa.inspect(conn)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Create redroom_systems if not present.
    if not _table_exists(conn, "redroom_systems"):
        op.create_table(
            "redroom_systems",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("fingerprint", sa.String(length=64), nullable=False),
            sa.Column(
                "components_json",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.UniqueConstraint(
                "tenant_id", "fingerprint", name="uq_redroom_system_tenant_fp"
            ),
        )

    op.create_index(
        "ix_redroom_systems_tenant_id",
        "redroom_systems",
        ["tenant_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_redroom_systems_fingerprint",
        "redroom_systems",
        ["fingerprint"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_redroom_systems_name",
        "redroom_systems",
        ["name"],
        unique=False,
        if_not_exists=True,
    )

    # 2. Add system_id to redroom_traces if not present.
    if _table_exists(conn, "redroom_traces") and not _column_exists(
        conn, "redroom_traces", "system_id"
    ):
        op.add_column(
            "redroom_traces",
            sa.Column("system_id", sa.Integer(), nullable=True),
        )
        op.create_index(
            "ix_redroom_traces_system_id",
            "redroom_traces",
            ["system_id"],
            unique=False,
            if_not_exists=True,
        )


def downgrade() -> None:
    conn = op.get_bind()

    if _table_exists(conn, "redroom_traces") and _column_exists(
        conn, "redroom_traces", "system_id"
    ):
        op.drop_index(
            "ix_redroom_traces_system_id", table_name="redroom_traces"
        )
        # SQLite supports drop_column via batch_alter_table since alembic 1.7.
        with op.batch_alter_table("redroom_traces") as batch:
            batch.drop_column("system_id")

    op.drop_index("ix_redroom_systems_name", table_name="redroom_systems")
    op.drop_index(
        "ix_redroom_systems_fingerprint", table_name="redroom_systems"
    )
    op.drop_index(
        "ix_redroom_systems_tenant_id", table_name="redroom_systems"
    )
    op.drop_table("redroom_systems")
