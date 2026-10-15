"""The case catalog (PLAN_V2 §3.1, "Pick a case"): real situations found in the data by fixed
rules over live computations. Nothing here is written by hand: each case is the first (or the
strongest) item a rule finds when the engines compute over the real SECOM units and the real
WM-811K demo wafers, once, at startup. The rules are deterministic, so the catalog is the same
on every start with the same bundles, and a case run computes exactly what the rule saw.

Rules (a case is left out when its rule finds nothing):

- ``spe_alarm``: the first unit of the test block (units the risk model never saw), in time
  order, whose live SPE is beyond the 99.9% control limit; the run holds it and the 29 units
  before it in time order.
- ``slow_drift``: the test block cut into consecutive windows of 50 units, in time order; the
  first window in which a sensor group's live EWMA or CUSUM signals.
- ``scratch``: the first demo wafer, by lot name and then wafer number, that the live model
  auto-accepts as Scratch and does not flag as unknown.
- ``unknown_pattern``: of the demo wafers the live model flags as unknown, the one with the
  highest unknown score relative to its threshold (first by lot and wafer on a tie).
- ``lot_repeat``: the demo lot whose live lot test (all its wafers, as a run computes it) has
  the smallest q-value (first by lot name on a tie); its title says whether it is flagged.
"""

import asyncio
import contextlib
import threading
from collections.abc import Sequence
from dataclasses import dataclass

import structlog

from yield_guardian.contracts.base import LotId, UnitId, WaferId
from yield_guardian.contracts.runs import (
    Dataset,
    RunCase,
    RunCaseList,
    RunOrigin,
    SensorUnitInput,
    Station,
    WaferInput,
)
from yield_guardian.contracts.services import NotFoundError, NotReadyError
from yield_guardian.live.protocols import NeedsInput, SensorEngine, WaferEngine
from yield_guardian.services.runs import RunInput

log = structlog.get_logger(__name__)

SPE_WINDOW = 30
DRIFT_WINDOW = 50
WAIT_S = 20.0
RETRY_AFTER_S = 5
NOT_READY = "The case catalog is still being computed from the data. Try again shortly."


@dataclass(frozen=True, slots=True)
class Case:
    """A case and the real items it runs on."""

    case: RunCase
    unit_ids: tuple[UnitId, ...] = ()
    wafer_ids: tuple[WaferId, ...] = ()
    lot: LotId | None = None


@dataclass(slots=True)
class _Strongest:
    """The best candidate so far: a larger score wins, the first found wins a tie."""

    score: float = float("-inf")
    found: Case | None = None

    def offer(self, score: float, case: Case) -> None:
        if score > self.score:
            self.score = score
            self.found = case


def _case(
    case_id: str,
    title: str,
    description: str,
    rule: str,
    *,
    datasets: list[Dataset],
    stations: list[Station],
    unit_ids: Sequence[UnitId] = (),
    wafer_ids: Sequence[WaferId] = (),
    lot: LotId | None = None,
    wafers: int = 0,
) -> Case:
    return Case(
        case=RunCase(
            case_id=case_id,
            title=title,
            description=description,
            rule=rule,
            datasets=datasets,
            units=len(unit_ids),
            wafers=wafers or len(wafer_ids),
            stations=stations,
        ),
        unit_ids=tuple(unit_ids),
        wafer_ids=tuple(wafer_ids),
        lot=lot,
    )


SENSOR_STATIONS: list[Station] = ["manufacturing", "monitoring", "investigation", "decision"]
WAFER_STATIONS: list[Station] = ["manufacturing", "wafer_test", "investigation", "decision"]


