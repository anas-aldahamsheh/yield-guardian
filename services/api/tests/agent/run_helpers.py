"""A run built from the run contract, and a RunReader double that serves it.

Every value here is a SYNTHETIC test value chosen so the tests can check the run tools'
arithmetic by hand; none is shown to anyone. Unit 3 stands for the real SECOM unit 1062 (the
unit the science fakes serve) and wafer 0 for a WM-811K wafer, so the tests can follow a run
item to the science tools.
"""

from __future__ import annotations

import base64
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from tests.agent.helpers import FakeSecom, fixture
from yield_guardian.contracts.base import BundleRef, Estimate
from yield_guardian.contracts.knowledge import PatternCauses
from yield_guardian.contracts.runs import (
    STAGE_STATION,
    ClassProbabilityItem,
    ControlChartsResult,
    DriftHealthResult,
    FdcContributionItem,
    FinalTestResult,
    FinalTestUnit,
    GroupDrift,
    IntakeResult,
    LotItem,
    LotResult,
    RiskFeature,
    Run,
    RunAlarm,
    RunOrigin,
    SensorHealthItem,
    SensorRiskResult,
    SensorUnitInput,
    SimilarItem,
    StageId,
    StageResult,
    StageState,
    UnitChartResult,
    UnitRiskResult,
    WaferInput,
    WaferPatternItem,
    WaferPatternResult,
    WaferSimilarItem,
    WaferSimilarResult,
)
from yield_guardian.contracts.secom import FdcLimits, MetricValue
from yield_guardian.contracts.wafer import PatternTest, SpatialTest, StackedMap, WaferMap

RUN_ID = "run_testcase0001"
UNITS = 25
REAL_UNIT_INDEX = 3
REAL_UNIT = 1062
FEATURES = [f"S{i:03d}" for i in range(1, 11)]
CREATED = datetime(2026, 10, 15, 8, 0, tzinfo=UTC)
GRID = 9
LOT = "L7A"


def ring_map() -> tuple[WaferMap, list[int]]:
    """A 9 x 9 disc of dies whose outer ring failed: 2 where the distance from the centre is
    above 3, 1 within it, 0 outside the disc."""
    cells = []
    for row in range(GRID):
        for col in range(GRID):
            d = math.hypot(row - 4, col - 4)
            cells.append(0 if d > 4 else 2 if d > 3 else 1)
    encoded = base64.b64encode(bytes(cells)).decode()
    return WaferMap(height=GRID, width=GRID, cells=encoded), cells


def bundle(name: str) -> BundleRef:
    return BundleRef.model_validate(
        {"name": name, "version": "v1", "created_at": CREATED, "git_commit": "abcdef0"}
    )


def unit_input(index: int) -> SensorUnitInput:
    readings: list[float | None] = [float(index + i % 7) for i in range(590)]
    readings[4] = None  # S005 missing
    return SensorUnitInput(
        unit_id="17" if index == 17 else f"U-{index}",
        timestamp=CREATED + timedelta(minutes=index),
        readings=readings,
        result="fail" if index == REAL_UNIT_INDEX else "pass",
        source_unit=REAL_UNIT if index == REAL_UNIT_INDEX else None,
    )


def _risk(index: int, label: str) -> UnitRiskResult:
    risk = 0.62 if index == REAL_UNIT_INDEX else 0.05 + index / 1000
    return UnitRiskResult(
        index=index,
        unit_id=label,
        risk=risk,
        band="high" if risk >= 0.3 else "low",
        above_threshold=risk >= 0.3,
        validity="held_out" if index == REAL_UNIT_INDEX else "new_data",
        raw_score=0.5,
        base_value=-2.0,
        top=[
            RiskFeature(feature="S001", sensor="S001", indicator=False, value=3.0, shap=0.4, group_id="G1"),
            RiskFeature(feature="S002", sensor="S002", indicator=False, value=4.0, shap=0.25, group_id="G1"),
            RiskFeature(feature="S005_missing", sensor="S005", indicator=True, value=1.0, shap=0.1, group_id="G2"),
            RiskFeature(feature="S009", sensor="S009", indicator=False, value=2.0, shap=-0.05, group_id=None),
        ],
    )  # fmt: skip


