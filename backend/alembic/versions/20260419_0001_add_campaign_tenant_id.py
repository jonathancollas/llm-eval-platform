"""Add tenant_id and owner_id to campaigns, BenchmarkPack table

Revision ID: 20260419_0001
Revises: 20260418_0002
Create Date: 2026-04-19

Idempotent: every column / table is added only when missing so the migration
is safe against fresh databases (where ``SQLModel.metadata.create_all`` has
already created the schema) and existing ones.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection

revision = "20260419_0001"
down_revision = "20260418_0002"
branch_labels = None
depends_on = None


def _existing_columns(conn: Connection, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def _existing_tables(conn: Connection) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _add_column_if_missing(
    conn: Connection,
    table: str,
    column: str,
    col_type: sa.types.TypeEngine,
    *,
    nullable: bool = True,
    server_default: str | None = None,
) -> None:
    if column in _existing_columns(conn, table):
        return
    op.add_column(
        table,
        sa.Column(
            column,
            col_type,
            nullable=nullable,
            server_default=sa.text(server_default) if server_default else None,
        ),
    )


def upgrade() -> None:
    conn = op.get_bind()
    existing_tables = _existing_tables(conn)

    if "campaigns" in existing_tables:
        _add_column_if_missing(conn, "campaigns", "tenant_id", sa.Integer())
        _add_column_if_missing(conn, "campaigns", "owner_id", sa.Integer())

    if "benchmark_packs" not in existing_tables:
        op.create_table(
            "benchmark_packs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("slug", sa.String(), nullable=False, index=True),
            sa.Column("version", sa.String(), nullable=False, server_default="1.0.0"),
            sa.Column("publisher", sa.String(), nullable=False, server_default=""),
            sa.Column("family", sa.String(), nullable=False, server_default="", index=True),
            sa.Column("changelog", sa.String(), nullable=False, server_default=""),
            sa.Column("benchmark_ids_json", sa.String(), nullable=False, server_default="[]"),
            sa.Column("is_public", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("tenant_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    else:
        # Add columns added later to an existing benchmark_packs (e.g. SQLModel
        # created_all created the table without tenant_id).
        _add_column_if_missing(conn, "benchmark_packs", "tenant_id", sa.Integer())

    if "campaign_models" not in existing_tables:
        op.create_table(
            "campaign_models",
            sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("campaigns.id"), primary_key=True),
            sa.Column("model_id", sa.Integer(), sa.ForeignKey("llm_models.id"), primary_key=True),
        )

    if "campaign_benchmarks" not in existing_tables:
        op.create_table(
            "campaign_benchmarks",
            sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("campaigns.id"), primary_key=True),
            sa.Column("benchmark_id", sa.Integer(), sa.ForeignKey("benchmarks.id"), primary_key=True),
        )

    if "benchmark_tags" not in existing_tables:
        op.create_table(
            "benchmark_tags",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("benchmark_id", sa.Integer(), sa.ForeignKey("benchmarks.id"), nullable=False, index=True),
            sa.Column("tag", sa.String(), nullable=False, index=True),
        )

    if "eval_run_metrics" not in existing_tables:
        op.create_table(
            "eval_run_metrics",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("eval_runs.id"), nullable=False, index=True),
            sa.Column("metric_key", sa.String(), nullable=False),
            sa.Column("metric_value_json", sa.String(), nullable=False, server_default="null"),
        )


def downgrade() -> None:
    # SQLite does not support DROP COLUMN reliably for older versions.
    # Drop only the table we created so downgrade stays best-effort.
    op.drop_table("benchmark_packs")
