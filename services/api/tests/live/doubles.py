"""Test doubles and real-bundle loaders for the run tests.

The sensor track uses the real SECOM engine on real SECOM units (wrapped when a test needs to
slow it down, record it or make it fail). The wafer engine (V3) is a double here until it is
on main: it labels the test's wafers as each test says, with no model behind it.
"""

import base64
import functools
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from random import Random

import pyarrow.parquet as pq

from yield_guardian.bundles.manifest import latest_version, verify_bundle
from yield_guardian.bundles.secom import SecomBundle, load_secom_bundle
from yield_guardian.bundles.wafermap import LABELS
from yield_guardian.contracts.base import BundleRef, LotId, SensorId, UnitId, WaferId
from yield_guardian.contracts.knowledge import PatternCauses
from yield_guardian.contracts.runs import (
    ClassProbabilityItem,
    ControlChartsResult,
    DriftHealthResult,
    LotItem,
    LotResult,
    RunAlarm,
    RunEventPayload,
    RunStatus,
    SensorRiskResult,
    SensorUnitInput,
    StageState,
    UnitChartResult,
    WaferInput,
    WaferPatternItem,
    WaferPatternResult,
    WaferSimilarItem,
    WaferSimilarResult,
)
from yield_guardian.contracts.services import NotFoundError
from yield_guardian.contracts.wafer import PatternTest, WaferLabel, WaferMap
from yield_guardian.live.protocols import DrawLayout, Picked, SensorEngine
from yield_guardian.live.sensors import SecomSensorEngine
from yield_guardian.services.runs import EventFactory

REPO = Path(__file__).resolve().parents[4]
ARTIFACTS = REPO / "artifacts"
SECOM_DATA = REPO / "data" / "secom"


@functools.cache
def real_secom() -> SecomBundle:
    return load_secom_bundle(verify_bundle(latest_version(ARTIFACTS, "secom"), "secom"), SECOM_DATA)


@functools.cache
def real_sensor_engine() -> SecomSensorEngine:
    return SecomSensorEngine(real_secom())


def held_out_ids() -> list[UnitId]:
    """The SECOM test block (units the risk model never saw), in time order."""
    timeline = real_secom().timeline
    return [
        int(u)
        for u, block in zip(timeline.unit_id.tolist(), timeline.block, strict=True)
        if block == "test"
    ]


WAFERMAP_DEMO = ARTIFACTS / "wafermap" / "v1" / "demo"


def demo_wafers(lot: LotId) -> list[WaferInput]:
    """Every real demo wafer of `lot` (artifacts/wafermap/v1/demo/wafers.parquet), as input,
    with its recorded label. Read directly: loading the whole bundle takes about 20 s."""
    frame = pq.read_table(WAFERMAP_DEMO / "wafers.parquet", filters=[("lot", "=", lot)])
    rows = sorted(frame.to_pylist(), key=lambda r: int(r["wafer_index"]))
    return [
        WaferInput(
            lot=str(r["lot"]),
            wafer=int(r["wafer_index"]),
            map=WaferMap(
                height=int(r["height"]),
                width=int(r["width"]),
                cells=base64.b64encode(bytes(r["map"])).decode(),
            ),
            label=r["label"] if r["label"] in LABELS else None,
            source_wafer=str(r["wafer_id"]),
        )
        for r in rows
    ]


def small_wafer(
    lot: str, wafer: int, fails: Sequence[int] = (), label: WaferLabel | None = None
) -> WaferInput:
    """A 3 x 3 wafer built in the test: every cell a die, `fails` (cell numbers) failing."""
    cells = bytes(2 if i in fails else 1 for i in range(9))
    return WaferInput(
        lot=lot,
        wafer=wafer,
        map=WaferMap(height=3, width=3, cells=base64.b64encode(cells).decode()),
        label=label,
    )


# The orchestrator's writer ---------------------------------------------------------------------