def unit_chart(index: int, *, with_z: bool = True) -> UnitChartResult:
    """The control-chart result of one unit; the run itself carries it without ``z``, as for a
    unit past the first 200, so the tests show that ``z`` comes from ``get_unit_chart``."""
    label = unit_input(index).unit_id
    big = index == REAL_UNIT_INDEX
    return UnitChartResult(
        index=index,
        unit_id=label,
        timestamp=CREATED + timedelta(minutes=index),
        t2=40.0 if big else 3.0,
        spe=90.0 if big else 2.0,
        level="alarm" if big else "none",
        top_t2=[
            FdcContributionItem(sensor="S001", contribution=12.0, share=0.3),
            FdcContributionItem(sensor="S002", contribution=8.0, share=0.2),
            FdcContributionItem(sensor="S007", contribution=4.0, share=0.1),
        ],
        top_spe=[
            FdcContributionItem(sensor="S002", contribution=45.0, share=0.5),
            FdcContributionItem(sensor="S005", contribution=9.0, share=0.1),
        ],
        z=[2.5, -3.5, 0.1, 0.2, None, 0.0, 1.5, 0.3, 0.4, 0.5] if with_z else None,
    )


def build_run() -> Run:
    labels = [unit_input(i).unit_id for i in range(UNITS)]
    wafer_map, _ = ring_map()
    causes = fixture("get_pattern_causes", PatternCauses)
    estimate = Estimate(value=0.6, ci_low=0.5, ci_high=0.7)
    stages: dict[StageId, StageResult] = {
        "intake": IntakeResult(
            units=UNITS, wafers=3, lots=1, sensors=590, missing_readings=UNITS,
            missing_share=1 / 590, first_timestamp=CREATED,
            last_timestamp=CREATED + timedelta(minutes=UNITS - 1), in_time_order=True,
            two_sources=True, unmonitored_sensors=["S011"],
        ),
        "sensor_risk": SensorRiskResult(
            units=[_risk(i, labels[i]) for i in range(UNITS)],
            threshold=0.3,
            elevated_threshold=0.2,
            operating_point="5% false-alarm rate on the validation block",
            skill=[MetricValue(metric="roc_auc", label="ROC-AUC", estimate=estimate)],
            caution="Weak risk model.",
            model=bundle("secom"),
        ),
        "control_charts": ControlChartsResult(
            limits=FdcLimits(t2_99=20.0, t2_999=30.0, spe_99=50.0, spe_999=80.0),
            n_components=4,
            explained_variance=0.7,
            features=FEATURES,
            units=[unit_chart(i, with_z=False) for i in range(UNITS)],
            method="PCA T² and SPE",
            model=bundle("secom"),
        ),
        "drift_health": DriftHealthResult(
            groups=[
                GroupDrift(
                    group_id="G1", sensors=["S001", "S002", "S003"],
                    ewma=[0.1 * i for i in range(UNITS)], ewma_limit=1.0,
                    cusum_upper=[0.5 * i for i in range(UNITS)],
                    cusum_lower=[0.0] * UNITS, cusum_h=5.0,
                    first_ewma_alarm=11, first_cusum_alarm=None,
                )
            ],
            ewma_lambda=0.2, ewma_width=2.962, cusum_k=0.5,
            health=[SensorHealthItem(sensor="S002", status="watch", reasons=["jumps"])],
            health_counts={"ok": 588, "watch": 1, "dead": 1},
            rules=["jumps"], method="EWMA and CUSUM",
        ),
        "wafer_pattern": WaferPatternResult(
            wafers=[
                WaferPatternItem(
                    index=i, lot=LOT, wafer=i + 1, map=wafer_map,
                    source_wafer="lot47542-12" if i == 0 else None,
                    top_label="Edge-Ring", top_probability=0.93 - i / 100,
                    probabilities=[ClassProbabilityItem(label="Edge-Ring", probability=0.93 - i / 100)],
                    auto_accepted=i == 0, unknown_score=4.0, unknown_threshold=9.0,
                    is_unknown=False, energy_score=-3.0,
                    spatial=SpatialTest(statistic=40.0, expected=20.0, p_value=0.001, permutations=999, clustered=True),
                    recorded_label="Edge-Ring" if i == 0 else None,
                )
                for i in range(3)
            ],
            accept_threshold=0.9, temperature=1.2, method="CNN", model=bundle("wafermap"),
        ),
        "wafer_similar": WaferSimilarResult(
            wafers=[
                WaferSimilarItem(
                    index=i,
                    similar=[
                        SimilarItem(wafer_id="lot1-1", recorded_label="Edge-Ring", predicted_label="Edge-Ring", similarity=0.97, map=wafer_map),
                        SimilarItem(wafer_id="lot1-2", recorded_label="Edge-Ring", predicted_label="Edge-Ring", similarity=0.95, map=wafer_map),
                        SimilarItem(wafer_id="lot2-5", recorded_label="Center", predicted_label="Edge-Ring", similarity=0.9, map=wafer_map),
                        SimilarItem(wafer_id="lot3-7", recorded_label=None, predicted_label="Edge-Ring", similarity=0.88, map=wafer_map),
                    ],
                )
                for i in range(3)
            ],
            searched=10253, precision_at_10=estimate, causes=causes, method="cosine",
        ),
        "lot": LotResult(
            lots=[
                LotItem(
                    lot=LOT, wafers=3, pattern_counts={"Edge-Ring": 3},
                    tests=[PatternTest(label="Edge-Ring", count=3, wafers=3, expected_rate=0.05, p_value=0.0001, q_value=0.0008, flagged=True)],
                    flagged=True,
                    stacked=StackedMap(
                        height=GRID, width=GRID, wafers=3,
                        frequencies=[
                            None if v == 0 else (1.0 if v == 2 else 0.0) for v in ring_map()[1]
                        ],
                    ),
                )
            ],
            method="binomial, BH",
        ),
        "final_test": FinalTestResult(
            units=[FinalTestUnit(index=i, unit_id=labels[i], result="pass", flagged=False) for i in range(UNITS)],
            wafers=[], units_with_result=UNITS, failed_units=1, failed_flagged=1,
            passed_flagged=0, wafers_with_label=1, wafers_agreeing=1,
            summary="The failed unit was flagged.",
        ),
    }  # fmt: skip
    alarms = [
        RunAlarm(
            alarm_id="RA-1", run_id=RUN_ID, stage="control_charts", kind="spe",
            severity="alarm", unit_index=REAL_UNIT_INDEX, unit_id=labels[REAL_UNIT_INDEX],
            value=90.0, limit=80.0, title="Sensor relationships broke (SPE)",
            meaning="The unit's readings do not fit the usual relationships.", sensors=["S002", "S005"],
        ),
        RunAlarm(
            alarm_id="RA-2", run_id=RUN_ID, stage="wafer_pattern", kind="wafer_pattern",
            severity="warning", wafer_index=0, lot=LOT, value=0.93, limit=0.9,
            title="Edge-Ring pattern", meaning="The wafer shows an Edge-Ring pattern.",
        ),
        RunAlarm(
            alarm_id="RA-3", run_id=RUN_ID, stage="lot", kind="lot_excursion", severity="alarm",
            lot=LOT, value=0.0008, limit=0.05, title="Pattern repeats in the lot",
            meaning="Edge-Ring repeats more often than the reference rate.",
        ),
    ]  # fmt: skip
    return Run(
        run_id=RUN_ID,
        created_at=CREATED,
        status="done",
        origin=RunOrigin(
            source="pick",
            datasets=["secom", "wm811k"],
            title="Picked items",
            rule="Items picked in the dataset browsers.",
        ),
        units=UNITS,
        wafers=3,
        stages=[
            StageState(stage=s, station=STAGE_STATION[s], status="done", result=r)
            for s, r in stages.items()
        ],
        alarms=alarms,
        expires_at=CREATED + timedelta(hours=24),
    )


