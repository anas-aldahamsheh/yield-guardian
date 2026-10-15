"""Live runs (PLAN_V2 §3): turn a submission into sensor units and wafer maps, then compute every
stage now, in order, and stream each result as soon as it is computed.

Every way in (a random real sample, a case from the catalog, a pick from the dataset browsers, a
drawing, an uploaded file) is materialised into the same ``SensorUnitInput[]`` and
``WaferInput[]`` and processed by the same code, so a sample is processed exactly like an
upload. The input keeps its order: units are never re-sorted (units whose timestamps go back
make intake say so, and the drift stage asks for a file sorted by time).

The stages run one at a time in the order of ``StageId``: intake, sensor_risk, control_charts,
drift_health, wafer_pattern, wafer_similar, lot, final_test. Each stage ends with exactly one of
``stage_result``, ``stage_skipped`` or ``stage_failed``; a stage that is attempted is announced
by ``stage_started`` first, and a stage skipped before the run starts (its track is absent: "needs
sensor data", "needs wafer maps") gets its ``stage_skipped`` at its place in the order. The
engines compute in a worker thread and ``elapsed_ms`` is their own compute time. A stage that
fails gives ``stage_failed`` with a Problem and the run goes on; the stages that need its result
are skipped and say so. Alarms (``live.run_alarms``) follow the ``stage_result`` that raised them,
in the same transaction, and ``run_done`` ends the stream.
"""

import asyncio
import contextlib
import math
import secrets
import time
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field
from random import Random
from typing import Literal, Protocol

import structlog

from yield_guardian.contracts.base import Problem
from yield_guardian.contracts.runs import (
    MAX_DIES,
    MAX_UNITS,
    MAX_WAFERS,
    AlarmEvent,
    CaseRunCreate,
    ControlChartsResult,
    Dataset,
    DrawLayoutItem,
    DrawLayoutList,
    DrawnRunCreate,
    PickRunCreate,
    Run,
    RunAlarm,
    RunCaseList,
    RunCreated,
    RunCreatePayload,
    RunEventPayload,
    RunOrigin,
    RunStatus,
    SampleRunCreate,
    SensorRiskResult,
    SensorUnitInput,
    StageId,
    StageResult,
    StageResultEvent,
    StageStartedEvent,
    StageState,
    UnitChartResult,
    UploadRunCreate,
    WaferInput,
    WaferPatternResult,
)
from yield_guardian.contracts.services import (
    InvalidArgumentError,
    NotFoundError,
    NotReadyError,
    ServiceError,
)
from yield_guardian.live.protocols import (
    NeedsInput,
    Picked,
    SensorEngine,
    SensorFileParser,
    WaferEngine,
    WaferFileParser,
)
from yield_guardian.live.run_alarms import Candidate, raise_alarms
from yield_guardian.live.stages import final_test, has_results, intake
from yield_guardian.live.wafers import MapError, decode_map
from yield_guardian.services.runs import (
    STAGES,
    Z_IN_RESULT,
    EventFactory,
    InputError,
    RunInput,
    as_stored,
    count_dies,
    initial_stage,
    run_done,
    stage_failed,
    stage_skipped,
)

log = structlog.get_logger(__name__)

SENSOR_STAGES: tuple[StageId, ...] = ("sensor_risk", "control_charts", "drift_health")
WAFER_STAGES: tuple[StageId, ...] = ("wafer_pattern", "wafer_similar", "lot")
NEEDS_SENSORS = "needs sensor data"
NEEDS_WAFERS = "needs wafer maps"
NEEDS_RESULTS = "needs recorded final-test results or wafer labels"
NEEDS_PATTERN = "needs the wafer pattern result, which did not finish"
NEEDS_COMPARABLE = "needs the risk or wafer pattern result, which did not finish"
SEED_LIMIT = 2**31
RULE_LIMIT = 600
SECOM_MISSING = "The SECOM model bundle is not loaded on this server."
WAFERMAP_MISSING = "The wafer-map model bundle is not loaded on this server."


