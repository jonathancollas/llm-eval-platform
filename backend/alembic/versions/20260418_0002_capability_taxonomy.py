"""add capability taxonomy tables (M3)

Revision ID: 20260418_0002
Revises: 20260418_0001
Create Date: 2026-04-18

Creates the four tables that form the flat-first, graph-ready capability
taxonomy defined in M3:

  capability_domains            — top-level domains (cybersecurity, reasoning …)
  capability_sub_capabilities   — sub-capability nodes; parent_id FK is
                                  reserved for future graph migration to Neo4j
  benchmark_capability_mappings — many-to-many: benchmark ↔ sub-capability
  capability_eval_scores        — persisted score per (model, sub-capability)
                                  with bootstrap CI

Graph-DB upgrade path
---------------------
The schema is Neo4j-compatible without data loss:
  • capability_domains          → :Domain nodes
  • capability_sub_capabilities → :SubCapability nodes + BELONGS_TO edges
  • parent_id self-FK           → :HAS_CHILD edges (enables DAG expansion)
  • benchmark_capability_mappings → :EVALUATES edges (Benchmark → SubCapability)
  • capability_eval_scores      → :SCORED_ON edges with {score, ci_lower, ci_upper}

Migration to graph DB is justified when:
  1. Taxonomy exceeds ~500 nodes (traversal queries become expensive in SQL)
  2. Cross-domain sub-capability inheritance is needed
  3. Graph algorithms (PageRank on capability importance) are required
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection


revision = "20260418_0002"
down_revision = "20260418_0001"
branch_labels = None
depends_on = None


def _table_exists(conn: Connection, table_name: str) -> bool:
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def _index_exists(conn: Connection, index_name: str) -> bool:
    insp = sa.inspect(conn)
    for tname in insp.get_table_names():
        for idx in insp.get_indexes(tname):
            if idx["name"] == index_name:
                return True
    return False


def upgrade() -> None:
    conn = op.get_bind()

    # ── capability_domains ───────────────────────────────────────────────────
    if not _table_exists(conn, "capability_domains"):
        op.create_table(
            "capability_domains",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("slug", sa.Text(), nullable=False),
            sa.Column("display_name", sa.Text(), nullable=False, server_default=""),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("uq_capability_domains_slug", "capability_domains", ["slug"], unique=True)

    # ── capability_sub_capabilities ──────────────────────────────────────────
    if not _table_exists(conn, "capability_sub_capabilities"):
        op.create_table(
            "capability_sub_capabilities",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("domain_id", sa.Integer(), sa.ForeignKey("capability_domains.id", ondelete="CASCADE"), nullable=False),
            sa.Column("slug", sa.Text(), nullable=False),
            sa.Column("display_name", sa.Text(), nullable=False, server_default=""),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("difficulty", sa.Text(), nullable=False, server_default="medium"),
            sa.Column("risk_level", sa.Text(), nullable=False, server_default="low"),
            # Graph-ready self-FK reserved for future Neo4j migration
            sa.Column("parent_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_capability_sub_capabilities_domain_id", "capability_sub_capabilities", ["domain_id"])
        op.create_index("ix_capability_sub_capabilities_slug", "capability_sub_capabilities", ["slug"])

    # ── benchmark_capability_mappings ────────────────────────────────────────
    if not _table_exists(conn, "benchmark_capability_mappings"):
        op.create_table(
            "benchmark_capability_mappings",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("benchmark_id", sa.Integer(), sa.ForeignKey("benchmarks.id", ondelete="CASCADE"), nullable=False),
            sa.Column("sub_capability_id", sa.Integer(), sa.ForeignKey("capability_sub_capabilities.id", ondelete="CASCADE"), nullable=False),
            sa.Column("mapping_source", sa.Text(), nullable=False, server_default="auto"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_benchmark_capability_mappings_benchmark_id", "benchmark_capability_mappings", ["benchmark_id"])
        op.create_index("ix_benchmark_capability_mappings_sub_capability_id", "benchmark_capability_mappings", ["sub_capability_id"])
        op.create_index(
            "uq_benchmark_capability_mappings_bench_sub_cap",
            "benchmark_capability_mappings",
            ["benchmark_id", "sub_capability_id"],
            unique=True,
        )

    # ── capability_eval_scores ───────────────────────────────────────────────
    if not _table_exists(conn, "capability_eval_scores"):
        op.create_table(
            "capability_eval_scores",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("model_id", sa.Integer(), sa.ForeignKey("llm_models.id", ondelete="CASCADE"), nullable=False),
            sa.Column("sub_capability_id", sa.Integer(), sa.ForeignKey("capability_sub_capabilities.id", ondelete="CASCADE"), nullable=False),
            sa.Column("eval_run_id", sa.Integer(), sa.ForeignKey("eval_runs.id", ondelete="SET NULL"), nullable=True),
            sa.Column("score", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("ci_lower", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("ci_upper", sa.Float(), nullable=False, server_default="1.0"),
            sa.Column("n_items", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("scored_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_capability_eval_scores_model_id", "capability_eval_scores", ["model_id"])
        op.create_index("ix_capability_eval_scores_sub_capability_id", "capability_eval_scores", ["sub_capability_id"])
        op.create_index("ix_capability_eval_scores_eval_run_id", "capability_eval_scores", ["eval_run_id"])
        op.create_index(
            "ix_capability_eval_scores_model_sub_cap",
            "capability_eval_scores",
            ["model_id", "sub_capability_id"],
        )


def downgrade() -> None:
    conn = op.get_bind()

    for index_name, table_name in [
        ("ix_capability_eval_scores_model_sub_cap", "capability_eval_scores"),
        ("ix_capability_eval_scores_eval_run_id", "capability_eval_scores"),
        ("ix_capability_eval_scores_sub_capability_id", "capability_eval_scores"),
        ("ix_capability_eval_scores_model_id", "capability_eval_scores"),
    ]:
        if _index_exists(conn, index_name):
            op.drop_index(index_name, table_name=table_name)
    if _table_exists(conn, "capability_eval_scores"):
        op.drop_table("capability_eval_scores")

    for index_name, table_name in [
        ("uq_benchmark_capability_mappings_bench_sub_cap", "benchmark_capability_mappings"),
        ("ix_benchmark_capability_mappings_sub_capability_id", "benchmark_capability_mappings"),
        ("ix_benchmark_capability_mappings_benchmark_id", "benchmark_capability_mappings"),
    ]:
        if _index_exists(conn, index_name):
            op.drop_index(index_name, table_name=table_name)
    if _table_exists(conn, "benchmark_capability_mappings"):
        op.drop_table("benchmark_capability_mappings")

    for index_name, table_name in [
        ("ix_capability_sub_capabilities_slug", "capability_sub_capabilities"),
        ("ix_capability_sub_capabilities_domain_id", "capability_sub_capabilities"),
    ]:
        if _index_exists(conn, index_name):
            op.drop_index(index_name, table_name=table_name)
    if _table_exists(conn, "capability_sub_capabilities"):
        op.drop_table("capability_sub_capabilities")

    if _index_exists(conn, "uq_capability_domains_slug"):
        op.drop_index("uq_capability_domains_slug", table_name="capability_domains")
    if _table_exists(conn, "capability_domains"):
        op.drop_table("capability_domains")
