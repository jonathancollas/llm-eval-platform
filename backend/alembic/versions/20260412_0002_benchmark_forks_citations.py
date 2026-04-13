"""add benchmark fork and citation tables

Revision ID: 20260412_0002
Revises: 20260412_0001
Create Date: 2026-04-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection


revision = "20260412_0002"
down_revision = "20260412_0001"
branch_labels = None
depends_on = None


def _table_exists(conn: Connection, table_name: str) -> bool:
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    conn = op.get_bind()

    if not _table_exists(conn, "benchmark_forks"):
        op.create_table(
            "benchmark_forks",
            sa.Column("child_benchmark_id", sa.Integer(), sa.ForeignKey("benchmarks.id", ondelete="CASCADE"), nullable=False),
            sa.Column("parent_benchmark_id", sa.Integer(), sa.ForeignKey("benchmarks.id", ondelete="CASCADE"), nullable=False),
            sa.Column("fork_type", sa.Text(), nullable=False, server_default="extension"),
            sa.Column("changes_description", sa.Text(), nullable=False, server_default=""),
            sa.Column("forked_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("forked_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.PrimaryKeyConstraint("child_benchmark_id"),
        )
    op.create_index("idx_benchmark_forks_parent_benchmark_id", "benchmark_forks", ["parent_benchmark_id"], unique=False, if_not_exists=True)
    op.create_index("idx_benchmark_forks_fork_type", "benchmark_forks", ["fork_type"], unique=False, if_not_exists=True)
    op.create_index("idx_benchmark_forks_forked_by", "benchmark_forks", ["forked_by"], unique=False, if_not_exists=True)
    op.create_index("idx_benchmark_forks_forked_at", "benchmark_forks", ["forked_at"], unique=False, if_not_exists=True)

    if not _table_exists(conn, "benchmark_citations"):
        op.create_table(
            "benchmark_citations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("benchmark_id", sa.Integer(), sa.ForeignKey("benchmarks.id", ondelete="CASCADE"), nullable=False),
            sa.Column("paper_doi", sa.Text(), nullable=False),
            sa.Column("citing_lab", sa.Text(), nullable=False, server_default=""),
            sa.Column("year", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
    op.create_index("idx_benchmark_citations_benchmark_id", "benchmark_citations", ["benchmark_id"], unique=False, if_not_exists=True)
    op.create_index("idx_benchmark_citations_paper_doi", "benchmark_citations", ["paper_doi"], unique=False, if_not_exists=True)
    op.create_index("idx_benchmark_citations_citing_lab", "benchmark_citations", ["citing_lab"], unique=False, if_not_exists=True)
    op.create_index("idx_benchmark_citations_year", "benchmark_citations", ["year"], unique=False, if_not_exists=True)


def downgrade() -> None:
    op.drop_index("idx_benchmark_citations_year", table_name="benchmark_citations", if_exists=True)
    op.drop_index("idx_benchmark_citations_citing_lab", table_name="benchmark_citations", if_exists=True)
    op.drop_index("idx_benchmark_citations_paper_doi", table_name="benchmark_citations", if_exists=True)
    op.drop_index("idx_benchmark_citations_benchmark_id", table_name="benchmark_citations", if_exists=True)
    op.drop_table("benchmark_citations", if_exists=True)

    op.drop_index("idx_benchmark_forks_forked_at", table_name="benchmark_forks", if_exists=True)
    op.drop_index("idx_benchmark_forks_forked_by", table_name="benchmark_forks", if_exists=True)
    op.drop_index("idx_benchmark_forks_fork_type", table_name="benchmark_forks", if_exists=True)
    op.drop_index("idx_benchmark_forks_parent_benchmark_id", table_name="benchmark_forks", if_exists=True)
    op.drop_table("benchmark_forks", if_exists=True)
