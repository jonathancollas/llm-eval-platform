"""add performance indexes

Revision ID: 20260413_0001
Revises: 20260412_0002
Create Date: 2026-04-13

Adds composite indexes on the hottest query paths:
- EvalRun  (campaign_id, status), (model_id, status), (benchmark_id, status)
- EvalResult (run_id, score),      (run_id, item_index)
- FailureProfile (campaign_id, model_id)
- RedboxExploit  (model_id, mutation_type)
- TelemetryEvent (tenant_id, event_type, timestamp)
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection


revision = "20260413_0001"
down_revision = "20260412_0002"
branch_labels = None
depends_on = None


def _table_exists(conn: Connection, table_name: str) -> bool:
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def _index_exists(conn: Connection, index_name: str) -> bool:
    insp = sa.inspect(conn)
    for table_name in insp.get_table_names():
        for idx in insp.get_indexes(table_name):
            if idx["name"] == index_name:
                return True
    return False


def upgrade() -> None:
    conn = op.get_bind()

    # ── EvalRun composite indexes ────────────────────────────────────────────
    if _table_exists(conn, "eval_runs"):
        if not _index_exists(conn, "ix_eval_runs_campaign_id_status"):
            op.create_index(
                "ix_eval_runs_campaign_id_status",
                "eval_runs",
                ["campaign_id", "status"],
            )
        if not _index_exists(conn, "ix_eval_runs_model_id_status"):
            op.create_index(
                "ix_eval_runs_model_id_status",
                "eval_runs",
                ["model_id", "status"],
            )
        if not _index_exists(conn, "ix_eval_runs_benchmark_id_status"):
            op.create_index(
                "ix_eval_runs_benchmark_id_status",
                "eval_runs",
                ["benchmark_id", "status"],
            )

    # ── EvalResult composite indexes ─────────────────────────────────────────
    if _table_exists(conn, "eval_results"):
        if not _index_exists(conn, "ix_eval_results_run_id_score"):
            op.create_index(
                "ix_eval_results_run_id_score",
                "eval_results",
                ["run_id", "score"],
            )
        if not _index_exists(conn, "ix_eval_results_run_id_item_index"):
            op.create_index(
                "ix_eval_results_run_id_item_index",
                "eval_results",
                ["run_id", "item_index"],
            )

    # ── FailureProfile composite index ───────────────────────────────────────
    if _table_exists(conn, "failure_profiles"):
        if not _index_exists(conn, "ix_failure_profiles_campaign_id_model_id"):
            op.create_index(
                "ix_failure_profiles_campaign_id_model_id",
                "failure_profiles",
                ["campaign_id", "model_id"],
            )

    # ── RedboxExploit composite index ────────────────────────────────────────
    if _table_exists(conn, "redbox_exploits"):
        if not _index_exists(conn, "ix_redbox_exploits_model_id_mutation_type"):
            op.create_index(
                "ix_redbox_exploits_model_id_mutation_type",
                "redbox_exploits",
                ["model_id", "mutation_type"],
            )

    # ── TelemetryEvent composite index ───────────────────────────────────────
    if _table_exists(conn, "telemetry_events"):
        if not _index_exists(conn, "ix_telemetry_events_tenant_id_event_type_timestamp"):
            op.create_index(
                "ix_telemetry_events_tenant_id_event_type_timestamp",
                "telemetry_events",
                ["tenant_id", "event_type", "timestamp"],
            )


def downgrade() -> None:
    conn = op.get_bind()

    for index_name, table_name in [
        ("ix_eval_runs_campaign_id_status", "eval_runs"),
        ("ix_eval_runs_model_id_status", "eval_runs"),
        ("ix_eval_runs_benchmark_id_status", "eval_runs"),
        ("ix_eval_results_run_id_score", "eval_results"),
        ("ix_eval_results_run_id_item_index", "eval_results"),
        ("ix_failure_profiles_campaign_id_model_id", "failure_profiles"),
        ("ix_redbox_exploits_model_id_mutation_type", "redbox_exploits"),
        ("ix_telemetry_events_tenant_id_event_type_timestamp", "telemetry_events"),
    ]:
        if _index_exists(conn, index_name):
            op.drop_index(index_name, table_name=table_name)
