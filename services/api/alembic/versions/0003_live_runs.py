"""Live runs: runs with their input items, stages, unit charts and events, and uploaded files
(PLAN_V2 §3).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("origin", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("wafers", sa.Integer(), nullable=False),
        sa.Column(
            "alarms",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("alarms_not_listed", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_seq", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')", name=op.f("ck_runs_status")
        ),
        sa.PrimaryKeyConstraint("run_id", name=op.f("pk_runs")),
    )
    op.create_index(op.f("ix_runs_expires_at"), "runs", ["expires_at"], unique=False)
    op.create_index(
        "ix_runs_unfinished",
        "runs",
        ["heartbeat_at"],
        unique=False,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_table(
        "uploads",
        sa.Column("upload_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("runnable", sa.Boolean(), nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("items", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint("kind IN ('sensors', 'wafers')", name=op.f("ck_uploads_kind")),
        sa.PrimaryKeyConstraint("upload_id", name=op.f("pk_uploads")),
    )
    op.create_index(op.f("ix_uploads_expires_at"), "uploads", ["expires_at"], unique=False)
    op.create_table(
        "run_events",
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.run_id"], name=op.f("fk_run_events_run_id_runs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("run_id", "seq", name=op.f("pk_run_events")),
    )
    op.create_table(
        "run_items",
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint("kind IN ('unit', 'wafer')", name=op.f("ck_run_items_kind")),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.run_id"], name=op.f("fk_run_items_run_id_runs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("run_id", "kind", "position", name=op.f("pk_run_items")),
    )
    op.create_table(
        "run_unit_charts",
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("chart", sa.LargeBinary(), nullable=False),
        sa.Column("z", sa.LargeBinary(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.run_id"],
            name=op.f("fk_run_unit_charts_run_id_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("run_id", "position", name=op.f("pk_run_unit_charts")),
    )
    op.create_table(
        "run_stages",
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.run_id"], name=op.f("fk_run_stages_run_id_runs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("run_id", "position", name=op.f("pk_run_stages")),
    )


def downgrade() -> None:
    op.drop_table("run_stages")
    op.drop_table("run_unit_charts")
    op.drop_table("run_items")
    op.drop_table("run_events")
    op.drop_index(op.f("ix_uploads_expires_at"), table_name="uploads")
    op.drop_table("uploads")
    op.drop_index(
        "ix_runs_unfinished",
        table_name="runs",
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.drop_index(op.f("ix_runs_expires_at"), table_name="runs")
    op.drop_table("runs")