@dataclass(frozen=True, slots=True)
class Engines:
    """The loaded engines and file parsers; a missing one leaves its track unavailable."""

    sensors: SensorEngine | None = None
    wafers: WaferEngine | None = None
    sensor_file: SensorFileParser | None = None
    wafer_file: WaferFileParser | None = None


class RunWriter(Protocol):
    """What the orchestrator writes to (``services.runs.DbRunStore``)."""

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
    ) -> None: ...

    async def heartbeat(self, run_id: str) -> None: ...


class RunStore(RunWriter, Protocol):
    """The run store as the service uses it."""

    async def create(
        self, origin: RunOrigin, data: RunInput, stages: Sequence[StageState]
    ) -> Run: ...

    async def get(self, run_id: str) -> Run: ...

    async def unit_chart(self, run_id: str, index: int) -> UnitChartResult: ...

    def events(
        self, run_id: str, *, after_seq: int | None = None
    ) -> AsyncIterator[RunEventPayload]: ...

    async def interrupt(self, run_id: str, problem: Problem = ...) -> bool: ...


class UploadSource(Protocol):
    async def runnable_upload(self, upload_id: str) -> tuple[str, RunInput]:
        """The file name and parsed items of a runnable upload; a ServiceError otherwise."""
        ...


class CaseSource(Protocol):
    async def materialise(self, case_id: str) -> tuple[RunOrigin, RunInput]: ...

    async def list(self) -> RunCaseList: ...


def fit(text: str, limit: int = RULE_LIMIT) -> str:
    """`text` within `limit` characters, cut after a whole sentence when it is too long."""
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    end = cut.rfind(". ")
    return (cut[: end + 1] if end > 0 else cut.rstrip()) + "…"


def datasets(units: Sequence[SensorUnitInput], wafers: Sequence[WaferInput]) -> list[Dataset]:
    found: list[Dataset] = []
    if units:
        found.append("secom")
    if wafers:
        found.append("wm811k")
    return found


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:]


def check_size(data: RunInput) -> None:
    if len(data.units) > MAX_UNITS:
        raise InputError(
            f"The run has {len(data.units):,} units; a run takes at most {MAX_UNITS:,}."
        )
    if len(data.wafers) > MAX_WAFERS:
        raise InputError(
            f"The run has {len(data.wafers):,} wafers; a run takes at most {MAX_WAFERS:,}."
        )
    if not data.units and not data.wafers:
        raise InputError("The run has no sensor units and no wafers.")
    dies = count_dies(data.wafers)
    if dies > MAX_DIES:
        raise InputError(
            f"This run has {dies:,} dies; the limit is {MAX_DIES:,}. Choose fewer wafers."
        )