def sensor_cases(
    engine: SensorEngine, units: Sequence[UnitId], held_out: Sequence[UnitId]
) -> list[Case]:
    """The SPE and drift cases. `units` is every SECOM unit in time order; `held_out` the test
    block in time order."""
    if not held_out:
        return []
    position = {unit: i for i, unit in enumerate(units)}
    inputs = engine.from_secom(list(held_out))
    found: list[Case] = []
    charts = engine.control_charts(inputs)
    limit = charts.limits.spe_999
    first = next((u for u in charts.units if u.spe > limit), None)
    if first is not None:
        unit = held_out[first.index]
        end = position[unit]
        window = list(units[max(0, end - (SPE_WINDOW - 1)) : end + 1])
        found.append(
            _case(
                "spe_alarm",
                "A unit that raised an SPE alarm",
                f"Unit {unit}'s sensors stopped moving together the way they do in normal "
                f"operation: its SPE {first.spe:.1f} is beyond the 99.9% control limit "
                f"{limit:.1f}. The run holds it and the {len(window) - 1} units before it.",
                "The first unit of the test block (units the risk model never saw), in time "
                "order, whose live SPE is beyond the 99.9% control limit, with the "
                f"{SPE_WINDOW - 1} units before it in time order.",
                datasets=["secom"],
                stations=SENSOR_STATIONS,
                unit_ids=window,
            )
        )
    for start in range(0, len(held_out) - DRIFT_WINDOW + 1, DRIFT_WINDOW):
        window = list(held_out[start : start + DRIFT_WINDOW])
        try:
            drift = engine.drift_health(inputs[start : start + DRIFT_WINDOW])
        except NeedsInput:
            continue
        signals = [
            (min(i for i in (g.first_ewma_alarm, g.first_cusum_alarm) if i is not None), g)
            for g in drift.groups
            if g.first_ewma_alarm is not None or g.first_cusum_alarm is not None
        ]
        if not signals:
            continue
        at, group = min(signals, key=lambda s: s[0])
        groups = len(signals)
        found.append(
            _case(
                "slow_drift",
                "A slow drift",
                f"Over these {len(window)} consecutive units, {groups} sensor group"
                f"{'s' if groups != 1 else ''} drift: the first signal is sensor group "
                f"{group.group_id} at unit {window[at]}.",
                f"The test block cut into consecutive windows of {DRIFT_WINDOW} units in time "
                "order: the first window in which a sensor group's live EWMA or CUSUM signals.",
                datasets=["secom"],
                stations=SENSOR_STATIONS,
                unit_ids=window,
            )
        )
        break
    return found


def wafer_cases(
    engine: WaferEngine, lots: Sequence[LotId], stopping: threading.Event | None = None
) -> list[Case]:
    """The scratch, unknown-pattern and lot cases, from every demo lot in name order."""
    scratch: Case | None = None
    unknown = _Strongest()
    repeat = _Strongest()
    for lot in sorted(lots):
        if stopping is not None and stopping.is_set():
            break
        wafers: list[WaferInput] = engine.from_demo(lot=lot)
        if not wafers:
            continue
        pattern = engine.pattern(wafers)
        for item in pattern.wafers:
            wafer_id = wafers[item.index].source_wafer or f"{lot}-{item.wafer}"
            if (
                scratch is None
                and item.top_label == "Scratch"
                and item.auto_accepted
                and not item.is_unknown
            ):
                scratch = _case(
                    "scratch",
                    "A wafer with a scratch",
                    f"Wafer {wafer_id}: the model auto-accepts it as Scratch "
                    f"({item.top_probability:.2%} probability, above the 99%-precision "
                    "threshold).",
                    "The first demo wafer, by lot name and then wafer number, that the live "
                    "model auto-accepts as Scratch and does not flag as unknown.",
                    datasets=["wm811k"],
                    stations=WAFER_STATIONS,
                    wafer_ids=[wafer_id],
                )
            if item.is_unknown:
                ratio = item.unknown_score / item.unknown_threshold if item.unknown_threshold else 0
                unknown.offer(
                    ratio,
                    _case(
                        "unknown_pattern",
                        "An unknown pattern",
                        f"Wafer {wafer_id} looks like no pattern the model learned: its unknown "
                        f"score {item.unknown_score:.1f} is above the threshold "
                        f"{item.unknown_threshold:.1f}, by the widest margin of all demo wafers.",
                        "Of the demo wafers the live model flags as unknown, the one with the "
                        "highest unknown score relative to its threshold.",
                        datasets=["wm811k"],
                        stations=WAFER_STATIONS,
                        wafer_ids=[wafer_id],
                    ),
                )
        if len(wafers) < 2:
            continue
        try:
            result = engine.lots(wafers, pattern)
        except NeedsInput:
            continue
        for found in result.lots:
            if not found.tests:
                continue
            test = min(found.tests, key=lambda t: t.q_value)
            title = (
                "A lot with a repeating pattern"
                if found.flagged
                else "The lot closest to a repeating pattern"
            )
            verdict = (
                "a repeat this large is unlikely to be chance"
                if found.flagged
                else "not flagged, so even the strongest repeat in the demo lots may be chance"
            )
            repeat.offer(
                -test.q_value,
                _case(
                    "lot_repeat",
                    title,
                    f"Lot {found.lot}: {test.count} of {test.wafers} wafers show {test.label}, "
                    f"against a training-period rate of {test.expected_rate:.1%} "
                    f"(q = {test.q_value:.2g}): {verdict}.",
                    "The demo lot whose live lot test, over all its wafers, has the smallest "
                    "q-value (Benjamini-Hochberg).",
                    datasets=["wm811k"],
                    stations=WAFER_STATIONS,
                    lot=lot,
                    wafers=len(wafers),
                ),
            )
    return [c for c in (scratch, unknown.found, repeat.found) if c is not None]


