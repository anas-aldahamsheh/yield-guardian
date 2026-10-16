"""Investigations: the snapshot, the event log and the human decision.

Every change appends an event with the next `seq` of its investigation (1, 2, ...) and updates the
snapshot in the same transaction, then `pg_notify('yg_investigation_events', investigation_id)`
wakes the streams of every API process. The investigator itself runs in the job queue
(`yield_guardian.services.jobs`); this module only stores what it reports.
"""

import asyncio
import builtins
import contextlib
import dataclasses
import re
import secrets
import time
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime
from typing import cast

import structlog
from sqlalchemy import func, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from yield_guardian.agent.run_results import find_alarm, parse_run_alarm_ref
from yield_guardian.contracts.base import Problem
from yield_guardian.contracts.investigation import (
    Decision,
    DecisionCreate,
    DecisionEvent,
    EndEvent,
    ErrorEvent,
    Evidence,
    EvidenceEvent,
    Investigation,
    InvestigationEvent,
    InvestigationEventPayload,
    InvestigationPage,
    InvestigationStatus,
    InvestigationStep,
    InvestigationSummary,
    InvestigationTrigger,
    Report,
    ReportEvent,
    RoleModel,
    StatusEvent,
    StepEvent,
    Verification,
    VerificationEvent,
)
from yield_guardian.contracts.models import Usage
from yield_guardian.contracts.runs import RunAlarm
from yield_guardian.contracts.services import InvalidArgumentError, NotFoundError, NotReadyError
from yield_guardian.db.notify import EVENTS_CHANNEL, JOBS_CHANNEL, Notifier
from yield_guardian.db.tables import InvestigationEventRow, InvestigationJobRow, InvestigationRow
from yield_guardian.live.protocols import RunReader
from yield_guardian.services import alarms, audit, cursors
from yield_guardian.services.access import Viewer, current_viewer, examples, is_example, owned
from yield_guardian.services.errors import ConflictError, ReadOnlyError
from yield_guardian.services.protocols import ActiveSession
from yield_guardian.services.workorders import open_work_order

log = structlog.get_logger(__name__)

CURSOR_KIND = "inv"
TERMINAL: frozenset[str] = frozenset({"approved", "rejected", "failed"})
STREAM_POLL_S = 10.0

_CROCKFORD = "0123456789abcdefghjkmnpqrstvwxyz"
_ALARM_REF = re.compile(r"^AL-(\d+)-(risk|t2|spe|ewma|cusum)$")
_UNIT_REF = re.compile(r"^\d+$")
_WAFER_REF = re.compile(r"^[A-Za-z0-9_.]{1,64}-\d+$")
_LOT_REF = re.compile(r"^[A-Za-z0-9_.]{1,64}$")
_ALARM_TITLES = {
    "risk": "Failure-risk alarm",
    "t2": "T² alarm",
    "spe": "SPE alarm",
    "ewma": "EWMA alarm",
    "cusum": "CUSUM alarm",
}

INTERRUPTED = Problem(
    title="Investigation interrupted",
    status=500,
    code="internal_error",
    detail="The server stopped while the investigator was running. Start a new investigation.",
)
NO_REPORT = Problem(
    title="Investigation incomplete",
    status=500,
    code="internal_error",
    detail="The investigator stopped before its report was ready for a decision.",
)

STOPPED = Problem(
    title="Stopped by the user",
    status=409,
    code="conflict",
    detail="The investigation was stopped before its report was written. Its evidence so far "
    "is kept.",
)
STOPPABLE: frozenset[str] = frozenset({"queued", "running"})

EventFactory = Callable[[int, datetime], InvestigationEventPayload]
EventBatch = list[InvestigationEventPayload]


