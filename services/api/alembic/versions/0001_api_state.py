"""API state: sessions, investigations, the job queue, work orders, audit entries, alarm states.

Revision ID: 0001
Revises:
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pgvector is used by the wafer and knowledge tables of later revisions.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(sa.schema.CreateSequence(sa.Sequence("work_order_number_seq")))
    op.create_table(
        "audit_entries",
        sa.Column("audit_id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_role", sa.Text(), nullable=False),
        sa.Column("actor_name", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_kind", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("audit_id", name=op.f("pk_audit_entries")),
    )
    op.create_index(
        "ix_audit_entries_action", "audit_entries", ["action", "audit_id"], unique=False
    )
    op.create_table(
        "investigations",
        sa.Column("investigation_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("trigger_kind", sa.Text(), nullable=False),
        sa.Column("trigger_ref", sa.Text(), nullable=False),
        sa.Column("trigger_question", sa.Text(), nullable=True),
        sa.Column("recorded", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seq", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "steps",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "models",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("verification", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("decision", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("work_order_id", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'awaiting_decision', 'approved', 'rejected', 'failed')",
            name=op.f("ck_investigations_status"),
        ),
        sa.CheckConstraint(
            "trigger_kind IN ('alarm', 'unit', 'wafer', 'lot')",
            name=op.f("ck_investigations_trigger_kind"),
        ),
        sa.PrimaryKeyConstraint("investigation_id", name=op.f("pk_investigations")),
    )
    op.create_index(
        "ix_investigations_created",
        "investigations",
        ["created_at", "investigation_id"],
        unique=False,
    )
    op.create_index(
        "ix_investigations_status_created",
        "investigations",
        ["status", "created_at", "investigation_id"],
        unique=False,
    )
    op.create_index(
        "ix_investigations_trigger", "investigations", ["trigger_kind", "trigger_ref"], unique=False
    )
    op.create_table(
        "sessions",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("csrf_token", sa.Text(), nullable=False),
        sa.Column("client", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('engineer', 'admin')", name=op.f("ck_sessions_role")),
        sa.PrimaryKeyConstraint("session_id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sessions_token_hash")),
    )
    op.create_index(op.f("ix_sessions_expires_at"), "sessions", ["expires_at"], unique=False)
    op.create_table(
        "alarm_states",
        sa.Column("alarm_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("investigation_id", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('open', 'investigating', 'closed')", name=op.f("ck_alarm_states_status")
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id"],
            ["investigations.investigation_id"],
            name=op.f("fk_alarm_states_investigation_id_investigations"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("alarm_id", name=op.f("pk_alarm_states")),
    )
    op.create_index(
        op.f("ix_alarm_states_investigation_id"), "alarm_states", ["investigation_id"], unique=False
    )
    op.create_table(
        "investigation_events",
        sa.Column("investigation_id", sa.Text(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["investigation_id"],
            ["investigations.investigation_id"],
            name=op.f("fk_investigation_events_investigation_id_investigations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("investigation_id", "seq", name=op.f("pk_investigation_events")),
    )
    op.create_table(
        "investigation_jobs",
        sa.Column("job_id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("investigation_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("worker", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('run', 'resume')", name=op.f("ck_investigation_jobs_kind")),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')",
            name=op.f("ck_investigation_jobs_status"),
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id"],
            ["investigations.investigation_id"],
            name=op.f("fk_investigation_jobs_investigation_id_investigations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("job_id", name=op.f("pk_investigation_jobs")),
    )
    op.create_index(
        op.f("ix_investigation_jobs_investigation_id"),
        "investigation_jobs",
        ["investigation_id"],
        unique=False,
    )
    op.create_index(
        "ix_investigation_jobs_queued",
        "investigation_jobs",
        ["job_id"],
        unique=False,
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.create_index(
        "ix_investigation_jobs_running",
        "investigation_jobs",
        ["heartbeat_at"],
        unique=False,
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_table(
        "work_orders",
        sa.Column("work_order_id", sa.Text(), nullable=False),
        sa.Column("investigation_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("actions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column(
            "outcome_confirmed", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'done', 'cancelled')",
            name=op.f("ck_work_orders_status"),
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id"],
            ["investigations.investigation_id"],
            name=op.f("fk_work_orders_investigation_id_investigations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("work_order_id", name=op.f("pk_work_orders")),
        sa.UniqueConstraint("investigation_id", name=op.f("uq_work_orders_investigation_id")),
    )


def downgrade() -> None:
    op.drop_table("work_orders")
    op.drop_index(
        "ix_investigation_jobs_running",
        table_name="investigation_jobs",
        postgresql_where=sa.text("status = 'running'"),
    )
    op.drop_index(
        "ix_investigation_jobs_queued",
        table_name="investigation_jobs",
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.drop_index(op.f("ix_investigation_jobs_investigation_id"), table_name="investigation_jobs")
    op.drop_table("investigation_jobs")
    op.drop_table("investigation_events")
    op.drop_index(op.f("ix_alarm_states_investigation_id"), table_name="alarm_states")
    op.drop_table("alarm_states")
    op.drop_index(op.f("ix_sessions_expires_at"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_investigations_trigger", table_name="investigations")
    op.drop_index("ix_investigations_status_created", table_name="investigations")
    op.drop_index("ix_investigations_created", table_name="investigations")
    op.drop_table("investigations")
    op.drop_index("ix_audit_entries_action", table_name="audit_entries")
    op.drop_table("audit_entries")
    op.execute(sa.schema.DropSequence(sa.Sequence("work_order_number_seq")))
    # The vector extension stays: it is database-wide and may serve objects outside this chain.