class CaseCatalog:
    """The catalog, computed once in a worker thread at startup (a registry Resource).

    `scan_wafers` is the wafer engine the scan uses (by default `wafers`): the live engine
    without its join-count test, whose result no rule reads. Case runs use `wafers`."""

    def __init__(
        self,
        sensors: SensorEngine | None,
        wafers: WaferEngine | None,
        *,
        units: Sequence[UnitId] = (),
        held_out: Sequence[UnitId] = (),
        lots: Sequence[LotId] = (),
        wait_s: float = WAIT_S,
        scan_wafers: WaferEngine | None = None,
    ) -> None:
        self.sensors = sensors
        self.wafers = wafers
        self.scan_wafers = scan_wafers or wafers
        self.units = list(units)
        self.held_out = list(held_out)
        self.lots = list(lots)
        self.wait_s = wait_s
        self._task: asyncio.Task[list[Case]] | None = None
        self._stopping = threading.Event()

    def build(self) -> list[Case]:
        """Every case the rules find (blocking; the catalog runs it in a worker thread)."""
        found: list[Case] = []
        if self.sensors is not None:
            try:
                found += sensor_cases(self.sensors, self.units, self.held_out)
            except Exception:
                log.exception("case_catalog_sensors_failed")
        if self.scan_wafers is not None:
            try:
                found += wafer_cases(self.scan_wafers, self.lots, self._stopping)
            except Exception:
                log.exception("case_catalog_wafers_failed")
        if self._stopping.is_set():
            log.info("case_catalog_stopped", cases=[c.case.case_id for c in found])
        else:
            log.info("case_catalog_ready", cases=[c.case.case_id for c in found])
        return found

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(asyncio.to_thread(self.build), name="case-catalog")

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None and not self._task.done():
            with contextlib.suppress(Exception):
                await asyncio.wait_for(asyncio.shield(self._task), timeout=5)

    async def cases(self) -> list[Case]:
        await self.start()
        assert self._task is not None
        try:
            return await asyncio.wait_for(asyncio.shield(self._task), timeout=self.wait_s)
        except TimeoutError as error:
            raise NotReadyError(NOT_READY, retry_after_s=RETRY_AFTER_S) from error

    async def list(self) -> RunCaseList:
        return RunCaseList(items=[c.case for c in await self.cases()])

    async def materialise(self, case_id: str) -> tuple[RunOrigin, RunInput]:
        found = next((c for c in await self.cases() if c.case.case_id == case_id), None)
        if found is None:
            raise NotFoundError(f"There is no case {case_id} in the catalog.")
        units: list[SensorUnitInput] = []
        wafers: list[WaferInput] = []
        if found.unit_ids:
            if self.sensors is None:
                raise NotReadyError("The SECOM model bundle is not loaded on this server.")
            units = await asyncio.to_thread(self.sensors.from_secom, list(found.unit_ids))
        if found.wafer_ids or found.lot is not None:
            if self.wafers is None:
                raise NotReadyError("The wafer-map model bundle is not loaded on this server.")
            wafers = await asyncio.to_thread(
                self.wafers.from_demo, list(found.wafer_ids), found.lot
            )
        origin = RunOrigin(
            source="case",
            datasets=found.case.datasets,
            title=found.case.title,
            rule=found.case.rule,
            case_id=case_id,
        )
        return origin, RunInput(units=units, wafers=wafers)
