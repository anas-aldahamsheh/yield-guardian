"""Investigations: the snapshot, the event log and the human decision.

Every change appends an event with the next `seq` of its investigation (1, 2, ...) and updates the
snapshot in the same transaction, then `pg_notify('yg_investigation_events', investigation_id)`
wakes the streams of every API process. The investigator itself runs in the job queue
(`yield_guardian.services.jobs`); this module only stores what it reports.
"""

import asyncio
import builtins
import contextlib
import re
import secrets
import time
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime
from typing import cast

import structlog
from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
from yield_guardian.contracts.services import InvalidArgumentError, NotFoundError
from yield_guardian.db.notify import EVENTS_CHANNEL, JOBS_CHANNEL, Notifier
from yield_guardian.db.tables import InvestigationEventRow, InvestigationJobRow, InvestigationRow
from yield_guardian.services import alarms, audit, cursors
from yield_guardian.services.errors import ConflictError
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
    raise InvalidArgumentError(f"{ref!r} is not a valid {trigger.kind} reference.")


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

    async def _apply(self, mutate: Callable[[InvestigationRow], None], make: EventFactory) -> None:
        async with self._sessionmaker() as db, db.begin():
            row = await _lock(db, self._id)
            mutate(row)
            await _append(db, row, make)

    async def status(self, status: InvestigationStatus) -> None:
        if self._resuming or status not in self._RUNNER_STATUSES:
            log.warning("runner_status_ignored", investigation_id=self._id, status=status)
            return
        async with self._sessionmaker() as db, db.begin():
            await _set_status(db, await _lock(db, self._id), status)

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
        self, trigger: InvestigationTrigger, *, session: ActiveSession
    ) -> Investigation:
        """Store a queued investigation and enqueue its run.

        An alarm that is already being investigated returns that investigation instead.
        """
        title = trigger_title(trigger)
        actor = audit.Actor.of(session)
        now = datetime.now(UTC)
        async with self._sessionmaker() as db, db.begin():
            if trigger.kind == "alarm":
                alarm = await alarms.lock(db, trigger.ref)
                if alarm.status == "investigating" and alarm.investigation_id is not None:
                    current = await db.get(InvestigationRow, alarm.investigation_id)
                    if current is not None and current.status not in TERMINAL:
                        return to_investigation(current)
            row = InvestigationRow(
                investigation_id=new_investigation_id(),
                title=title,
                status="queued",
                trigger_kind=trigger.kind,
                trigger_ref=trigger.ref,
                trigger_question=trigger.question,
                recorded=False,
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
            )
            db.add(row)
            await db.flush()
            await _append(
                db, row, lambda seq, at: StatusEvent(type="status", seq=seq, at=at, status="queued")
            )
            await self._enqueue(db, row.investigation_id, "run", {})
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

    async def get(self, investigation_id: str) -> Investigation:
        async with self._sessionmaker() as db:
            row = await db.get(InvestigationRow, investigation_id)
        if row is None:
            raise NotFoundError(f"Investigation {investigation_id} does not exist.")
        return to_investigation(row)

    async def list(
        self,
        *,
        status: InvestigationStatus | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> InvestigationPage:
        """Newest first; cursors carry the creation time and ID of the last item."""
        query = select(InvestigationRow)
        count = select(func.count()).select_from(InvestigationRow)
        if status is not None:
            query = query.where(InvestigationRow.status == status)
            count = count.where(InvestigationRow.status == status)
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
        query = query.order_by(
            InvestigationRow.created_at.desc(), InvestigationRow.investigation_id.desc()
        ).limit(limit + 1)
        async with self._sessionmaker() as db:
            rows = list((await db.scalars(query)).all())
            total = (await db.scalar(count)) or 0
        more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = (
            cursors.encode(CURSOR_KIND, rows[-1].created_at.isoformat(), rows[-1].investigation_id)
            if more
            else None
        )
        return InvestigationPage(
            items=[to_summary(row) for row in rows], next_cursor=next_cursor, total=total
        )

    async def for_unit(self, unit_id: int) -> builtins.list[str]:
        """IDs of the investigations about one unit or one of its alarms, newest first."""
        unit = InvestigationRow.trigger_ref.regexp_match(f"^0*{unit_id}$")
        alarm = InvestigationRow.trigger_ref.regexp_match(f"^AL-0*{unit_id}-")
        query = (
            select(InvestigationRow.investigation_id)
            .where(
                ((InvestigationRow.trigger_kind == "unit") & unit)
                | ((InvestigationRow.trigger_kind == "alarm") & alarm)
            )
            .order_by(InvestigationRow.created_at.desc(), InvestigationRow.investigation_id.desc())
        )
        async with self._sessionmaker() as db:
            return builtins.list((await db.scalars(query)).all())

    async def get_evidence(self, investigation_id: str, evidence_id: str) -> Evidence:
        investigation = await self.get(investigation_id)
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
        """Record the decision and enqueue the resume; the job then opens the work order."""
        actor = audit.Actor.of(session)
        async with self._sessionmaker() as db, db.begin():
            row = await _lock(db, investigation_id)
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