class Materialiser:
    """Every way in, made into the same run input, with its origin in words the page shows."""

    def __init__(
        self, engines: Engines, cases: CaseSource | None, uploads: UploadSource | None
    ) -> None:
        self.engines = engines
        self.cases = cases
        self.uploads = uploads

    def _sensors(self) -> SensorEngine:
        if self.engines.sensors is None:
            raise NotReadyError(SECOM_MISSING)
        return self.engines.sensors

    def _wafers(self) -> WaferEngine:
        if self.engines.wafers is None:
            raise NotReadyError(WAFERMAP_MISSING)
        return self.engines.wafers

    async def __call__(self, payload: RunCreatePayload) -> tuple[RunOrigin, RunInput]:
        match payload:
            case SampleRunCreate():
                origin, data = await self._sample(payload)
            case CaseRunCreate():
                if self.cases is None:
                    raise NotReadyError("The case catalog is not available on this server.")
                origin, data = await self.cases.materialise(payload.case_id)
            case PickRunCreate():
                origin, data = await self._pick(payload)
            case DrawnRunCreate():
                origin, data = self._drawn(payload)
            case UploadRunCreate():
                origin, data = await self._upload(payload)
        check_size(data)
        return origin, data

    async def _sample(self, payload: SampleRunCreate) -> tuple[RunOrigin, RunInput]:
        """Real SECOM units, then a real WM-811K lot, from one Random seeded with the run's
        seed (the units first, so a seed picks the same units whether or not the wafer engine
        is loaded). A track whose engine is not loaded is left out and the rule says so."""
        sensors, wafers = self.engines.sensors, self.engines.wafers
        if sensors is None and wafers is None:
            raise NotReadyError("Neither model bundle is loaded on this server.")
        seed = payload.seed if payload.seed is not None else secrets.randbelow(SEED_LIMIT)

        def pick() -> tuple[Picked[SensorUnitInput] | None, Picked[WaferInput] | None]:
            rng = Random(seed)  # noqa: S311 - a reproducible pick of real data, not a secret
            units = sensors.sample(rng) if sensors is not None else None
            return units, wafers.sample(rng) if wafers is not None else None

        units, lot = await asyncio.to_thread(pick)
        rules = [
            units.rule if units else "No SECOM units: the SECOM bundle is not loaded here.",
            lot.rule if lot else "No wafers: the wafer-map bundle is not loaded here.",
            f"Seed {seed}: the same seed repeats this pick.",
        ]
        data = RunInput(units=units.items if units else [], wafers=lot.items if lot else [])
        origin = RunOrigin(
            source="sample",
            datasets=datasets(data.units, data.wafers),
            title="A random real sample",
            rule=fit(" ".join(rules)),
            seed=seed,
        )
        return origin, data

    async def _pick(self, payload: PickRunCreate) -> tuple[RunOrigin, RunInput]:
        if not payload.unit_ids and not payload.wafer_ids and payload.lot is None:
            raise InputError("Pick at least one unit, one wafer or a lot.")
        for name, chosen in (("Unit", payload.unit_ids), ("Wafer", payload.wafer_ids)):
            seen: set[object] = set()
            for item in chosen:
                if item in seen:
                    raise InputError(f"{name} {item} is picked twice.")
                seen.add(item)
        units: list[SensorUnitInput] = []
        wafers: list[WaferInput] = []
        rules: list[str] = []
        try:
            if payload.unit_ids:
                try:
                    units = await asyncio.to_thread(self._sensors().from_secom, payload.unit_ids)
                except InvalidArgumentError as error:  # a unit SECOM does not have
                    raise NotFoundError(error.detail) from error
                rules.append(
                    f"The {len(units):,} SECOM units you chose, in time order."
                    if len(units) != 1
                    else "The SECOM unit you chose."
                )
            if payload.wafer_ids or payload.lot is not None:
                engine = self._wafers()
                wafers = await asyncio.to_thread(engine.from_demo, payload.wafer_ids, payload.lot)
                chosen_lot = f"every demo wafer of lot {payload.lot}" if payload.lot else ""
                chosen_wafers = (
                    f"the {len(payload.wafer_ids):,} WM-811K demo wafers you chose"
                    if payload.wafer_ids
                    else ""
                )
                rules.append(
                    _sentence(" and ".join(p for p in (chosen_wafers, chosen_lot) if p)) + "."
                )
        except ServiceError:
            raise  # NotFoundError for a wafer or lot the demo set does not have: 404
        except (LookupError, ValueError) as error:
            raise InputError(f"The pick cannot be read: {error}") from error
        origin = RunOrigin(
            source="pick",
            datasets=datasets(units, wafers),
            title="Your pick of real data",
            rule=fit(" ".join(rules)),
        )
        return origin, RunInput(units=units, wafers=wafers)

    def _drawn(self, payload: DrawnRunCreate) -> tuple[RunOrigin, RunInput]:
        self._wafers()
        for position, wafer in enumerate(payload.wafers):
            try:
                decode_map(wafer.map)
            except MapError as error:
                raise InputError(f"Drawing {position + 1}: {error.message}") from error
        # A drawing is not a WM-811K wafer: no recorded label, no source wafer.
        wafers = [
            w.model_copy(update={"label": None, "source_wafer": None}) for w in payload.wafers
        ]
        count = "the wafer" if len(wafers) == 1 else f"the {len(wafers)} wafers"
        origin = RunOrigin(
            source="drawn",
            datasets=["user"],
            title="Your drawing",
            rule=(
                f"Your drawing: {count} you painted on the die layout of a real WM-811K wafer, "
                "where every die you did not paint is a pass."
            ),
        )
        return origin, RunInput(wafers=wafers)

    async def _upload(self, payload: UploadRunCreate) -> tuple[RunOrigin, RunInput]:
        if self.uploads is None:
            raise NotReadyError("Uploads are not available on this server.")
        filename, data = await self.uploads.runnable_upload(payload.upload_id)
        if data.units:
            self._sensors()
        if data.wafers:
            self._wafers()
        rows = f"{len(data.units):,} units" if data.units else f"{len(data.wafers):,} wafers"
        origin = RunOrigin(
            source="upload",
            datasets=["user"],
            title="Your file",
            rule=f"The {rows} of your file {filename}, in file order, as validated on upload.",
            filename=filename,
        )
        return origin, data


