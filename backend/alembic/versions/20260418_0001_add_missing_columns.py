"""add missing columns to llm_models, benchmarks, campaigns, eval_runs

Revision ID: 20260418_0001
Revises: 20260413_0001
Create Date: 2026-04-18

Idempotent: checks column existence before each ALTER TABLE so it is safe
to run against both fresh and existing databases.

Affected tables
---------------
llm_models  : is_free, max_output_tokens, is_moderated, tokenizer,
              instruct_type, hugging_face_id, model_created_at, is_open_weight
benchmarks  : eval_dimension, source
campaigns   : system_prompt_hash, dataset_version, judge_model,
              run_context_json, current_item_index, current_item_total,
              current_item_label, last_heartbeat_at
eval_runs   : capability_score, propensity_score
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection

revision = "20260418_0001"
down_revision = "20260413_0001"
branch_labels = None
depends_on = None


def _existing_columns(conn: Connection, table: str) -> set[str]:
    insp = sa.inspect(conn)
    return {c["name"] for c in insp.get_columns(table)}


def _add_if_missing(
    conn: Connection,
    table: str,
    column: str,
    col_type: sa.types.TypeEngine,
    *,
    nullable: bool = True,
    server_default: str | None = None,
) -> None:
    if column not in _existing_columns(conn, table):
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

    # ── llm_models ────────────────────────────────────────────────────────────
    _add_if_missing(conn, "llm_models", "is_free",           sa.Integer(),  server_default="0")
    _add_if_missing(conn, "llm_models", "max_output_tokens", sa.Integer(),  server_default="0")
    _add_if_missing(conn, "llm_models", "is_moderated",      sa.Integer(),  server_default="0")
    _add_if_missing(conn, "llm_models", "tokenizer",         sa.Text(),     server_default="''")
    _add_if_missing(conn, "llm_models", "instruct_type",     sa.Text(),     server_default="''")
    _add_if_missing(conn, "llm_models", "hugging_face_id",   sa.Text(),     server_default="''")
    _add_if_missing(conn, "llm_models", "model_created_at",  sa.Integer(),  server_default="0")
    _add_if_missing(conn, "llm_models", "is_open_weight",    sa.Integer(),  server_default="0")

    # ── benchmarks ────────────────────────────────────────────────────────────
    _add_if_missing(conn, "benchmarks", "eval_dimension", sa.Text(), server_default="'capability'")
    _add_if_missing(conn, "benchmarks", "source",         sa.Text(), server_default="'public'")

    # ── campaigns ─────────────────────────────────────────────────────────────
    _add_if_missing(conn, "campaigns", "system_prompt_hash",  sa.Text())
    _add_if_missing(conn, "campaigns", "dataset_version",     sa.Text())
    _add_if_missing(conn, "campaigns", "judge_model",         sa.Text())
    _add_if_missing(conn, "campaigns", "run_context_json",    sa.Text())
    _add_if_missing(conn, "campaigns", "current_item_index",  sa.Integer())
    _add_if_missing(conn, "campaigns", "current_item_total",  sa.Integer())
    _add_if_missing(conn, "campaigns", "current_item_label",  sa.Text())
    _add_if_missing(conn, "campaigns", "last_heartbeat_at",   sa.DateTime())

    # ── eval_runs ─────────────────────────────────────────────────────────────
    _add_if_missing(conn, "eval_runs", "capability_score",  sa.Float())
    _add_if_missing(conn, "eval_runs", "propensity_score",  sa.Float())


def downgrade() -> None:
    # SQLite does not support DROP COLUMN in older versions; downgrade is a no-op.
    pass
