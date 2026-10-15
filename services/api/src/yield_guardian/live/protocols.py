"""The seams between the run orchestrator and the engines (PLAN_V2 §3, §10).

Engines are synchronous and pure: they load their bundle once at startup and then compute from
the input alone, with no I/O and no stored per-unit results. The orchestrator calls them in a
worker thread, one stage at a time, and streams each result as soon as it returns.

A stage that cannot run on the given input raises `NeedsInput` with a plain sentence that the
page shows on the grey station ("needs at least 20 units in time order").
"""

from collections.abc import Sequence
from dataclasses import dataclass
from random import Random
from typing import Protocol

from yield_guardian.contracts.base import LotId, SensorId, UnitId, WaferId
from yield_guardian.contracts.knowledge import PatternCauses
from yield_guardian.contracts.runs import (
    ControlChartsResult,
    DriftHealthResult,
    LotResult,
    Run,
    SensorRiskResult,
    SensorUnitInput,
    UnitChartResult,
    UploadIssue,
    WaferInput,
    WaferPatternResult,
    WaferSimilarResult,
)
from yield_guardian.contracts.wafer import WaferLabel, WaferMap


class NeedsInput(Exception):  # noqa: N818 - it is a condition, not an error
    """The stage cannot run on this input; `needs` says what is missing, in plain words."""

    def __init__(self, needs: str) -> None:
        super().__init__(needs)
        self.needs = needs


@dataclass(frozen=True, slots=True)
class Picked[T]:
    """Real items taken from a dataset, with the rule that chose them (shown on the page)."""

    items: list[T]
    rule: str


@dataclass(frozen=True, slots=True)
class Parsed[T]:
    """A parsed file: the items, and every problem found (errors block the run)."""

    items: list[T]
    issues: list[UploadIssue]


@dataclass(frozen=True, slots=True)
class DrawLayout:
    """An empty wafer to draw on: the die layout (0 no die, 1 pass) of a real WM-811K wafer."""

    layout_id: str
    map: WaferMap
    source_wafer: WaferId
    rule: str


class SensorEngine(Protocol):
    """SECOM models (artifacts/secom): LightGBM risk, TreeSHAP, PCA T²/SPE, EWMA/CUSUM, health."""

    def unmonitored_sensors(self) -> list[SensorId]: ...

    def risk(self, units: Sequence[SensorUnitInput]) -> SensorRiskResult: ...

    def control_charts(self, units: Sequence[SensorUnitInput]) -> ControlChartsResult: ...

    def drift_health(self, units: Sequence[SensorUnitInput]) -> DriftHealthResult: ...

    def from_secom(self, unit_ids: Sequence[UnitId]) -> list[SensorUnitInput]:
        """The real SECOM rows, as input, in time order, with recorded results."""
        ...

    def sample(self, rng: Random) -> Picked[SensorUnitInput]:
        """A random window of consecutive real units the risk model never saw."""
        ...


class WaferEngine(Protocol):
    """WM-811K model (artifacts/wafermap): ONNX CNN, Mahalanobis unknown, similarity, lot tests."""

    def pattern(self, wafers: Sequence[WaferInput]) -> WaferPatternResult: ...

    def similar(
        self, wafers: Sequence[WaferInput], pattern: WaferPatternResult
    ) -> WaferSimilarResult: ...

    def lots(self, wafers: Sequence[WaferInput], pattern: WaferPatternResult) -> LotResult: ...

    def from_demo(
        self, wafer_ids: Sequence[WaferId] = (), lot: LotId | None = None
    ) -> list[WaferInput]:
        """Real demo wafers, as input, with their recorded labels."""
        ...

    def sample(self, rng: Random) -> Picked[WaferInput]:
        """All wafers of one random real lot."""
        ...

    def draw_layouts(self) -> list[DrawLayout]: ...


class PatternCausesSource(Protocol):
    """Literature causes per pattern (docs/knowledge/pattern_causes.json)."""

    def causes(self, labels: Sequence[WaferLabel]) -> PatternCauses: ...


class SensorFileParser(Protocol):
    """unit_id, timestamp, S001..S590, result? as CSV or XLSX."""

    def parse(self, data: bytes, filename: str) -> Parsed[SensorUnitInput]: ...


class WaferFileParser(Protocol):
    """lot, wafer, x, y, result as CSV or XLSX; positions not listed are no die."""

    def parse(self, data: bytes, filename: str) -> Parsed[WaferInput]: ...


class RunReader(Protocol):
    """Read access to stored runs for the investigator and the chat (PLAN_V2 §3.4, §8).

    The run store implements it. Reads are per item so a 5,000-unit run is never loaded whole
    for one question.
    """

    async def get_run(self, run_id: str) -> Run | None:
        """The run as GET /runs/{run_id} returns it: every stage state and result (z for at
        most the first 200 units, as streamed) and every listed alarm. None when absent or
        expired."""
        ...

    async def get_unit_chart(self, run_id: str, index: int) -> UnitChartResult | None:
        """Control-chart result of unit `index` with `z` (every monitored sensor's standardised
        reading), for any unit of the run. None when absent or not computed."""
        ...

    async def get_unit_input(self, run_id: str, index: int) -> SensorUnitInput | None:
        """Sensor unit `index` (0-based position in the run input). None when absent."""
        ...

    async def get_wafer_input(self, run_id: str, index: int) -> WaferInput | None:
        """Wafer `index` (0-based position in the run input). None when absent."""
        ...