@dataclass(slots=True)
class _Progress:
    results: dict[StageId, StageResult] = field(default_factory=dict)
    listed: int = 0
    not_listed: int = 0
    failed: bool = False
    started: bool = False


@dataclass(frozen=True, slots=True)
class _Skip:
    needs: str


Job = Callable[[], StageResult]


def _shown(result: StageResult) -> tuple[StageResult, list[UnitChartResult]]:
    """The result as the event and GET carry it (control charts: `z` for the first
    `Z_IN_RESULT` units only), and each unit's full chart for the per-unit read."""
    if not isinstance(result, ControlChartsResult):
        return result, []
    charts = [as_stored(u) for u in result.units]
    units = [u if u.index < Z_IN_RESULT else u.model_copy(update={"z": None}) for u in charts]
    return result.model_copy(update={"units": units}), charts


def _internal(stage: StageId) -> Problem:
    return Problem(
        title="Stage failed",
        status=500,
        code="internal_error",
        detail=f"The {stage.replace('_', ' ')} stage stopped with an unexpected error. It has "
        "been logged.",
    )


class RunOrchestrator:
    def __init__(self, engines: Engines, writer: RunWriter, *, heartbeat_s: float = 15.0) -> None:
        self.engines = engines
        self.writer = writer
        self.heartbeat_s = heartbeat_s

    @staticmethod
    def plan(data: RunInput) -> list[StageState]:
        """Every stage, pending, or skipped when its track or anything to compare is absent."""
        needs: dict[StageId, str] = {}
        if not data.units:
            needs.update(dict.fromkeys(SENSOR_STAGES, NEEDS_SENSORS))
        if not data.wafers:
            needs.update(dict.fromkeys(WAFER_STAGES, NEEDS_WAFERS))
        if not has_results(data.units, data.wafers):
            needs["final_test"] = NEEDS_RESULTS
        return [initial_stage(stage, needs.get(stage)) for stage in STAGES]

    async def execute(self, run_id: str, data: RunInput, plan: Sequence[StageState]) -> None:
        progress = _Progress()
        for planned in plan:
            if planned.status == "skipped":
                await self.writer.update(
                    run_id, events=[stage_skipped(planned.stage, planned.needs or "")]
                )
                continue
            await self._stage(run_id, planned, data, progress)
        status: Literal["done", "failed"] = "failed" if progress.failed else "done"
        await self.writer.update(
            run_id,
            status=status,
            events=[run_done(status, progress.listed, progress.not_listed)],
        )

    def _job(self, stage: StageId, data: RunInput, progress: _Progress) -> Job | _Skip | Problem:
        sensors, wafers = self.engines.sensors, self.engines.wafers
        units, maps = data.units, data.wafers
        results = progress.results
        if stage == "intake":
            engine = sensors if units else None
            return lambda: intake(units, maps, engine.unmonitored_sensors() if engine else [])
        if stage in SENSOR_STAGES:
            if sensors is None:
                return NotReadyError(SECOM_MISSING).problem()
            if stage == "sensor_risk":
                return lambda: sensors.risk(units)
            if stage == "control_charts":
                return lambda: sensors.control_charts(units)
            return lambda: sensors.drift_health(units)
        if stage in WAFER_STAGES:
            if wafers is None:
                return NotReadyError(WAFERMAP_MISSING).problem()
            if stage == "wafer_pattern":
                return lambda: wafers.pattern(maps)
            found = results.get("wafer_pattern")
            if not isinstance(found, WaferPatternResult):
                return _Skip(NEEDS_PATTERN)
            if stage == "wafer_similar":
                return lambda: wafers.similar(maps, found)
            return lambda: wafers.lots(maps, found)
        risk = results.get("sensor_risk")
        pattern = results.get("wafer_pattern")
        risk = risk if isinstance(risk, SensorRiskResult) else None
        pattern = pattern if isinstance(pattern, WaferPatternResult) else None
        comparable = (risk is not None and any(u.result for u in units)) or (
            pattern is not None and any(w.label for w in maps)
        )
        if not comparable:
            return _Skip(NEEDS_COMPARABLE)
        return lambda: final_test(units, maps, risk, pattern)

    async def _compute(self, run_id: str, job: Job) -> tuple[StageResult, float]:
        def timed() -> tuple[StageResult, float]:
            started = time.perf_counter()
            result = job()
            return result, (time.perf_counter() - started) * 1000.0

        async def beat() -> None:
            while True:
                await asyncio.sleep(self.heartbeat_s)
                with contextlib.suppress(Exception):
                    await self.writer.heartbeat(run_id)

        ticker = asyncio.create_task(beat())
        try:
            return await asyncio.to_thread(timed)
        finally:
            ticker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ticker

    async def _stage(
        self, run_id: str, planned: StageState, data: RunInput, progress: _Progress
    ) -> None:
        stage = planned.stage
        job = self._job(stage, data, progress)
        if isinstance(job, _Skip):
            await self._skip(run_id, planned, job.needs)
            return
        status: RunStatus | None = None if progress.started else "running"
        progress.started = True
        await self.writer.update(
            run_id,
            status=status,
            stage=planned.model_copy(update={"status": "running"}),
            events=[lambda seq, at: StageStartedEvent(seq=seq, at=at, stage=stage)],
        )
        if isinstance(job, Problem):
            await self._fail(run_id, planned, job, progress)
            return
        try:
            result, elapsed = await self._compute(run_id, job)
        except NeedsInput as needs:
            await self._skip(run_id, planned, needs.needs)
            return
        except ServiceError as error:
            await self._fail(run_id, planned, error.problem(), progress)
            return
        except Exception:
            log.exception("run_stage_failed", run_id=run_id, stage=stage)
            await self._fail(run_id, planned, _internal(stage), progress)
            return
        if not math.isfinite(elapsed) or elapsed < 0:
            elapsed = 0.0
        progress.results[stage] = result
        found, left_out = raise_alarms(stage, result, data.units)
        alarms = [
            self._alarm(run_id, stage, candidate, progress.listed + number)
            for number, candidate in enumerate(found, start=1)
        ]
        progress.listed += len(alarms)
        progress.not_listed += left_out
        shown, charts = _shown(result)
        events: list[EventFactory] = [
            lambda seq, at: StageResultEvent(
                seq=seq, at=at, stage=stage, elapsed_ms=elapsed, result=shown
            ),
            *(_alarm_event(alarm) for alarm in alarms),
        ]
        await self.writer.update(
            run_id,
            stage=planned.model_copy(
                update={"status": "done", "elapsed_ms": elapsed, "result": shown}
            ),
            alarms=alarms,
            not_listed=left_out,
            events=events,
            unit_charts=charts,
        )

    async def _skip(self, run_id: str, planned: StageState, needs: str) -> None:
        await self.writer.update(
            run_id,
            stage=planned.model_copy(update={"status": "skipped", "needs": needs}),
            events=[stage_skipped(planned.stage, needs)],
        )

    async def _fail(
        self, run_id: str, planned: StageState, problem: Problem, progress: _Progress
    ) -> None:
        progress.failed = True
        await self.writer.update(
            run_id,
            stage=planned.model_copy(update={"status": "failed", "problem": problem}),
            events=[stage_failed(planned.stage, problem)],
        )

    @staticmethod
    def _alarm(run_id: str, stage: StageId, found: Candidate, number: int) -> RunAlarm:
        return RunAlarm(
            alarm_id=f"RA-{number}",
            run_id=run_id,
            stage=stage,
            kind=found.kind,
            severity=found.severity,
            unit_index=found.unit_index,
            unit_id=found.unit_id,
            wafer_index=found.wafer_index,
            lot=found.lot,
            value=found.value,
            limit=found.limit,
            title=found.title,
            meaning=found.meaning,
            sensors=list(found.sensors),
        )