def wafer_input(index: int) -> WaferInput:
    wafer_map, _ = ring_map()
    return WaferInput(
        lot=LOT,
        wafer=index + 1,
        map=wafer_map,
        label="Edge-Ring" if index == 0 else None,
        source_wafer="lot47542-12" if index == 0 else None,
    )


@dataclass
class FakeRuns:
    """RunReader double: one stored run; records every read."""

    run: Run = field(default_factory=build_run)
    calls: list[tuple[str, str, int | None]] = field(default_factory=list)

    async def get_run(self, run_id: str) -> Run | None:
        self.calls.append(("get_run", run_id, None))
        return self.run if run_id == self.run.run_id else None

    async def get_unit_chart(self, run_id: str, index: int) -> UnitChartResult | None:
        self.calls.append(("get_unit_chart", run_id, index))
        if run_id != self.run.run_id or not 0 <= index < self.run.units:
            return None
        return unit_chart(index)

    async def get_unit_input(self, run_id: str, index: int) -> SensorUnitInput | None:
        self.calls.append(("get_unit_input", run_id, index))
        if run_id != self.run.run_id or not 0 <= index < self.run.units:
            return None
        return unit_input(index)

    async def get_wafer_input(self, run_id: str, index: int) -> WaferInput | None:
        self.calls.append(("get_wafer_input", run_id, index))
        if run_id != self.run.run_id or not 0 <= index < self.run.wafers:
            return None
        return wafer_input(index)


class LineSecom(FakeSecom):
    """A SECOM double with a visibility cursor, like the real service."""

    def __init__(self) -> None:
        super().__init__()
        self.timeline = list(range(1567))
        self.positions: list[int] = []

    def as_of(self, position: int) -> LineSecom:
        self.positions.append(position)
        return self
