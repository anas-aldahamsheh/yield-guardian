"""Live runs and uploads in PostgreSQL (PLAN_V2 §3.3).

A run row holds the origin, the alarms and the sequence counter. Each item of the materialised
input (a sensor unit or a wafer) is a compressed row of ``run_items`` at its input position, so
one item is read without the rest (``RunReader``); each stage is a row of ``run_stages``, so a
large result is written once. The control-chart stage keeps ``z`` (every monitored sensor's
standardised reading) for the first ``Z_IN_RESULT`` units only; each unit's full chart is a row
of ``run_unit_charts`` with ``z`` as float32 bytes, read one unit at a time. Every change appends an event with the next ``seq`` of its run in
the same transaction, then ``pg_notify('yg_run_events', run_id)`` wakes the streams of every API
process.

A run or upload of a workspace belongs to it: another workspace gets exactly what a missing ID
gets (:mod:`yield_guardian.services.access`), and it is kept as long as the workspace, which ends
``workspace_life`` (30 days) after it was last used and takes its runs and uploads with it; its
``expires_at`` is null and reads as that moving date. A run or upload with no workspace (an API
client without a session) expires 24 hours after creation. Such a run an investigation uses
(trigger ref ``<run_id>:<alarm_id>``) is kept: starting the investigation sets its
``expires_at`` to null (:func:`retain_in`), and the prune also skips any run an investigation
references (:func:`used_by_investigation`). A run whose process stopped (no heartbeat) is failed
by any process, so its stream ends.
"""

import asyncio
import base64
import binascii
import contextlib
import gzip
import math
import secrets
import time
import uuid
import zlib
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol, cast, get_args

import numpy as np
import structlog
from pydantic import Field
from sqlalchemy import ColumnElement, delete, exists, func, insert, literal, select, update
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import InstrumentedAttribute

from yield_guardian.contracts.base import Contract, Problem
from yield_guardian.contracts.investigation import InvestigationStatus
from yield_guardian.contracts.runs import (
    STAGE_STATION,
    Run,
    RunAlarm,
    RunDoneEvent,
    RunEvent,
    RunEventPayload,
    RunOrigin,
    RunStartedEvent,
    RunStatus,
    SensorUnitInput,
    StageFailedEvent,
    StageId,
    StageSkippedEvent,
    StageState,
    UnitChartResult,
    UploadKind,
    UploadSummary,
    WaferInput,
)
from yield_guardian.contracts.services import NotFoundError, ServiceError
from yield_guardian.db.notify import RUN_EVENTS_CHANNEL, Notifier
from yield_guardian.db.tables import (
    InvestigationRow,
    RunEventRow,
    RunItemRow,
    RunRow,
    RunStageRow,
    RunUnitChartRow,
    UploadRow,
    WorkspaceRow,
)
from yield_guardian.services.access import NOBODY, Viewer, current_viewer, visible

log = structlog.get_logger(__name__)

RUN_TTL = timedelta(hours=24)
WORKSPACE_LIFE = timedelta(days=30)
"""A workspace's runs and uploads go with it, this long after it was last used (the default of
``workspace_session_days``)."""
STREAM_POLL_S = 10.0
STAGES: tuple[StageId, ...] = get_args(StageId)
Z_IN_RESULT = 200
"""Units whose standardised readings ride on the control-chart result (event and GET)."""
TERMINAL: frozenset[str] = frozenset({"done", "failed"})
_CROCKFORD = "0123456789abcdefghjkmnpqrstvwxyz"

INTERRUPTED = Problem(
    title="Run interrupted",
    status=500,
    code="internal_error",
    detail="The server stopped while this stage was computing. Start the run again.",
)
STOPPED_BEFORE = "The run stopped before this stage could start."

EventFactory = Callable[[int, datetime], RunEventPayload]


class GoneError(ServiceError):
    """The run or upload existed and has expired."""

    code = "gone"
    status = 410
    title = "Expired"


class InputError(ServiceError):
    """The submission cannot run as it is (too large, a bad map, nothing chosen): 422 with what
    to change, before any run is created."""

    code = "validation_error"
    status = 422
    title = "Input cannot run"


class RunInput(Contract):
    """What a run computes from: SECOM-layout units and wafer maps, as materialised."""

    units: list[SensorUnitInput] = Field(default_factory=list)
    wafers: list[WaferInput] = Field(default_factory=list)


