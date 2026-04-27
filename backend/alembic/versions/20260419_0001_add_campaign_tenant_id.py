"""Add tenant_id and owner_id to campaigns, BenchmarkPack table

Revision ID: 20260419_0001
Revises: 20260418_0002
Create Date: 2026-04-19
"""
from alembic import op
import sqlalchemy as sa

revision = "20260419_0001"
down_revision = "20260418_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add tenant_id and owner_id to campaigns
    with op.batch_alter_table("campaigns") as batch_op:
        batch_op.add_column(sa.Column("tenant_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("owner_id", sa.Integer(), nullable=True))

    # Create benchmark_packs table
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

    # Normalised join tables (if not already created by prior migration)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = {t for t in inspector.get_table_names()}

    if "campaign_models" not in existing:
        op.create_table(
            "campaign_models",
            sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("campaigns.id"), primary_key=True),
            sa.Column("model_id", sa.Integer(), sa.ForeignKey("llm_models.id"), primary_key=True),
        )

    if "campaign_benchmarks" not in existing:
        op.create_table(
            "campaign_benchmarks",
            sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("campaigns.id"), primary_key=True),
            sa.Column("benchmark_id", sa.Integer(), sa.ForeignKey("benchmarks.id"), primary_key=True),
        )

    if "benchmark_tags" not in existing:
        op.create_table(
            "benchmark_tags",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("benchmark_id", sa.Integer(), sa.ForeignKey("benchmarks.id"), nullable=False, index=True),
            sa.Column("tag", sa.String(), nullable=False, index=True),
        )

    if "eval_run_metrics" not in existing:
        op.create_table(
            "eval_run_metrics",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("eval_runs.id"), nullable=False, index=True),
            sa.Column("metric_key", sa.String(), nullable=False),
            sa.Column("metric_value_json", sa.String(), nullable=False, server_default="null"),
        )


def downgrade() -> None:
    with op.batch_alter_table("campaigns") as batch_op:
        batch_op.drop_column("tenant_id")
        batch_op.drop_column("owner_id")
    op.drop_table("benchmark_packs")
