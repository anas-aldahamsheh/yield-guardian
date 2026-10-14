"""Tables of the API's own state: sessions, investigations, the job queue, work orders, audit, alarms.

Every timestamp is timestamptz and written in UTC. JSONB columns hold contract models dumped with
`model_dump(mode="json")`, so they read back with `model_validate`.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    Sequence,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from yield_guardian.db.base import Base

JsonList = list[dict[str, Any]]
JsonObject = dict[str, Any]

WORK_ORDER_NUMBER = Sequence("work_order_number_seq", metadata=Base.metadata)


class SessionRow(Base):
    """A signed-in session. Only the SHA-256 of the cookie token is stored."""

    __tablename__ = "sessions"
    __table_args__ = (CheckConstraint("role IN ('engineer', 'admin')", name="role"),)

    session_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    role: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    csrf_token: Mapped[str] = mapped_column(Text)
    client: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime] = mapped_column(index=True)


class InvestigationRow(Base):
    """An investigation and the snapshot its events build (steps, evidence, report, decision)."""

    __tablename__ = "investigations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'awaiting_decision', 'approved', 'rejected', 'failed')",
            name="status",
        ),
        CheckConstraint("trigger_kind IN ('alarm', 'unit', 'wafer', 'lot')", name="trigger_kind"),
        Index("ix_investigations_created", "created_at", "investigation_id"),
        Index("ix_investigations_status_created", "status", "created_at", "investigation_id"),
        Index("ix_investigations_trigger", "trigger_kind", "trigger_ref"),
    )

    investigation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    trigger_kind: Mapped[str] = mapped_column(Text)
    trigger_ref: Mapped[str] = mapped_column(Text)
    trigger_question: Mapped[str | None] = mapped_column(Text)
    recorded: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    last_seq: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    steps: Mapped[JsonList] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    evidence: Mapped[JsonList] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    models: Mapped[JsonList] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    usage: Mapped[JsonObject | None] = mapped_column(JSONB)
    report: Mapped[JsonObject | None] = mapped_column(JSONB)
    verification: Mapped[JsonObject | None] = mapped_column(JSONB)
    decision: Mapped[JsonObject | None] = mapped_column(JSONB)
    error: Mapped[JsonObject | None] = mapped_column(JSONB)
    work_order_id: Mapped[str | None] = mapped_column(Text)


class InvestigationEventRow(Base):
    """One SSE event; `seq` is monotonic per investigation, starting at 1."""

    __tablename__ = "investigation_events"

    investigation_id: Mapped[str] = mapped_column(
        Text, ForeignKey("investigations.investigation_id", ondelete="CASCADE"), primary_key=True
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime]
    payload: Mapped[JsonObject] = mapped_column(JSONB)


class InvestigationJobRow(Base):
    """The job queue: claimed with SELECT ... FOR UPDATE SKIP LOCKED, kept alive by a heartbeat."""

    __tablename__ = "investigation_jobs"
    __table_args__ = (
        CheckConstraint("kind IN ('run', 'resume')", name="kind"),
        CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name="status"),
        Index(
            "ix_investigation_jobs_queued",
            "job_id",
            postgresql_where=text("status = 'queued'"),
        ),
        Index(
            "ix_investigation_jobs_running",
            "heartbeat_at",
            postgresql_where=text("status = 'running'"),
        ),
    )

    job_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(
        Text, ForeignKey("investigations.investigation_id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(Text)
    payload: Mapped[JsonObject] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(Text, server_default=text("'queued'"))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    worker: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime]
    started_at: Mapped[datetime | None]
    heartbeat_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]


class WorkOrderRow(Base):
    __tablename__ = "work_orders"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'in_progress', 'done', 'cancelled')", name="status"),
    )

    work_order_id: Mapped[str] = mapped_column(Text, primary_key=True)
    investigation_id: Mapped[str] = mapped_column(
        Text, ForeignKey("investigations.investigation_id", ondelete="CASCADE"), unique=True
    )
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    created_by: Mapped[str] = mapped_column(Text)
    actions: Mapped[JsonList] = mapped_column(JSONB)
    note: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(Text)
    outcome_confirmed: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class AuditEntryRow(Base):
    __tablename__ = "audit_entries"
    __table_args__ = (Index("ix_audit_entries_action", "action", "audit_id"),)

    audit_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    at: Mapped[datetime]
    actor_role: Mapped[str] = mapped_column(Text)
    actor_name: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    target_kind: Mapped[str] = mapped_column(Text)
    target_id: Mapped[str] = mapped_column(Text)
    details: Mapped[JsonObject] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class AlarmStateRow(Base):
    """The state of an alarm that left "open". Alarms without a row are open."""

    __tablename__ = "alarm_states"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'investigating', 'closed')", name="status"),
    )

    alarm_id: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(Text)
    investigation_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("investigations.investigation_id", ondelete="SET NULL"), index=True
    )
    updated_at: Mapped[datetime]
