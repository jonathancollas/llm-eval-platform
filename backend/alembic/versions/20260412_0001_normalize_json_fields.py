"""normalize json-backed relations

Revision ID: 20260412_0001
Revises:
Create Date: 2026-04-12
"""

from __future__ import annotations

import json
from collections import defaultdict

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError


revision = "20260412_0001"
down_revision = None
branch_labels = None
depends_on = None


def _table_exists(conn: Connection, table_name: str) -> bool:
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def _insert_ignore(conn: Connection, insert_stmt) -> None:
    try:
        conn.execute(insert_stmt)
    except IntegrityError:
        pass


def upgrade() -> None:
    conn = op.get_bind()

    if not _table_exists(conn, "campaign_models"):
        op.create_table(
            "campaign_models",
            sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
            sa.Column("model_id", sa.Integer(), sa.ForeignKey("llm_models.id", ondelete="CASCADE"), nullable=False),
            sa.PrimaryKeyConstraint("campaign_id", "model_id"),
        )

    if not _table_exists(conn, "campaign_benchmarks"):
        op.create_table(
            "campaign_benchmarks",
            sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
            sa.Column("benchmark_id", sa.Integer(), sa.ForeignKey("benchmarks.id", ondelete="CASCADE"), nullable=False),
            sa.PrimaryKeyConstraint("campaign_id", "benchmark_id"),
        )

    if not _table_exists(conn, "benchmark_tags"):
        op.create_table(
            "benchmark_tags",
            sa.Column("benchmark_id", sa.Integer(), sa.ForeignKey("benchmarks.id", ondelete="CASCADE"), nullable=False),
            sa.Column("tag", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("benchmark_id", "tag"),
        )
    op.create_index("idx_benchmark_tags_tag", "benchmark_tags", ["tag"], unique=False, if_not_exists=True)

    if not _table_exists(conn, "eval_run_metrics"):
        op.create_table(
            "eval_run_metrics",
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("eval_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("metric_key", sa.Text(), nullable=False),
            sa.Column("metric_value_json", sa.Text(), nullable=False, server_default="null"),
            sa.PrimaryKeyConstraint("run_id", "metric_key"),
        )

    campaigns = conn.execute(sa.text("SELECT id, model_ids, benchmark_ids FROM campaigns")).fetchall()
    campaign_models = sa.table(
        "campaign_models",
        sa.column("campaign_id", sa.Integer),
        sa.column("model_id", sa.Integer),
    )
    campaign_benchmarks = sa.table(
        "campaign_benchmarks",
        sa.column("campaign_id", sa.Integer),
        sa.column("benchmark_id", sa.Integer),
    )
    for row in campaigns:
        model_ids = []
        benchmark_ids = []
        try:
            model_ids = json.loads(row.model_ids or "[]")
        except Exception:
            pass
        try:
            benchmark_ids = json.loads(row.benchmark_ids or "[]")
        except Exception:
            pass

        for model_id in model_ids:
            if isinstance(model_id, int):
                _insert_ignore(
                    conn,
                    campaign_models.insert().values(campaign_id=row.id, model_id=model_id),
                )
        for benchmark_id in benchmark_ids:
            if isinstance(benchmark_id, int):
                _insert_ignore(
                    conn,
                    campaign_benchmarks.insert().values(campaign_id=row.id, benchmark_id=benchmark_id),
                )

    benchmarks = conn.execute(sa.text("SELECT id, tags FROM benchmarks")).fetchall()
    benchmark_tags = sa.table(
        "benchmark_tags",
        sa.column("benchmark_id", sa.Integer),
        sa.column("tag", sa.Text),
    )
    for row in benchmarks:
        tags = []
        try:
            tags = json.loads(row.tags or "[]")
        except Exception:
            pass
        for tag in tags:
            if isinstance(tag, str) and tag:
                _insert_ignore(
                    conn,
                    benchmark_tags.insert().values(benchmark_id=row.id, tag=tag),
                )

    eval_runs = conn.execute(sa.text("SELECT id, metrics_json FROM eval_runs")).fetchall()
    eval_run_metrics = sa.table(
        "eval_run_metrics",
        sa.column("run_id", sa.Integer),
        sa.column("metric_key", sa.Text),
        sa.column("metric_value_json", sa.Text),
    )
    for row in eval_runs:
        try:
            metrics = json.loads(row.metrics_json or "{}")
        except Exception:
            metrics = {}
        if not isinstance(metrics, dict):
            continue
        for key, value in metrics.items():
            _insert_ignore(
                conn,
                eval_run_metrics.insert().values(
                    run_id=row.id,
                    metric_key=str(key),
                    metric_value_json=json.dumps(value),
                ),
            )


def downgrade() -> None:
    conn = op.get_bind()

    campaign_models_rows = conn.execute(
        sa.text("SELECT campaign_id, model_id FROM campaign_models ORDER BY campaign_id, model_id")
    ).fetchall() if _table_exists(conn, "campaign_models") else []
    grouped_models: dict[int, list[int]] = defaultdict(list)
    for row in campaign_models_rows:
        grouped_models[row.campaign_id].append(row.model_id)

    campaign_bench_rows = conn.execute(
        sa.text("SELECT campaign_id, benchmark_id FROM campaign_benchmarks ORDER BY campaign_id, benchmark_id")
    ).fetchall() if _table_exists(conn, "campaign_benchmarks") else []
    grouped_benchmarks: dict[int, list[int]] = defaultdict(list)
    for row in campaign_bench_rows:
        grouped_benchmarks[row.campaign_id].append(row.benchmark_id)

    for campaign_id, model_ids in grouped_models.items():
        conn.execute(
            sa.text("UPDATE campaigns SET model_ids = :model_ids WHERE id = :id"),
            {"id": campaign_id, "model_ids": json.dumps(model_ids)},
        )
    for campaign_id, benchmark_ids in grouped_benchmarks.items():
        conn.execute(
            sa.text("UPDATE campaigns SET benchmark_ids = :benchmark_ids WHERE id = :id"),
            {"id": campaign_id, "benchmark_ids": json.dumps(benchmark_ids)},
        )

    benchmark_tags_rows = conn.execute(
        sa.text("SELECT benchmark_id, tag FROM benchmark_tags ORDER BY benchmark_id, tag")
    ).fetchall() if _table_exists(conn, "benchmark_tags") else []
    grouped_tags: dict[int, list[str]] = defaultdict(list)
    for row in benchmark_tags_rows:
        grouped_tags[row.benchmark_id].append(row.tag)
    for benchmark_id, tags in grouped_tags.items():
        conn.execute(
            sa.text("UPDATE benchmarks SET tags = :tags WHERE id = :id"),
            {"id": benchmark_id, "tags": json.dumps(tags)},
        )

    metric_rows = conn.execute(
        sa.text("SELECT run_id, metric_key, metric_value_json FROM eval_run_metrics ORDER BY run_id, metric_key")
    ).fetchall() if _table_exists(conn, "eval_run_metrics") else []
    grouped_metrics: dict[int, dict] = defaultdict(dict)
    for row in metric_rows:
        grouped_metrics[row.run_id][row.metric_key] = json.loads(row.metric_value_json)
    for run_id, metrics in grouped_metrics.items():
        conn.execute(
            sa.text("UPDATE eval_runs SET metrics_json = :metrics WHERE id = :id"),
            {"id": run_id, "metrics": json.dumps(metrics)},
        )

    op.drop_table("eval_run_metrics", if_exists=True)
    op.drop_index("idx_benchmark_tags_tag", table_name="benchmark_tags", if_exists=True)
    op.drop_table("benchmark_tags", if_exists=True)
    op.drop_table("campaign_benchmarks", if_exists=True)
    op.drop_table("campaign_models", if_exists=True)