@dataclass
class MemoryWriter:
    """RunWriter in memory: events get seq 2, 3, ... (seq 1 is the stored run_started)."""

    events: list[RunEventPayload] = field(default_factory=list)
    stages: dict[str, StageState] = field(default_factory=dict)
    statuses: list[RunStatus] = field(default_factory=list)
    alarms: list[RunAlarm] = field(default_factory=list)
    not_listed: int = 0
    unit_charts: list[UnitChartResult] = field(default_factory=list)
    heartbeats: int = 0

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
        if status is not None:
            self.statuses.append(status)
        if stage is not None:
            self.stages[stage.stage] = stage
        self.alarms += alarms
        self.not_listed += not_listed
        self.unit_charts += unit_charts
        for make in events:
            self.events.append(make(len(self.events) + 2, datetime.now(UTC)))

    async def heartbeat(self, run_id: str) -> None:
        self.heartbeats += 1

    def kinds(self) -> list[tuple[str, str | None]]:
        return [(e.type, getattr(e, "stage", None)) for e in self.events]


# Engines -------------------------------------------------------------------------------------


@dataclass
class Calls:
    """Which engine call ran when (perf_counter), across threads."""

    spans: list[tuple[str, float, float]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def timed[T](self, name: str, delay: float, call: Callable[[], T]) -> T:
        started = time.perf_counter()
        try:
            time.sleep(delay)
            return call()
        finally:
            with self.lock:
                self.spans.append((name, started, time.perf_counter()))


class Wrapped:
    """A SensorEngine around a real one: each stage call can wait `delay` seconds first (to
    show the timing), or raise what `fail` gives for it."""

    def __init__(
        self,
        inner: SensorEngine,
        calls: Calls | None = None,
        *,
        delay: float = 0.0,
        fail: dict[str, Exception] | None = None,
    ) -> None:
        self.inner = inner
        self.calls = calls or Calls()
        self.delay = delay
        self.fail = fail or {}

    def _call[T](self, name: str, call: Callable[[], T]) -> T:
        def run() -> T:
            if name in self.fail:
                raise self.fail[name]
            return call()

        return self.calls.timed(name, self.delay, run)

    def unmonitored_sensors(self) -> list[SensorId]:
        return self.inner.unmonitored_sensors()

    def risk(self, units: Sequence[SensorUnitInput]) -> SensorRiskResult:
        return self._call("sensor_risk", lambda: self.inner.risk(units))

    def control_charts(self, units: Sequence[SensorUnitInput]) -> ControlChartsResult:
        return self._call("control_charts", lambda: self.inner.control_charts(units))

    def drift_health(self, units: Sequence[SensorUnitInput]) -> DriftHealthResult:
        return self._call("drift_health", lambda: self.inner.drift_health(units))

    def from_secom(self, unit_ids: Sequence[UnitId]) -> list[SensorUnitInput]:
        return self.inner.from_secom(unit_ids)

    def sample(self, rng: Random) -> Picked[SensorUnitInput]:
        return self.inner.sample(rng)


DOUBLE_REF = BundleRef(
    name="wafermap",
    version="v1",
    created_at=datetime(2026, 10, 14, tzinfo=UTC),
    git_commit="0000000",
)


@dataclass
class WaferCall:
    """What the double says about one wafer, keyed by (lot, wafer)."""

    label: WaferLabel = "none"
    probability: float = 0.95
    accepted: bool = True
    unknown_score: float = 1.0
    unknown_threshold: float = 10.0


class WaferDouble:
    """WaferEngine double: `calls` decide each wafer's pattern; `q` each lot's smallest q-value
    (flagged below 0.05); `demo` is what from_demo and sample serve."""

    def __init__(
        self,
        *,
        calls: dict[tuple[str, int], WaferCall] | None = None,
        q: dict[str, float] | None = None,
        demo: dict[str, list[WaferInput]] | None = None,
        timing: Calls | None = None,
        delay: float = 0.0,
        fail: dict[str, Exception] | None = None,
    ) -> None:
        self.calls = calls or {}
        self.q = q or {}
        self.demo = demo or {}
        self.timing = timing or Calls()
        self.delay = delay
        self.fail = fail or {}

    def _run[T](self, name: str, call: Callable[[], T]) -> T:
        def run() -> T:
            if name in self.fail:
                raise self.fail[name]
            return call()

        return self.timing.timed(name, self.delay, run)

    def pattern(self, wafers: Sequence[WaferInput]) -> WaferPatternResult:
        def compute() -> WaferPatternResult:
            items: list[WaferPatternItem] = []
            for i, w in enumerate(wafers):
                said = self.calls.get((w.lot, w.wafer), WaferCall())
                items.append(
                    WaferPatternItem(
                        index=i,
                        lot=w.lot,
                        wafer=w.wafer,
                        map=w.map,
                        source_wafer=w.source_wafer,
                        top_label=said.label,
                        top_probability=said.probability,
                        probabilities=[
                            ClassProbabilityItem(label=said.label, probability=said.probability)
                        ],
                        auto_accepted=said.accepted,
                        unknown_score=said.unknown_score,
                        unknown_threshold=said.unknown_threshold,
                        is_unknown=said.unknown_score > said.unknown_threshold,
                        energy_score=0.0,
                        spatial=None,
                        recorded_label=w.label,
                    )
                )
            return WaferPatternResult(
                wafers=items,
                accept_threshold=0.9,
                temperature=1.0,
                method="test double",
                model=DOUBLE_REF,
            )

        return self._run("wafer_pattern", compute)

    def similar(
        self, wafers: Sequence[WaferInput], pattern: WaferPatternResult
    ) -> WaferSimilarResult:
        return self._run(
            "wafer_similar",
            lambda: WaferSimilarResult(
                wafers=[WaferSimilarItem(index=i, similar=[]) for i in range(len(wafers))],
                searched=0,
                precision_at_10=None,
                causes=PatternCauses(framing="test double", causes=[], sources=[]),
                method="test double",
            ),
        )

    def lots(self, wafers: Sequence[WaferInput], pattern: WaferPatternResult) -> LotResult:
        def compute() -> LotResult:
            items: list[LotItem] = []
            for lot in dict.fromkeys(w.lot for w in wafers):
                members = [p for p in pattern.wafers if p.lot == lot]
                q = self.q.get(lot, 1.0)
                label = members[0].top_label if members else "none"
                count = sum(p.top_label == label for p in members)
                test = PatternTest(
                    label=label,
                    count=count,
                    wafers=len(members),
                    expected_rate=0.05,
                    p_value=q,
                    q_value=q,
                    flagged=q < 0.05,
                )
                items.append(
                    LotItem(
                        lot=lot,
                        wafers=len(members),
                        pattern_counts={label: count},
                        tests=[test],
                        flagged=test.flagged,
                        stacked=None,
                    )
                )
            return LotResult(lots=items, method="test double")

        return self._run("lot", compute)

    def from_demo(
        self, wafer_ids: Sequence[WaferId] = (), lot: LotId | None = None
    ) -> list[WaferInput]:
        every = [w for lot_wafers in self.demo.values() for w in lot_wafers]
        by_id = {w.source_wafer: w for w in every}
        missing = [i for i in wafer_ids if i not in by_id]
        if missing:
            raise NotFoundError(f"Wafer {missing[0]} is not in the demo set.")
        chosen = [by_id[i] for i in wafer_ids]
        if lot is not None:
            if lot not in self.demo:
                raise NotFoundError(f"Lot {lot} is not in the demo set.")
            chosen += [w for w in self.demo[lot] if w not in chosen]
        return chosen

    def sample(self, rng: Random) -> Picked[WaferInput]:
        lot = sorted(self.demo)[rng.randrange(len(self.demo))]
        return Picked(items=list(self.demo[lot]), rule=f"Every demo wafer of lot {lot}.")

    def draw_layouts(self) -> list[DrawLayout]:
        return []