def count_dies(wafers: Sequence[WaferInput]) -> int:
    """Dies over all wafers (cells that are not 0); a map that does not decode counts none."""
    dies = 0
    for wafer in wafers:
        try:
            cells = base64.b64decode(wafer.map.cells, validate=True)
        except (binascii.Error, ValueError):
            continue
        dies += len(cells) - cells.count(0)
    return dies


def pack(data: RunInput) -> bytes:
    return gzip.compress(data.model_dump_json().encode(), compresslevel=6)


def unpack(blob: bytes) -> RunInput:
    return RunInput.model_validate_json(gzip.decompress(blob))


def _pack_item(item: SensorUnitInput | WaferInput) -> bytes:
    return zlib.compress(item.model_dump_json().encode(), 6)


def encode_z(z: Sequence[float | None] | None) -> bytes | None:
    """Little-endian float32, NaN where a reading is missing."""
    if z is None:
        return None
    return np.array([math.nan if v is None else v for v in z], dtype="<f4").tobytes()


def decode_z(blob: bytes | None) -> list[float | None] | None:
    if blob is None:
        return None
    return [None if math.isnan(v) else v for v in np.frombuffer(blob, dtype="<f4").tolist()]


def as_stored(unit: UnitChartResult) -> UnitChartResult:
    """The unit with `z` at the precision it is stored at (float32), so the stream, GET and the
    per-unit chart give the same numbers."""
    if unit.z is None:
        return unit
    return unit.model_copy(update={"z": decode_z(encode_z(unit.z))})


def _chart_row(run_id: str, unit: UnitChartResult) -> dict[str, object]:
    chart = unit.model_copy(update={"z": None}).model_dump_json(exclude={"z"})
    return {
        "run_id": run_id,
        "position": unit.index,
        "chart": zlib.compress(chart.encode(), 6),
        "z": encode_z(unit.z),
    }


def used_by_investigation(run_id: InstrumentedAttribute[str] | str) -> ColumnElement[bool]:
    """True where an investigation was opened from one of the run's alarms (trigger ref
    ``<run_id>:<alarm_id>``). The one place the retention rule reads investigations."""
    return exists().where(func.starts_with(InvestigationRow.trigger_ref, run_id + ":"))


@dataclass(frozen=True)
class AlarmInvestigation:
    investigation_id: str
    status: InvestigationStatus


async def alarm_investigations(
    db: AsyncSession, run_id: str, viewer: Viewer | None = None
) -> dict[str, AlarmInvestigation]:
    """Alarm ID to the newest investigation opened from it, with its status (one that `viewer`
    may open; None: any)."""
    query = select(
        InvestigationRow.trigger_ref,
        InvestigationRow.investigation_id,
        InvestigationRow.status,
    ).where(func.starts_with(InvestigationRow.trigger_ref, run_id + ":"))
    if viewer is not None:
        query = query.where(visible(InvestigationRow.workspace_id, viewer))
    rows = (
        await db.execute(
            query.order_by(InvestigationRow.created_at, InvestigationRow.investigation_id)
        )
    ).all()
    return {
        ref.partition(":")[2]: AlarmInvestigation(
            investigation_id, cast(InvestigationStatus, status)
        )
        for ref, investigation_id, status in rows
    }


async def retain_in(db: AsyncSession, run_id: str) -> None:
    """Keep a run while an investigation uses it (its ``expires_at`` becomes null), in the
    caller's transaction: call it where an investigation is created from a run alarm."""
    await db.execute(update(RunRow).where(RunRow.run_id == run_id).values(expires_at=None))


