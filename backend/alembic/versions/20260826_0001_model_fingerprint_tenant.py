"""tenant-scope model_fingerprints

Revision ID: 20260826_0001
Revises: 20260427_0003
Create Date: 2026-08-26

ModelFingerprint was unique on model_id alone, so computing a genome for a
shared catalog model overwrote every other tenant's stored failure DNA and
mixed their eval-run scores into stats. GET /genome/models served that global
row with no tenant check.

This migration:
  - adds tenant_id (nullable for legacy rows)
  - drops the global unique index on model_id
  - adds a composite unique (tenant_id, model_id)
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection


revision = "20260826_0001"
down_revision = "20260427_0003"
branch_labels = None
depends_on = None


def _existing_columns(conn: Connection, table: str) -> set[str]:
    if table not in sa.inspect(conn).get_table_names():
        return set()
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def _add_column_if_missing(
    conn: Connection,
    table: str,
    column: str,
    col_type: sa.types.TypeEngine,
) -> None:
    if column in _existing_columns(conn, table):
        return
    op.add_column(table, sa.Column(column, col_type, nullable=True))


def _drop_model_id_unique(conn: Connection) -> None:
    insp = sa.inspect(conn)
    if "model_fingerprints" not in insp.get_table_names():
        return
    for ix in insp.get_indexes("model_fingerprints"):
        cols = list(ix.get("column_names") or [])
        if ix.get("unique") and cols == ["model_id"]:
            op.drop_index(ix["name"], table_name="model_fingerprints")
    for uk in insp.get_unique_constraints("model_fingerprints"):
        cols = list(uk.get("column_names") or [])
        if cols == ["model_id"] and uk.get("name"):
            try:
                op.drop_constraint(uk["name"], "model_fingerprints", type_="unique")
            except Exception:
                pass


def _ensure_composite_unique(conn: Connection) -> None:
    insp = sa.inspect(conn)
    if "model_fingerprints" not in insp.get_table_names():
        return
    existing = {
        ix["name"] for ix in insp.get_indexes("model_fingerprints") if ix.get("name")
    }
    existing |= {
        uk["name"]
        for uk in insp.get_unique_constraints("model_fingerprints")
        if uk.get("name")
    }
    name = "uq_model_fingerprints_tenant_model"
    if name in existing:
        return
    op.create_index(
        name,
        "model_fingerprints",
        ["tenant_id", "model_id"],
        unique=True,
    )


def upgrade() -> None:
    conn = op.get_bind()
    if "model_fingerprints" not in sa.inspect(conn).get_table_names():
        return
    _add_column_if_missing(conn, "model_fingerprints", "tenant_id", sa.Integer())
    op.create_index(
        "ix_model_fingerprints_tenant_id",
        "model_fingerprints",
        ["tenant_id"],
        unique=False,
        if_not_exists=True,
    )
    _drop_model_id_unique(conn)
    _ensure_composite_unique(conn)


def downgrade() -> None:
    pass