def _alarm_event(alarm: RunAlarm) -> EventFactory:
    return lambda seq, at: AlarmEvent(seq=seq, at=at, alarm=alarm)


class RunService:
    """Runs as the API serves them: create (materialise, store, start in the background), read,
    stream, the case catalog and the draw layouts. A registry Resource: stopping it interrupts
    the runs still computing, so their streams end."""

    def __init__(
        self,
        store: RunStore,
        engines: Engines,
        *,
        cases: CaseSource | None = None,
        uploads: UploadSource | None = None,
        heartbeat_s: float = 15.0,
    ) -> None:
        self.store = store
        self.engines = engines
        self.cases = cases
        self.materialise = Materialiser(engines, cases, uploads)
        self.orchestrator = RunOrchestrator(engines, store, heartbeat_s=heartbeat_s)
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._layouts: DrawLayoutList | None = None

    async def create(self, payload: RunCreatePayload) -> RunCreated:
        origin, data = await self.materialise(payload)
        plan = self.orchestrator.plan(data)
        run = await self.store.create(origin, data, plan)
        task = asyncio.create_task(self._execute(run.run_id, data, plan), name=run.run_id)
        self._tasks[run.run_id] = task
        task.add_done_callback(lambda _t: self._tasks.pop(run.run_id, None))
        return RunCreated(
            run_id=run.run_id, events_url=f"/api/v1/runs/{run.run_id}/events", origin=origin
        )

    async def _execute(self, run_id: str, data: RunInput, plan: Sequence[StageState]) -> None:
        try:
            await self.orchestrator.execute(run_id, data, plan)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("run_failed", run_id=run_id)
            with contextlib.suppress(Exception):
                await self.store.interrupt(run_id, _internal_run())

    async def get(self, run_id: str) -> Run:
        return await self.store.get(run_id)

    async def unit_chart(self, run_id: str, index: int) -> UnitChartResult:
        return await self.store.unit_chart(run_id, index)

    def events(
        self, run_id: str, *, after_seq: int | None = None
    ) -> AsyncIterator[RunEventPayload]:
        return self.store.events(run_id, after_seq=after_seq)

    async def list_cases(self) -> RunCaseList:
        if self.cases is None:
            raise NotReadyError("The case catalog needs both model bundles, which are not loaded.")
        return await self.cases.list()

    async def layouts(self) -> DrawLayoutList:
        if self.engines.wafers is None:
            raise NotReadyError(WAFERMAP_MISSING)
        if self._layouts is None:
            found = await asyncio.to_thread(self.engines.wafers.draw_layouts)
            self._layouts = DrawLayoutList(
                items=[
                    DrawLayoutItem(
                        layout_id=f.layout_id, map=f.map, source_wafer=f.source_wafer, rule=f.rule
                    )
                    for f in found
                ]
            )
        return self._layouts

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        """Interrupt the runs still computing here; their streams end with a failed run_done."""
        tasks = dict(self._tasks)
        for task in tasks.values():
            task.cancel()
        await asyncio.gather(*tasks.values(), return_exceptions=True)
        for run_id in tasks:
            with contextlib.suppress(Exception):
                await self.store.interrupt(run_id)


def _internal_run() -> Problem:
    return Problem(
        title="Run failed",
        status=500,
        code="internal_error",
        detail="The run stopped with an unexpected error. It has been logged.",
    )