def new_id(prefix: str) -> str:
    """``prefix`` and a lowercase ULID: 48-bit millisecond time and 80 random bits."""
    value = (time.time_ns() // 1_000_000) << 80 | secrets.randbits(80)
    return prefix + "".join(_CROCKFORD[(value >> shift) & 31] for shift in range(125, -1, -5))


def id_time(identifier: str) -> datetime | None:
    """The creation time encoded in an ID made by :func:`new_id`, if it is one."""
    _, _, ulid = identifier.partition("_")
    if len(ulid) != 26 or any(c not in _CROCKFORD for c in ulid):
        return None
    value = 0
    for char in ulid:
        value = value << 5 | _CROCKFORD.index(char)
    return datetime.fromtimestamp((value >> 80) / 1000, tz=UTC)


def utc_now() -> datetime:
    return datetime.now(UTC)


def stage_failed(stage: StageId, problem: Problem) -> EventFactory:
    return lambda seq, at: StageFailedEvent(seq=seq, at=at, stage=stage, problem=problem)


def stage_skipped(stage: StageId, needs: str) -> EventFactory:
    return lambda seq, at: StageSkippedEvent(seq=seq, at=at, stage=stage, needs=needs)


def run_done(status: Literal["done", "failed"], alarms: int, not_listed: int) -> EventFactory:
    return lambda seq, at: RunDoneEvent(
        seq=seq, at=at, status=status, alarms=alarms, alarms_not_listed=not_listed
    )


def _expired(what: str, identifier: str, created: datetime | None) -> GoneError:
    when = f" (created {created:%Y-%m-%d %H:%M} UTC)" if created is not None else ""
    return GoneError(
        f"{what} {identifier}{when} is no longer kept: a workspace's runs and uploads go 30 days "
        "after it was last used, others 24 hours after they were made. Start a new one."
    )


def missing(what: str, identifier: str, *, now: datetime, ttl: timedelta = RUN_TTL) -> ServiceError:
    """What an ID that cannot be opened gets, whether it never existed, was deleted or belongs to
    another workspace: 410 when the time inside the ID is older than `ttl`, 404 otherwise. The
    answer never says which, so an ID reveals nothing."""
    created = id_time(identifier)
    if created is not None and created + ttl <= now:
        return _expired(what, identifier, created)
    return NotFoundError(f"{what} {identifier} does not exist.")


@dataclass(frozen=True, slots=True)
class PruneReport:
    runs: int
    uploads: int


class DbRunStore:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        notifier: Notifier | None = None,
        *,
        ttl: timedelta = RUN_TTL,
        workspace_life: timedelta = WORKSPACE_LIFE,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._notifier = notifier
        self.ttl = ttl
        self.workspace_life = workspace_life
        self._now = now

    # Runs ---------------------------------------------------------------------------------------

    async def create(
        self,
        origin: RunOrigin,
        data: RunInput,
        stages: Sequence[StageState],
        *,
        owner: str | None = None,
        upload_id: str | None = None,
        again_of: str | None = None,
    ) -> Run:
        """Store a queued run with its `run_started` event (seq 1), owned by the workspace
        `owner` (kept as long as it is), or by none (kept 24 hours)."""
        if [s.stage for s in stages] != list(STAGES):
            raise ValueError("a run has every stage, in order")
        run_id = new_id("run_")
        now = self._now()
        row = RunRow(
            run_id=run_id,
            created_at=now,
            expires_at=None if owner else now + self.ttl,
            status="queued",
            origin=origin.model_dump(mode="json"),
            units=len(data.units),
            wafers=len(data.wafers),
            alarms=[],
            alarms_not_listed=0,
            last_seq=0,
            heartbeat_at=now,
            finished_at=None,
            workspace_id=uuid.UUID(owner) if owner else None,
            upload_id=upload_id,
            again_of=again_of,
        )
        async with self._sessionmaker() as db, db.begin():
            db.add(row)
            await db.flush()
            items = [
                *(("unit", i, _pack_item(unit)) for i, unit in enumerate(data.units)),
                *(("wafer", i, _pack_item(wafer)) for i, wafer in enumerate(data.wafers)),
            ]
            if items:
                await db.execute(
                    insert(RunItemRow),
                    [
                        {"run_id": run_id, "kind": kind, "position": position, "data": blob}
                        for kind, position, blob in items
                    ],
                )
            for position, state in enumerate(stages):
                db.add(
                    RunStageRow(
                        run_id=run_id,
                        position=position,
                        stage=state.stage,
                        state=state.model_dump(mode="json"),
                    )
                )
            await self._append(
                db,
                row,
                [
                    lambda seq, at: RunStartedEvent(
                        seq=seq, at=at, run_id=run_id, origin=origin, stages=list(stages)
                    )
                ],
            )
        return self._run(
            row, list(stages), {}, used=False, read_at=now, kept_until=self._kept_from(now)
        )

    async def update(
        self,
        run_id: str,
        *,
        status: RunStatus | None = None,
        stage: StageState | None = None,
        alarms: Sequence[RunAlarm] = (),
        not_listed: int = 0,
        events: Sequence[EventFactory] = (),
        unit_charts: Sequence[UnitChartResult] = (),
    ) -> None:
        """Apply one change of a run and append its events, in one transaction. `unit_charts`
        are the control-chart results of single units, with every unit's `z`."""
        async with self._sessionmaker() as db, db.begin():
            row = await self._lock(db, run_id)
            if unit_charts:
                await db.execute(
                    insert(RunUnitChartRow), [_chart_row(run_id, u) for u in unit_charts]
                )
            if status is not None:
                row.status = status
                if status in TERMINAL:
                    row.finished_at = self._now()
            if stage is not None:
                if stage.status == "running" and stage.started_at is None:
                    stage = stage.model_copy(update={"started_at": self._now()})
                await self._set_stage(db, run_id, stage)
            if alarms:
                row.alarms = [*row.alarms, *(a.model_dump(mode="json") for a in alarms)]
            row.alarms_not_listed += not_listed
            row.heartbeat_at = self._now()
            await self._append(db, row, events)

    async def heartbeat(self, run_id: str) -> None:
        async with self._sessionmaker() as db, db.begin():
            await db.execute(
                update(RunRow)
                .where(RunRow.run_id == run_id, RunRow.status.in_(("queued", "running")))
                .values(heartbeat_at=self._now())
            )

    async def get(self, run_id: str, viewer: Viewer | None = None) -> Run:
        """The run with its stages and alarms (each alarm with the investigation opened from it,
        if any, and its status). One consistent snapshot: `last_seq` is the newest event it
        includes, so the stream after it carries exactly what came later. NotFoundError for an
        unknown run or one `viewer` may not open (None: any run), GoneError once it expired."""
        async with self._sessionmaker() as db, db.begin():
            await db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            row, used = await self._live(db, run_id, viewer)
            investigations = await alarm_investigations(db, run_id, viewer)
            stages = await self._stages(db, run_id)
            kept_until = await self._kept_until(db, row)
            read_at = self._now()
        return self._run(
            row, stages, investigations, used=used, read_at=read_at, kept_until=kept_until
        )

    async def unit_chart(
        self, run_id: str, index: int, viewer: Viewer | None = None
    ) -> UnitChartResult:
        """Unit `index`'s control-chart result with `z`. NotFoundError when the run has no such
        unit or its control charts are not computed, GoneError once the run expired."""
        async with self._sessionmaker() as db:
            row, _ = await self._live(db, run_id, viewer)
            if not 0 <= index < row.units:
                raise NotFoundError(
                    f"Run {run_id} has {row.units:,} sensor units (0 to {row.units - 1}); there "
                    f"is no unit {index}."
                    if row.units
                    else f"Run {run_id} has no sensor units."
                )
            found = (
                await db.execute(
                    select(RunUnitChartRow.chart, RunUnitChartRow.z).where(
                        RunUnitChartRow.run_id == run_id, RunUnitChartRow.position == index
                    )
                )
            ).first()
        if found is None:
            raise NotFoundError(f"The control charts of run {run_id} have not been computed.")
        chart = UnitChartResult.model_validate_json(zlib.decompress(found.chart))
        return chart.model_copy(update={"z": decode_z(found.z)})

    async def get_input(self, run_id: str, viewer: Viewer | None = None) -> RunInput:
        """Every item of the run's materialised input, in input order."""
        async with self._sessionmaker() as db:
            await self._live(db, run_id, viewer)
            rows = (
                await db.execute(
                    select(RunItemRow.kind, RunItemRow.data)
                    .where(RunItemRow.run_id == run_id)
                    .order_by(RunItemRow.kind, RunItemRow.position)
                )
            ).all()
        return RunInput(
            units=[
                SensorUnitInput.model_validate_json(zlib.decompress(blob))
                for kind, blob in rows
                if kind == "unit"
            ],
            wafers=[
                WaferInput.model_validate_json(zlib.decompress(blob))
                for kind, blob in rows
                if kind == "wafer"
            ],
        )

    async def input_digest(self, run_id: str, viewer: Viewer | None = None) -> str:
        """A digest of the run's stored input items, equal for two runs of the same input."""
        async with self._sessionmaker() as db:
            await self._live(db, run_id, viewer)
            found = await db.scalar(
                select(
                    func.md5(
                        func.string_agg(
                            RunItemRow.kind + ":" + func.md5(RunItemRow.data),
                            aggregate_order_by(literal(","), RunItemRow.kind, RunItemRow.position),
                        )
                    )
                ).where(RunItemRow.run_id == run_id)
            )
        return found or ""

    async def retain(self, run_id: str) -> None:
        """See :func:`retain_in`."""
        async with self._sessionmaker() as db, db.begin():
            await retain_in(db, run_id)

    # RunReader (the investigator and the chat) --------------------------------------------------
    # They read for the workspace the current request or investigation job acts for
    # (:func:`~yield_guardian.services.access.viewing`); acting for none, only runs of none.

    async def get_run(self, run_id: str) -> Run | None:
        try:
            return await self.get(run_id, current_viewer() or NOBODY)
        except (NotFoundError, GoneError):
            return None

    async def get_unit_chart(self, run_id: str, index: int) -> UnitChartResult | None:
        try:
            return await self.unit_chart(run_id, index, current_viewer() or NOBODY)
        except (NotFoundError, GoneError):
            return None

    async def get_unit_input(self, run_id: str, index: int) -> SensorUnitInput | None:
        data = await self._item(run_id, "unit", index)
        return None if data is None else SensorUnitInput.model_validate_json(data)

    async def get_wafer_input(self, run_id: str, index: int) -> WaferInput | None:
        data = await self._item(run_id, "wafer", index)
        return None if data is None else WaferInput.model_validate_json(data)

    async def events(
        self, run_id: str, *, after_seq: int | None = None
    ) -> AsyncIterator[RunEventPayload]:
        """Stored events after `after_seq`, then live ones; ends after `run_done`, or at once when
        nothing follows `after_seq` of a finished run."""
        last = after_seq or 0
        with self._subscribe(run_id) as wake:
            batch, status = await self._events_after(run_id, last)
            if not batch and status in TERMINAL:
                return
            while True:
                for event in batch:
                    yield event
                if batch:
                    last = batch[-1].seq
                    if batch[-1].type == "run_done":
                        return
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(wake.wait(), STREAM_POLL_S)
                wake.clear()
                batch, _ = await self._events_after(run_id, last)

    async def interrupt(self, run_id: str, problem: Problem = INTERRUPTED) -> bool:
        """Fail an unfinished run: its running stage fails with `problem`, the stages not started
        are skipped, then `run_done` (failed). False when the run had already finished."""
        async with self._sessionmaker() as db, db.begin():
            row = await self._lock(db, run_id)
            if row.status in TERMINAL:
                return False
            events: list[EventFactory] = []
            for state in await self._stages(db, run_id):
                if state.status == "running":
                    await self._set_stage(
                        db,
                        run_id,
                        state.model_copy(update={"status": "failed", "problem": problem}),
                    )
                    events.append(stage_failed(state.stage, problem))
                elif state.status == "pending":
                    await self._set_stage(
                        db,
                        run_id,
                        state.model_copy(update={"status": "skipped", "needs": STOPPED_BEFORE}),
                    )
                    events.append(stage_skipped(state.stage, STOPPED_BEFORE))
            row.status = "failed"
            row.finished_at = self._now()
            events.append(run_done("failed", len(row.alarms), row.alarms_not_listed))
            await self._append(db, row, events)
        return True

    async def fail_stale(self, stale_after: timedelta) -> list[str]:
        """Fail the runs whose process stopped: unfinished, no heartbeat for `stale_after`."""
        cutoff = self._now() - stale_after
        async with self._sessionmaker() as db:
            stale = list(
                (
                    await db.scalars(
                        select(RunRow.run_id).where(
                            RunRow.status.in_(("queued", "running")),
                            func.coalesce(RunRow.heartbeat_at, RunRow.created_at) < cutoff,
                        )
                    )
                ).all()
            )
        failed = [run_id for run_id in stale if await self.interrupt(run_id)]
        if failed:
            log.warning("runs_failed_stale", runs=failed)
        return failed

    # Uploads ------------------------------------------------------------------------------------

    async def create_upload(
        self,
        *,
        kind: UploadKind,
        filename: str,
        data: RunInput,
        summary: Callable[[str, datetime], UploadSummary],
        owner: str | None = None,
    ) -> UploadSummary:
        """Store parsed items; `summary(upload_id, expires_at)` builds what the client sees.
        An upload of the workspace `owner` is kept as long as it; one of none for 24 hours."""
        upload_id = new_id("upl_")
        now = self._now()
        built = summary(upload_id, now + (self.workspace_life if owner else self.ttl))
        async with self._sessionmaker() as db, db.begin():
            db.add(
                UploadRow(
                    upload_id=upload_id,
                    created_at=now,
                    expires_at=built.expires_at,
                    kind=kind,
                    filename=filename,
                    runnable=built.runnable,
                    summary=built.model_dump(mode="json"),
                    items=pack(data),
                    workspace_id=uuid.UUID(owner) if owner else None,
                )
            )
        return built

    async def get_upload(
        self, upload_id: str, viewer: Viewer | None = None
    ) -> tuple[UploadSummary, RunInput]:
        """The upload and its items; for another workspace's upload, what a missing one gets."""
        async with self._sessionmaker() as db:
            row = await db.get(UploadRow, upload_id)
            if row is None or (viewer is not None and not viewer.sees(row.workspace_id)):
                raise self._missing("Upload", upload_id)
            if row.workspace_id is None and row.expires_at <= self._now():
                raise _expired("Upload", upload_id, row.created_at)
            kept_until = await self._kept_until(db, row)
        summary = UploadSummary.model_validate(row.summary)
        if kept_until is not None:
            summary = summary.model_copy(update={"expires_at": kept_until})
        return summary, unpack(row.items)

    # Expiry -------------------------------------------------------------------------------------

    async def prune(self) -> PruneReport:
        """Delete expired uploads and expired runs no investigation uses, of no workspace (a
        workspace's go with it: ``DbSessionManager.prune``)."""
        now = self._now()
        async with self._sessionmaker() as db, db.begin():
            runs = await db.execute(
                delete(RunRow)
                .where(
                    RunRow.expires_at.is_not(None),
                    RunRow.expires_at <= now,
                    ~used_by_investigation(RunRow.run_id),
                )
                .returning(RunRow.run_id)
            )
            uploads = await db.execute(
                delete(UploadRow)
                .where(UploadRow.workspace_id.is_(None), UploadRow.expires_at <= now)
                .returning(UploadRow.upload_id)
            )
            report = PruneReport(runs=len(runs.all()), uploads=len(uploads.all()))
        if report.runs or report.uploads:
            log.info("runs_pruned", runs=report.runs, uploads=report.uploads)
        return report

    # Internals ----------------------------------------------------------------------------------

    async def _live(
        self, db: AsyncSession, run_id: str, viewer: Viewer | None = None
    ) -> tuple[RunRow, bool]:
        """The run's row and whether an investigation uses it; NotFoundError for an unknown run,
        GoneError once it expired, and for another workspace's run what its ID would get if the
        run did not exist."""
        row = await db.get(RunRow, run_id)
        if row is None or (viewer is not None and not viewer.sees(row.workspace_id)):
            raise self._missing("Run", run_id)
        used = bool(await db.scalar(select(used_by_investigation(run_id))))
        if not used and row.expires_at is not None and row.expires_at <= self._now():
            raise _expired("Run", run_id, row.created_at)
        return row, used

    def _missing(self, what: str, identifier: str) -> ServiceError:
        return missing(what, identifier, now=self._now(), ttl=self.ttl)

    @staticmethod
    async def _lock(db: AsyncSession, run_id: str) -> RunRow:
        row = await db.scalar(
            select(RunRow)
            .where(RunRow.run_id == run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise NotFoundError(f"Run {run_id} does not exist.")
        return row

    @staticmethod
    async def _set_stage(db: AsyncSession, run_id: str, state: StageState) -> None:
        await db.execute(
            update(RunStageRow)
            .where(RunStageRow.run_id == run_id, RunStageRow.position == STAGES.index(state.stage))
            .values(state=state.model_dump(mode="json"))
        )

    @staticmethod
    async def _stages(db: AsyncSession, run_id: str) -> list[StageState]:
        states = (
            await db.scalars(
                select(RunStageRow.state)
                .where(RunStageRow.run_id == run_id)
                .order_by(RunStageRow.position)
            )
        ).all()
        return [StageState.model_validate(s) for s in states]

    def _kept_from(self, last_seen: datetime) -> datetime:
        return last_seen + self.workspace_life

    async def _kept_until(self, db: AsyncSession, row: RunRow | UploadRow) -> datetime | None:
        """When a workspace's run or upload goes: when its workspace does (30 days after the
        workspace was last used); None for a row of no workspace."""
        if row.workspace_id is None:
            return None
        seen = await db.scalar(
            select(WorkspaceRow.last_seen_at).where(WorkspaceRow.workspace_id == row.workspace_id)
        )
        return self._kept_from(seen) if seen is not None else None

    async def _item(self, run_id: str, kind: str, index: int) -> bytes | None:
        if index < 0:
            return None
        async with self._sessionmaker() as db:
            try:
                await self._live(db, run_id, current_viewer() or NOBODY)
            except (NotFoundError, GoneError):
                return None
            data = await db.scalar(
                select(RunItemRow.data).where(
                    RunItemRow.run_id == run_id,
                    RunItemRow.kind == kind,
                    RunItemRow.position == index,
                )
            )
        return None if data is None else zlib.decompress(data)

    async def _append(self, db: AsyncSession, row: RunRow, events: Sequence[EventFactory]) -> None:
        for make in events:
            row.last_seq += 1
            at = self._now()
            event = make(row.last_seq, at)
            db.add(
                RunEventRow(
                    run_id=row.run_id,
                    seq=row.last_seq,
                    type=event.type,
                    at=at,
                    payload=event.model_dump(mode="json"),
                )
            )
        if events:
            await db.flush()
            await db.execute(select(func.pg_notify(RUN_EVENTS_CHANNEL, row.run_id)))

    @staticmethod
    def _run(
        row: RunRow,
        stages: list[StageState],
        investigations: dict[str, AlarmInvestigation],
        *,
        used: bool,
        read_at: datetime,
        kept_until: datetime | None = None,
    ) -> Run:
        alarms: list[RunAlarm] = []
        for stored in row.alarms:
            alarm = RunAlarm.model_validate(stored)
            found = investigations.get(alarm.alarm_id)
            if found is not None:
                alarm = alarm.model_copy(
                    update={
                        "investigation_id": found.investigation_id,
                        "investigation_status": found.status,
                    }
                )
            alarms.append(alarm)
        return Run(
            run_id=row.run_id,
            created_at=row.created_at,
            status=row.status,
            origin=RunOrigin.model_validate(row.origin),
            units=row.units,
            wafers=row.wafers,
            stages=stages,
            alarms=alarms,
            alarms_not_listed=row.alarms_not_listed,
            expires_at=(
                kept_until if row.workspace_id is not None else None if used else row.expires_at
            ),
            last_seq=row.last_seq,
            read_at=read_at,
        )

    @contextlib.contextmanager
    def _subscribe(self, run_id: str) -> Iterator[asyncio.Event]:
        if self._notifier is None:
            yield asyncio.Event()
            return
        with self._notifier.subscribe(RUN_EVENTS_CHANNEL, run_id) as wake:
            yield wake

    async def _events_after(self, run_id: str, after: int) -> tuple[list[RunEventPayload], str]:
        async with self._sessionmaker() as db:
            status = await db.scalar(select(RunRow.status).where(RunRow.run_id == run_id))
            if status is None:
                raise self._missing("Run", run_id)
            payloads = (
                await db.scalars(
                    select(RunEventRow.payload)
                    .where(RunEventRow.run_id == run_id, RunEventRow.seq > after)
                    .order_by(RunEventRow.seq)
                )
            ).all()
        return [RunEvent.model_validate(p).root for p in payloads], status


def initial_stage(stage: StageId, needs: str | None = None) -> StageState:
    """A stage before the run starts: pending, or skipped with what it needs."""
    return StageState(
        stage=stage,
        station=STAGE_STATION[stage],
        status="skipped" if needs is not None else "pending",
        needs=needs,
    )


class Pruner(Protocol):
    async def prune(self) -> object: ...


class RunMaintenance:
    """A registry Resource: fails stale runs and prunes expired runs and uploads, then runs the
    other `pruners` (ended sessions, handoff codes and empty workspaces), at start and then every
    `interval_s`."""

    def __init__(
        self,
        store: DbRunStore,
        *,
        interval_s: float = 300.0,
        stale_after: timedelta = timedelta(minutes=2),
        pruners: Sequence[Pruner] = (),
    ) -> None:
        self.store = store
        self.interval_s = interval_s
        self.stale_after = stale_after
        self.pruners = list(pruners)
        self._task: asyncio.Task[None] | None = None

    async def run_once(self) -> None:
        await self.store.fail_stale(self.stale_after)
        await self.store.prune()
        for pruner in self.pruners:
            await pruner.prune()

    async def _loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("run_maintenance_failed")
            await asyncio.sleep(self.interval_s)

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="run-maintenance")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
