"""add redroom_traces table

Revision ID: 20260427_0001
Revises: 20260419_0002
Create Date: 2026-04-27

Creates the immutable, HMAC-signed trace store used by Phase D Red
Room. Schema mirrors the SQLModel in
``backend/eval_engine/redroom/trace_store.py``. Adding the migration
makes deployments safe (no implicit ``create_all`` reliance) and
gives operators a clean rollback path.

The table is APPEND-ONLY at the application level. Operators with
direct DB access could in principle delete rows; the trace chain's
``prev_signature`` is what makes such tampering detectable via
``verify_chain()``.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection


revision = "20260427_0001"
down_revision = "20260419_0002"
branch_labels = None
depends_on = None


def _table_exists(conn: Connection, table_name: str) -> bool:
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    conn = op.get_bind()

    if not _table_exists(conn, "redroom_traces"):
        op.create_table(
            "redroom_traces",
            # Identity
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("uuid", sa.Text(), nullable=False, unique=True),
            # Context
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("session_id", sa.String(length=64), nullable=False),
            sa.Column("target_model_id", sa.Integer(), nullable=True),
            sa.Column("target_class", sa.String(length=20), nullable=False),
            sa.Column("aggressiveness", sa.Integer(), nullable=False),
            # Event
            sa.Column("kind", sa.String(length=20), nullable=False),
            sa.Column("verdict", sa.String(length=20), nullable=True),
            sa.Column("engine", sa.String(length=40), nullable=True),
            # Payload
            sa.Column(
                "payload_json",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            # Replay identity
            sa.Column("replay_hash", sa.String(length=64), nullable=False),
            # Provenance
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            # Integrity
            sa.Column("row_signature", sa.String(length=64), nullable=False),
            sa.Column("prev_signature", sa.String(length=64), nullable=True),
        )

    op.create_index(
        "ix_redroom_traces_uuid",
        "redroom_traces",
        ["uuid"],
        unique=True,
        if_not_exists=True,
    )
    op.create_index(
        "ix_redroom_traces_tenant_id",
        "redroom_traces",
        ["tenant_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_redroom_traces_session_id",
        "redroom_traces",
        ["session_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_redroom_traces_target_model_id",
        "redroom_traces",
        ["target_model_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_redroom_traces_kind_created_at",
        "redroom_traces",
        ["kind", "created_at"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_redroom_traces_replay_hash",
        "redroom_traces",
        ["replay_hash"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_redroom_traces_row_signature",
        "redroom_traces",
        ["row_signature"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_redroom_traces_row_signature", table_name="redroom_traces")
    op.drop_index("ix_redroom_traces_replay_hash", table_name="redroom_traces")
    op.drop_index(
        "ix_redroom_traces_kind_created_at", table_name="redroom_traces"
    )
    op.drop_index(
        "ix_redroom_traces_target_model_id", table_name="redroom_traces"
    )
    op.drop_index("ix_redroom_traces_session_id", table_name="redroom_traces")
    op.drop_index("ix_redroom_traces_tenant_id", table_name="redroom_traces")
    op.drop_index("ix_redroom_traces_uuid", table_name="redroom_traces")
    op.drop_table("redroom_traces")
