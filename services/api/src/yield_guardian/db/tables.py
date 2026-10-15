"""Tables of the API's own state: sessions, investigations, the job queue, work orders, audit, alarms,
live runs (their input, stages and events) and uploads, the language-model layer (call log, response cache, role assignments, chat routes,
evaluations) and the knowledge chunks searched with PostgreSQL full-text search.

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
    Computed,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    Sequence,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
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
        CheckConstraint(
            "trigger_kind IN ('alarm', 'unit', 'wafer', 'lot', 'run_alarm')", name="trigger_kind"
        ),
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
    confirmed_cause: Mapped[JsonObject | None] = mapped_column(JSONB)
    """The fab's own record of the cause (``ConfirmedCause``), set when the work order closes."""


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


# -- live runs ----------------------------------------------------------------------------------


class RunRow(Base):
    """A live run (PLAN_V2 §3): its origin and the snapshot its events build. Expires 24 h after
    creation; `expires_at` is null while an investigation uses the run."""

    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name="status"),
        Index(
            "ix_runs_unfinished",
            "heartbeat_at",
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    run_id: Mapped[str] = mapped_column(Text, primary_key=True)
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime | None] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(Text)
    origin: Mapped[JsonObject] = mapped_column(JSONB)
    units: Mapped[int] = mapped_column(Integer)
    wafers: Mapped[int] = mapped_column(Integer)
    alarms: Mapped[JsonList] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    alarms_not_listed: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_seq: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    heartbeat_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]


class RunItemRow(Base):
    """One item of a run's materialised input (a sensor unit or a wafer), at its 0-based input
    position; `data` is the item's JSON, compressed, so one item is read without the rest."""

    __tablename__ = "run_items"
    __table_args__ = (CheckConstraint("kind IN ('unit', 'wafer')", name="kind"),)

    run_id: Mapped[str] = mapped_column(
        Text, ForeignKey("runs.run_id", ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(Text, primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class RunUnitChartRow(Base):
    """One unit's control-chart result of a run, at its 0-based input position: `chart` is the
    result without `z`, as compressed JSON; `z` the standardised readings of the monitored
    sensors as little-endian float32, NaN where missing (about 1.7 kB a unit)."""

    __tablename__ = "run_unit_charts"

    run_id: Mapped[str] = mapped_column(
        Text, ForeignKey("runs.run_id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    chart: Mapped[bytes] = mapped_column(LargeBinary)
    z: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


class RunStageRow(Base):
    """One stage of a run (``StageState``), kept apart so a large result is written once."""

    __tablename__ = "run_stages"

    run_id: Mapped[str] = mapped_column(
        Text, ForeignKey("runs.run_id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    stage: Mapped[str] = mapped_column(Text)
    state: Mapped[JsonObject] = mapped_column(JSONB)


class RunEventRow(Base):
    """One SSE event of a run; `seq` is monotonic per run, starting at 1."""

    __tablename__ = "run_events"

    run_id: Mapped[str] = mapped_column(
        Text, ForeignKey("runs.run_id", ondelete="CASCADE"), primary_key=True
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime]
    payload: Mapped[JsonObject] = mapped_column(JSONB)


class UploadRow(Base):
    """A parsed and validated file (``UploadSummary``) and its items, kept 24 h to be run."""

    __tablename__ = "uploads"
    __table_args__ = (CheckConstraint("kind IN ('sensors', 'wafers')", name="kind"),)

    upload_id: Mapped[str] = mapped_column(Text, primary_key=True)
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime] = mapped_column(index=True)
    kind: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(Text)
    runnable: Mapped[bool] = mapped_column(Boolean)
    summary: Mapped[JsonObject] = mapped_column(JSONB)
    items: Mapped[bytes] = mapped_column(LargeBinary)
    """gzip of the parsed items as a JSON array (sensor units or wafers)."""


# -- language-model layer -----------------------------------------------------------------------


class LlmCallRow(Base):
    """One model call attempt (``LlmCallRecord``); the Models page sums them per quota day."""

    __tablename__ = "llm_calls"
    __table_args__ = (Index("ix_llm_calls_started", "started_at", "call_id"),)

    call_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    started_at: Mapped[datetime]
    role: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    correlation_id: Mapped[str | None] = mapped_column(Text, index=True)
    record: Mapped[JsonObject] = mapped_column(JSONB)


class LlmResponseCacheRow(Base):
    """A complete answer keyed by the SHA-256 of the built request (``llm.cache``)."""

    __tablename__ = "llm_response_cache"

    cache_key: Mapped[str] = mapped_column(Text, primary_key=True)
    result: Mapped[JsonObject] = mapped_column(JSONB)
    created_at: Mapped[datetime]
    last_used_at: Mapped[datetime] = mapped_column(index=True)
    hits: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class LlmRoleAssignmentRow(Base):
    """The model chain an administrator chose for a role; roles without a row use the default."""

    __tablename__ = "llm_role_assignments"

    role: Mapped[str] = mapped_column(Text, primary_key=True)
    chain: Mapped[JsonList] = mapped_column(JSONB)
    updated_at: Mapped[datetime | None]
    updated_by: Mapped[str | None] = mapped_column(Text)


class ChatRouteRow(Base):
    """How one chat question was routed: by rules (deterministic) or by the router model."""

    __tablename__ = "chat_routes"
    __table_args__ = (CheckConstraint("kind IN ('deterministic', 'model')", name="kind"),)

    route_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    at: Mapped[datetime] = mapped_column(index=True)
    kind: Mapped[str] = mapped_column(Text)
    intent: Mapped[str] = mapped_column(Text)


class LlmEvaluationRow(Base):
    """One evaluation run of a model in a role (``EvaluationResult``)."""

    __tablename__ = "llm_evaluations"
    __table_args__ = (Index("ix_llm_evaluations_run", "run_at", "evaluation_id"),)

    evaluation_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    role: Mapped[str] = mapped_column(Text)
    model_id: Mapped[str] = mapped_column(Text)
    task_set: Mapped[str] = mapped_column(Text)
    run_at: Mapped[datetime]
    result: Mapped[JsonObject] = mapped_column(JSONB)


class KnowledgeChunkRow(Base):
    """A passage of an open-access source with its location; ``search`` is its English
    full-text vector, kept by PostgreSQL."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (Index("ix_knowledge_chunks_search", "search", postgresql_using="gin"),)

    chunk_id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_id: Mapped[str] = mapped_column(Text, index=True)
    source: Mapped[JsonObject] = mapped_column(JSONB)
    position: Mapped[int] = mapped_column(Integer)
    location: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    search: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english'::regconfig, text)", persisted=True)
    )