def new_investigation_id() -> str:
    """`inv_` and a lowercase ULID: 48-bit millisecond time and 80 random bits, sortable by time."""
    value = (time.time_ns() // 1_000_000) << 80 | secrets.randbits(80)
    chars = [_CROCKFORD[(value >> shift) & 31] for shift in range(125, -1, -5)]
    return "inv_" + "".join(chars)


def trigger_title(trigger: InvestigationTrigger) -> str:
    """The title written by code; InvalidArgumentError when `ref` does not fit `kind`."""
    ref = trigger.ref
    if trigger.kind == "alarm" and (match := _ALARM_REF.match(ref)):
        return f"{_ALARM_TITLES[match.group(2)]} on unit {match.group(1)}"
    if trigger.kind == "unit" and _UNIT_REF.match(ref):
        return f"Unit {int(ref)}"
    if trigger.kind == "wafer" and _WAFER_REF.match(ref):
        return f"Wafer {ref}"
    if trigger.kind == "lot" and _LOT_REF.match(ref):
        return f"Lot {ref}"
    if trigger.kind == "run_alarm" and (parsed := parse_run_alarm_ref(ref)):
        return f"Run alarm {parsed[1]} in {parsed[0]}"
    raise InvalidArgumentError(f"{ref!r} is not a valid {trigger.kind} reference.")


def run_alarm_title(alarm: RunAlarm) -> str:
    """A run alarm's investigation title, from the alarm's own code-written title."""
    if alarm.unit_index is not None:
        item = f"unit {alarm.unit_id or alarm.unit_index}"
    elif alarm.wafer_index is not None:
        item = f"wafer {alarm.wafer_index}" + (f" of lot {alarm.lot}" if alarm.lot else "")
    elif alarm.lot is not None:
        item = f"lot {alarm.lot}"
    else:
        item = "the run"
    return f"{alarm.title} on {item} ({alarm.alarm_id})"


async def check_run_alarm(reader: RunReader | None, trigger: InvestigationTrigger) -> str:
    """For a ``run_alarm`` trigger: the run and the alarm must exist; returns the title.
    NotReadyError without a run store, NotFoundError for an unknown run or alarm."""
    trigger_title(trigger)
    parsed = parse_run_alarm_ref(trigger.ref)
    if parsed is None:  # trigger_title has refused it already
        raise InvalidArgumentError(f"{trigger.ref!r} is not a valid run_alarm reference.")
    if reader is None:
        raise NotReadyError("The run store is not available yet.")
    run_id, alarm_id = parsed
    run = await reader.get_run(run_id)
    if run is None:
        raise NotFoundError(f"Run {run_id} does not exist or has expired.")
    alarm = find_alarm(run, alarm_id)
    if alarm is None:
        raise NotFoundError(f"Run {run_id} has no alarm {alarm_id}.")
    return run_alarm_title(alarm)


def _trigger(row: InvestigationRow) -> InvestigationTrigger:
    return InvestigationTrigger.model_validate(
        {"kind": row.trigger_kind, "ref": row.trigger_ref, "question": row.trigger_question}
    )


def _summary_fields(row: InvestigationRow) -> dict[str, object]:
    return {
        "investigation_id": row.investigation_id,
        "title": row.title,
        "status": row.status,
        "trigger": _trigger(row),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "recorded": row.recorded,
        "models": row.models,
        "usage": row.usage,
        "work_order_id": row.work_order_id,
    }


def to_summary(row: InvestigationRow) -> InvestigationSummary:
    return InvestigationSummary.model_validate(_summary_fields(row))


def to_investigation(row: InvestigationRow) -> Investigation:
    return Investigation.model_validate(
        {
            **_summary_fields(row),
            "steps": row.steps,
            "evidence": row.evidence,
            "report": row.report,
            "verification": row.verification,
            "decision": row.decision,
            "error": row.error,
        }
    )


def _usage(steps: list[InvestigationStep]) -> tuple[list[RoleModel], Usage | None]:
    """Models and usage over the model calls of the steps; cached answers are not requests."""
    calls = [call for step in steps for call in step.llm]
    if not calls:
        return [], None
    models = list(dict.fromkeys((call.role, call.model_id) for call in calls))
    cache_hits = sum(call.cached for call in calls)
    known = [call for call in calls if call.tokens_in is not None and call.tokens_out is not None]
    unknown_sent = sum(
        1
        for call in calls
        if not call.cached and (call.tokens_in is None or call.tokens_out is None)
    )
    return [RoleModel(role=role, model_id=model) for role, model in models], Usage(
        requests=len(calls) - cache_hits,
        tokens_in=sum(call.tokens_in or 0 for call in known),
        tokens_out=sum(call.tokens_out or 0 for call in known),
        tokens_reasoning=sum(call.tokens_reasoning or 0 for call in known),
        points=sum(call.points or 0.0 for call in known),
        cache_hits=cache_hits,
        requests_without_usage=unknown_sent,
    )


async def _lock(db: AsyncSession, investigation_id: str) -> InvestigationRow:
    row = await db.scalar(
        select(InvestigationRow)
        .where(InvestigationRow.investigation_id == investigation_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise NotFoundError(f"Investigation {investigation_id} does not exist.")
    return row


async def _append(db: AsyncSession, row: InvestigationRow, make: EventFactory) -> None:
    """Append the next event of a locked investigation and wake its streams after commit."""
    row.last_seq += 1
    at = datetime.now(UTC)
    event = make(row.last_seq, at)
    row.updated_at = at
    db.add(
        InvestigationEventRow(
            investigation_id=row.investigation_id,
            seq=row.last_seq,
            type=event.type,
            at=at,
            payload=event.model_dump(mode="json"),
        )
    )
    await db.execute(select(func.pg_notify(EVENTS_CHANNEL, row.investigation_id)))


async def _set_status(db: AsyncSession, row: InvestigationRow, status: InvestigationStatus) -> None:
    if row.status == status:
        return
    row.status = status
    await _append(
        db, row, lambda seq, at: StatusEvent(type="status", seq=seq, at=at, status=status)
    )


async def _end(db: AsyncSession, row: InvestigationRow) -> None:
    status = cast(InvestigationStatus, row.status)
    await _append(db, row, lambda seq, at: EndEvent(type="end", seq=seq, at=at, status=status))


async def _reopen_alarm(db: AsyncSession, row: InvestigationRow) -> None:
    if row.trigger_kind != "alarm":
        return
    alarm = await alarms.lock(db, row.trigger_ref)
    if alarm.investigation_id == row.investigation_id:
        await alarms.set_state(db, row.trigger_ref, "open", None)


async def close_run_in(db: AsyncSession, investigation_id: str, problem: Problem) -> None:
    """Close a run in the caller's transaction, once, whatever stopped it.

    A run that reached the decision or failed gets its end event; an unfinished one is failed
    with `problem` (error, status and end events) and its alarm reopens.
    """
    row = await _lock(db, investigation_id)
    if row.status in ("approved", "rejected"):
        return
    if row.status in ("awaiting_decision", "failed"):
        last = await db.scalar(
            select(InvestigationEventRow.type).where(
                InvestigationEventRow.investigation_id == investigation_id,
                InvestigationEventRow.seq == row.last_seq,
            )
        )
        if last != "end":
            await _end(db, row)
        if row.status == "failed":
            await _reopen_alarm(db, row)
        return
    row.error = problem.model_dump(mode="json")
    await _append(
        db, row, lambda seq, at: ErrorEvent(type="error", seq=seq, at=at, problem=problem)
    )
    await _set_status(db, row, "failed")
    await _end(db, row)
    await _reopen_alarm(db, row)


class StoreSink:
    """The InvestigationSink the runner reports to: each call is one stored, streamed event.

    While resuming, status changes are ignored: the API sets the final status after the decision.
    """

    _RUNNER_STATUSES = frozenset({"running", "awaiting_decision", "failed"})

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        investigation_id: str,
        *,
        resuming: bool = False,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._id = investigation_id
        self._resuming = resuming

    async def _open(self, db: AsyncSession) -> InvestigationRow:
        """The locked row, while the investigation is not closed: a run stopped by the user or
        closed by the queue (timed out, interrupted) takes no more writes from its runner, so a
        late write can never overwrite the final status (ConflictError ends the runner)."""
        row = await _lock(db, self._id)
        if row.status in TERMINAL:
            log.warning("runner_write_after_close", investigation_id=self._id, status=row.status)
            raise ConflictError(f"Investigation {self._id} is closed ({row.status}).")
        return row

    async def _apply(self, mutate: Callable[[InvestigationRow], None], make: EventFactory) -> None:
        async with self._sessionmaker() as db, db.begin():
            row = await self._open(db)
            mutate(row)
            await _append(db, row, make)

    async def status(self, status: InvestigationStatus) -> None:
        if self._resuming or status not in self._RUNNER_STATUSES:
            log.warning("runner_status_ignored", investigation_id=self._id, status=status)
            return
        async with self._sessionmaker() as db, db.begin():
            await _set_status(db, await self._open(db), status)

    async def step(self, step: InvestigationStep) -> None:
        def mutate(row: InvestigationRow) -> None:
            steps = [InvestigationStep.model_validate(s) for s in row.steps]
            steps = [s for s in steps if s.index != step.index] + [step]
            steps.sort(key=lambda s: s.index)
            models, usage = _usage(steps)
            row.steps = [s.model_dump(mode="json") for s in steps]
            row.models = [m.model_dump(mode="json") for m in models]
            row.usage = usage.model_dump(mode="json") if usage else None

        await self._apply(mutate, lambda seq, at: StepEvent(type="step", seq=seq, at=at, step=step))

    async def evidence(self, evidence: Evidence) -> None:
        def mutate(row: InvestigationRow) -> None:
            kept = [e for e in row.evidence if e.get("evidence_id") != evidence.evidence_id]
            row.evidence = [*kept, evidence.model_dump(mode="json")]

        await self._apply(
            mutate,
            lambda seq, at: EvidenceEvent(type="evidence", seq=seq, at=at, evidence=evidence),
        )

    async def report(self, report: Report, *, round: int) -> None:
        def mutate(row: InvestigationRow) -> None:
            row.report = report.model_dump(mode="json")

        await self._apply(
            mutate,
            lambda seq, at: ReportEvent(type="report", seq=seq, at=at, round=round, report=report),
        )

    async def verification(self, verification: Verification, *, round: int) -> None:
        def mutate(row: InvestigationRow) -> None:
            row.verification = verification.model_dump(mode="json")

        await self._apply(
            mutate,
            lambda seq, at: VerificationEvent(
                type="verification", seq=seq, at=at, round=round, verification=verification
            ),
        )

    async def error(self, problem: Problem) -> None:
        def mutate(row: InvestigationRow) -> None:
            row.error = problem.model_dump(mode="json")

        await self._apply(
            mutate, lambda seq, at: ErrorEvent(type="error", seq=seq, at=at, problem=problem)
        )


class DbInvestigationStore:
    def __init__(
        self, sessionmaker: async_sessionmaker[AsyncSession], notifier: Notifier | None = None
    ) -> None:
        self._sessionmaker = sessionmaker
        self._notifier = notifier

    def sink(self, investigation_id: str, *, resuming: bool = False) -> StoreSink:
        return StoreSink(self._sessionmaker, investigation_id, resuming=resuming)

    async def create(
        self, trigger: InvestigationTrigger, *, session: ActiveSession, title: str | None = None
    ) -> Investigation:
        """Store a queued investigation and enqueue its run; ``title`` replaces the one
        :func:`trigger_title` writes (a run alarm's title read from the run).

        An alarm or run alarm this workspace is already investigating returns that
        investigation instead; another workspace's investigation of it is never returned.
        """
        return await self._create(
            trigger,
            audit.Actor.of(session),
            recorded=False,
            title=title,
            workspace_id=session.workspace_id,
        )

    async def create_recorded(
        self, trigger: InvestigationTrigger, *, actor: audit.Actor, as_of: int
    ) -> Investigation:
        """As :meth:`create`, for a run made once to be kept and shown as recorded
        (``scripts/record_investigations.py``); it runs through the same job queue, with its
        tools reading the line as of position ``as_of`` (the alarm's sequence)."""
        return await self._create(trigger, actor, recorded=True, as_of=as_of)

    async def _create(
        self,
        trigger: InvestigationTrigger,
        actor: audit.Actor,
        *,
        recorded: bool,
        as_of: int | None = None,
        title: str | None = None,
        workspace_id: str | None = None,
    ) -> Investigation:
        default_title = trigger_title(trigger)  # also refuses a reference that does not fit
        title = title or default_title
        now = datetime.now(UTC)
        owner = uuid.UUID(workspace_id) if workspace_id else None
        async with self._sessionmaker() as db, db.begin():
            if trigger.kind in ("alarm", "run_alarm"):
                # One transaction at a time per alarm: the SECOM alarm's state row, or (run
                # alarms live in the run store) an advisory lock on its reference.
                if trigger.kind == "alarm":
                    await alarms.lock(db, trigger.ref)
                else:
                    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(trigger.ref))))
                # Only this workspace's own: another's is never given away.
                current = await db.scalar(
                    select(InvestigationRow)
                    .where(
                        InvestigationRow.trigger_kind == trigger.kind,
                        InvestigationRow.trigger_ref == trigger.ref,
                        InvestigationRow.status.not_in(TERMINAL),
                        InvestigationRow.workspace_id.is_not_distinct_from(owner),
                    )
                    .order_by(InvestigationRow.created_at.desc())
                    .limit(1)
                )
                if current is not None:
                    return to_investigation(current)
            row = InvestigationRow(
                investigation_id=new_investigation_id(),
                title=title,
                status="queued",
                trigger_kind=trigger.kind,
                trigger_ref=trigger.ref,
                trigger_question=trigger.question,
                recorded=recorded,
                created_by=actor.label,
                created_at=now,
                updated_at=now,
                last_seq=0,
                steps=[],
                evidence=[],
                models=[],
                usage=None,
                report=None,
                verification=None,
                decision=None,
                error=None,
                work_order_id=None,
                workspace_id=owner,
            )
            db.add(row)
            await db.flush()
            await _append(
                db, row, lambda seq, at: StatusEvent(type="status", seq=seq, at=at, status="queued")
            )
            payload: dict[str, object] = {} if as_of is None else {"as_of": as_of}
            await self._enqueue(db, row.investigation_id, "run", payload)
            if trigger.kind == "alarm":
                await alarms.set_state(db, trigger.ref, "investigating", row.investigation_id)
            audit.record(
                db,
                actor,
                "investigation.created",
                "investigation",
                row.investigation_id,
                {"trigger": trigger.model_dump(mode="json")},
            )
        return to_investigation(row)

    async def get(self, investigation_id: str, viewer: Viewer | None = None) -> Investigation:
        """The investigation; NotFoundError when it does not exist or belongs to a workspace
        other than `viewer`'s (None: any)."""
        async with self._sessionmaker() as db:
            row = await db.get(InvestigationRow, investigation_id)
        if row is None or (viewer is not None and not viewer.sees(row.workspace_id)):
            raise NotFoundError(f"Investigation {investigation_id} does not exist.")
        return to_investigation(row)

    async def workspace_of(self, investigation_id: str) -> str | None:
        """The workspace the investigation belongs to (None for none, or no such one)."""
        async with self._sessionmaker() as db:
            owner = await db.scalar(
                select(InvestigationRow.workspace_id).where(
                    InvestigationRow.investigation_id == investigation_id
                )
            )
        return str(owner) if owner is not None else None

    async def list(
        self,
        *,
        status: InvestigationStatus | None = None,
        cursor: str | None = None,
        limit: int = 50,
        viewer: Viewer | None = None,
    ) -> InvestigationPage:
        """Newest first; cursors carry the creation time and ID of the last item. With a
        `viewer`, `items` are that workspace's own (none without a session), and the first page
        carries the product's examples apart, in `examples`, for every viewer; any other
        investigation of no workspace is listed nowhere."""
        query = select(InvestigationRow)
        count = select(func.count()).select_from(InvestigationRow)
        apart = None  # the examples, on the first page
        if viewer is not None:
            query = query.where(owned(InvestigationRow.workspace_id, viewer))
            count = count.where(owned(InvestigationRow.workspace_id, viewer))
            if cursor is None:
                apart = select(InvestigationRow).where(examples())
        if status is not None:
            query = query.where(InvestigationRow.status == status)
            count = count.where(InvestigationRow.status == status)
            apart = apart.where(InvestigationRow.status == status) if apart is not None else None
        if cursor is not None:
            created, last_id = cursors.decode(CURSOR_KIND, cursor, str, str)
            try:
                created_at = datetime.fromisoformat(str(created))
            except ValueError as exc:
                raise InvalidArgumentError("The cursor is not valid.") from exc
            if created_at.tzinfo is None:
                raise InvalidArgumentError("The cursor is not valid.")
            query = query.where(
                tuple_(InvestigationRow.created_at, InvestigationRow.investigation_id)
                < tuple_(created_at, last_id)
            )
        newest = (InvestigationRow.created_at.desc(), InvestigationRow.investigation_id.desc())
        query = query.order_by(*newest).limit(limit + 1)
        async with self._sessionmaker() as db:
            rows = list((await db.scalars(query)).all())
            total = (await db.scalar(count)) or 0
            example_rows = (
                list((await db.scalars(apart.order_by(*newest).limit(limit))).all())
                if apart is not None
                else []
            )
        more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = (
            cursors.encode(CURSOR_KIND, rows[-1].created_at.isoformat(), rows[-1].investigation_id)
            if more
            else None
        )
        return InvestigationPage(
            items=[to_summary(row) for row in rows],
            examples=[to_summary(row) for row in example_rows],
            next_cursor=next_cursor,
            total=total,
        )

    async def for_unit(self, unit_id: int) -> builtins.list[str]:
        """IDs of the investigations about one unit or one of its alarms, newest first: those
        of the workspace the current request or job acts for (none when it acts for none)."""
        viewer = current_viewer()
        if viewer is None:
            return []
        unit = InvestigationRow.trigger_ref.regexp_match(f"^0*{unit_id}$")
        alarm = InvestigationRow.trigger_ref.regexp_match(f"^AL-0*{unit_id}-")
        query = (
            select(InvestigationRow.investigation_id)
            .where(
                ((InvestigationRow.trigger_kind == "unit") & unit)
                | ((InvestigationRow.trigger_kind == "alarm") & alarm),
                owned(InvestigationRow.workspace_id, viewer),
            )
            .order_by(InvestigationRow.created_at.desc(), InvestigationRow.investigation_id.desc())
        )
        async with self._sessionmaker() as db:
            return builtins.list((await db.scalars(query)).all())

    async def for_run(self, run_id: str) -> dict[str, str]:
        """Alarm ID to the newest investigation of that alarm, for one run's alarms (the run
        store fills ``RunAlarm.investigation_id`` from it)."""
        query = (
            select(InvestigationRow.trigger_ref, InvestigationRow.investigation_id)
            .where(
                InvestigationRow.trigger_kind == "run_alarm",
                InvestigationRow.trigger_ref.startswith(f"{run_id}:", autoescape=True),
            )
            .order_by(InvestigationRow.created_at, InvestigationRow.investigation_id)
        )
        async with self._sessionmaker() as db:
            rows = (await db.execute(query)).all()
        return {ref.split(":", 1)[1]: investigation_id for ref, investigation_id in rows}

    async def get_evidence(
        self, investigation_id: str, evidence_id: str, viewer: Viewer | None = None
    ) -> Evidence:
        investigation = await self.get(investigation_id, viewer)
        for evidence in investigation.evidence:
            if evidence.evidence_id == evidence_id:
                return evidence
        raise NotFoundError(f"Evidence {evidence_id} is not part of {investigation_id}.")

    async def events(
        self, investigation_id: str, *, after_seq: int | None = None
    ) -> AsyncIterator[InvestigationEventPayload]:
        """Stored events after `after_seq`, then live ones; ends after an `end` event that is the
        latest one, or at once when nothing follows `after_seq` of a finished investigation."""
        last = after_seq or 0
        with self._subscribe(investigation_id) as wake:
            batch, status = await self._events_after(investigation_id, last)
            if not batch and status in TERMINAL:
                return
            while True:
                for event in batch:
                    yield event
                if batch:
                    last = batch[-1].seq
                    if batch[-1].type == "end":
                        return
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(wake.wait(), STREAM_POLL_S)
                wake.clear()
                batch, _ = await self._events_after(investigation_id, last)

    async def decide(
        self, investigation_id: str, decision: DecisionCreate, *, session: ActiveSession
    ) -> Investigation:
        """Record the decision and enqueue the resume; the job then opens the work order.
        ReadOnlyError for the product's example, which nobody decides."""
        actor = audit.Actor.of(session)
        async with self._sessionmaker() as db, db.begin():
            row = await _lock(db, investigation_id)
            if not session.viewer.sees(row.workspace_id):
                raise NotFoundError(f"Investigation {investigation_id} does not exist.")
            if is_example(row.recorded, row.workspace_id):
                raise ReadOnlyError(
                    f"Investigation {investigation_id} is the recorded example every visitor "
                    "sees, so nobody decides it. Start an investigation of your own to decide one."
                )
            if row.status != "awaiting_decision" or row.decision is not None:
                raise ConflictError(
                    f"Investigation {investigation_id} is not waiting for a decision."
                )
            report = Report.model_validate(row.report) if row.report is not None else None
            available = len(report.actions) if report is not None else 0
            if decision.verdict == "reject":
                if decision.actions:
                    raise InvalidArgumentError("A rejection approves no actions.")
                indexes: list[int] = []
            elif decision.actions is None:
                indexes = list(range(available))
            else:
                indexes = decision.actions
                if len(set(indexes)) != len(indexes) or any(i >= available for i in indexes):
                    raise InvalidArgumentError(
                        f"Action indexes must be distinct and below {available}."
                    )
            row.decision = Decision(
                verdict=decision.verdict,
                actions=indexes,
                note=decision.note,
                decided_by=actor.label,
                decided_at=datetime.now(UTC),
            ).model_dump(mode="json")
            row.updated_at = datetime.now(UTC)
            await self._enqueue(
                db, investigation_id, "resume", {"actor_role": actor.role, "actor_name": actor.name}
            )
        return to_investigation(row)

    async def stop(self, investigation_id: str, *, session: ActiveSession) -> Investigation:
        """Stop a queued or running investigation: it is failed with :data:`STOPPED` (its
        evidence is kept, no report is written), its run job is closed so no worker starts or
        keeps it, and every worker is woken to cancel its runner. ConflictError when it is not
        queued or running; ReadOnlyError for the product's example."""
        actor = audit.Actor.of(session)
        async with self._sessionmaker() as db, db.begin():
            row = await _lock(db, investigation_id)
            if not session.viewer.sees(row.workspace_id):
                raise NotFoundError(f"Investigation {investigation_id} does not exist.")
            if is_example(row.recorded, row.workspace_id):
                raise ReadOnlyError(
                    f"Investigation {investigation_id} is the recorded example every visitor "
                    "sees, so nobody stops it."
                )
            if row.status not in STOPPABLE:
                raise ConflictError(
                    f"Investigation {investigation_id} is not running (it is {row.status}), "
                    "so there is nothing to stop."
                )
            row.error = STOPPED.model_dump(mode="json")
            await _append(
                db, row, lambda seq, at: ErrorEvent(type="error", seq=seq, at=at, problem=STOPPED)
            )
            await _set_status(db, row, "failed")
            await _end(db, row)
            await _reopen_alarm(db, row)
            await db.execute(
                update(InvestigationJobRow)
                .where(
                    InvestigationJobRow.investigation_id == investigation_id,
                    InvestigationJobRow.kind == "run",
                    InvestigationJobRow.status.in_(("queued", "running")),
                )
                .values(status="failed", error="stopped", finished_at=func.now())
            )
            audit.record(db, actor, "investigation.stopped", "investigation", investigation_id)
            await db.execute(select(func.pg_notify(JOBS_CHANNEL, investigation_id)))
        return to_investigation(row)

    async def closed(self, investigation_ids: builtins.list[str]) -> builtins.list[str]:
        """Those of `investigation_ids` that are closed (finished, failed or stopped)."""
        if not investigation_ids:
            return []
        async with self._sessionmaker() as db:
            return builtins.list(
                (
                    await db.scalars(
                        select(InvestigationRow.investigation_id).where(
                            InvestigationRow.investigation_id.in_(investigation_ids),
                            InvestigationRow.status.in_(TERMINAL),
                        )
                    )
                ).all()
            )

    async def trigger(self, investigation_id: str) -> InvestigationTrigger:
        async with self._sessionmaker() as db:
            row = await db.get(InvestigationRow, investigation_id)
        if row is None:
            raise NotFoundError(f"Investigation {investigation_id} does not exist.")
        return _trigger(row)

    async def decision(self, investigation_id: str) -> Decision:
        async with self._sessionmaker() as db:
            row = await db.get(InvestigationRow, investigation_id)
        if row is None or row.decision is None:
            raise NotFoundError(f"Investigation {investigation_id} has no decision.")
        return Decision.model_validate(row.decision)

    async def mark_running(self, investigation_id: str) -> None:
        async with self._sessionmaker() as db, db.begin():
            row = await _lock(db, investigation_id)
            if row.status == "queued":
                await _set_status(db, row, "running")

    async def close_run(self, investigation_id: str, problem: Problem = NO_REPORT) -> None:
        """See `close_run_in`; `problem` explains a run that stopped unfinished."""
        async with self._sessionmaker() as db, db.begin():
            await close_run_in(db, investigation_id, problem)

    async def finalize(self, investigation_id: str, actor: audit.Actor) -> None:
        """After the resume: work order, audit entry, decision, final status and end; idempotent."""
        async with self._sessionmaker() as db, db.begin():
            row = await _lock(db, investigation_id)
            if row.status != "awaiting_decision" or row.decision is None:
                return
            # The work order and the audit entries belong to the investigation's workspace.
            actor = dataclasses.replace(
                actor, workspace_id=str(row.workspace_id) if row.workspace_id else None
            )
            decision = Decision.model_validate(row.decision)
            work_order_id: str | None = None
            if decision.verdict == "approve" and decision.actions and row.report is not None:
                report = Report.model_validate(row.report)
                work_order_id = await open_work_order(
                    db,
                    investigation_id=investigation_id,
                    title=row.title,
                    actions=[report.actions[i] for i in decision.actions],
                    note=decision.note,
                    actor=actor,
                )
                row.work_order_id = work_order_id
            status: InvestigationStatus = (
                "approved" if decision.verdict == "approve" else "rejected"
            )
            audit.record(
                db,
                actor,
                "investigation.approved" if status == "approved" else "investigation.rejected",
                "investigation",
                investigation_id,
                {"actions": list(decision.actions), "work_order_id": work_order_id},
            )
            await _append(
                db,
                row,
                lambda seq, at: DecisionEvent(
                    type="decision", seq=seq, at=at, decision=decision, work_order_id=work_order_id
                ),
            )
            await _set_status(db, row, status)
            await _end(db, row)
            if row.trigger_kind == "alarm":
                await alarms.set_state(db, row.trigger_ref, "closed", investigation_id)

    @staticmethod
    async def _enqueue(
        db: AsyncSession, investigation_id: str, kind: str, payload: dict[str, object]
    ) -> None:
        db.add(
            InvestigationJobRow(
                investigation_id=investigation_id,
                kind=kind,
                payload=payload,
                status="queued",
                attempts=0,
                created_at=datetime.now(UTC),
            )
        )
        await db.flush()
        await db.execute(select(func.pg_notify(JOBS_CHANNEL, investigation_id)))

    @contextlib.contextmanager
    def _subscribe(self, investigation_id: str) -> Iterator[asyncio.Event]:
        if self._notifier is None:
            yield asyncio.Event()
            return
        with self._notifier.subscribe(EVENTS_CHANNEL, investigation_id) as wake:
            yield wake

    async def _events_after(self, investigation_id: str, after: int) -> tuple[EventBatch, str]:
        async with self._sessionmaker() as db:
            status = await db.scalar(
                select(InvestigationRow.status).where(
                    InvestigationRow.investigation_id == investigation_id
                )
            )
            if status is None:
                raise NotFoundError(f"Investigation {investigation_id} does not exist.")
            payloads = (
                await db.scalars(
                    select(InvestigationEventRow.payload)
                    .where(
                        InvestigationEventRow.investigation_id == investigation_id,
                        InvestigationEventRow.seq > after,
                    )
                    .order_by(InvestigationEventRow.seq)
                )
            ).all()
        return [InvestigationEvent.model_validate(p).root for p in payloads], status
