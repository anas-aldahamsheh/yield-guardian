"""Live runs: one submission of real or user data, processed now, stage by stage, streamed as SSE.

A run is what the Line page shows. The input is a list of sensor units (SECOM layout: 590
sensors) and/or a list of wafer maps (WM-811K values: 0 no die, 1 pass, 2 fail). Every stage
computes its result from the input at request time with the deployed models; nothing is read
from a stored replay. A stage that lacks the input it needs is skipped and says what it needs.

The five stations the page draws group the stages:

    manufacturing  intake
    monitoring     sensor_risk, control_charts, drift_health
    wafer_test     wafer_pattern, wafer_similar, lot
    (both tracks)  final_test, when the input carries recorded results
    investigation  on demand, from an alarm (POST /investigations, trigger kind "run_alarm")
    decision       approve or reject the report (existing investigation decision)

SECOM and WM-811K are real data from different sources: a run never links a wafer map to a
sensor unit, and `IntakeResult.two_sources` tells the page to say so.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, RootModel, StringConstraints

from yield_guardian.contracts.base import (
    BundleRef,
    Contract,
    Count,
    Estimate,
    LotId,
    Probability,
    Problem,
    SensorId,
    Share,
    UnitId,
    WaferId,
)
from yield_guardian.contracts.knowledge import PatternCauses
from yield_guardian.contracts.line import FdcAlarmLevel, RiskBand
from yield_guardian.contracts.secom import FdcLimits, MetricValue, SensorStatus
from yield_guardian.contracts.wafer import (
    PatternTest,
    SpatialTest,
    StackedMap,
    WaferLabel,
    WaferMap,
)

N_SENSORS = 590
MAX_UNITS = 5000
MAX_WAFERS = 500
MIN_UNITS_FOR_DRIFT = 20

RunId = Annotated[
    str,
    StringConstraints(pattern=r"^run_[0-9a-z]{8,40}$"),
    Field(examples=["run_01jaf3k9x2m4q7r8s0t1v2w3x4"]),
]
UploadId = Annotated[
    str,
    StringConstraints(pattern=r"^upl_[0-9a-z]{8,40}$"),
    Field(examples=["upl_01jaf3k9x2m4q7r8s0t1v2w3x4"]),
]
RunAlarmId = Annotated[
    str,
    StringConstraints(pattern=r"^RA-\d{1,6}$"),
    Field(description="Alarm within one run, numbered in the order raised.", examples=["RA-3"]),
]
UserLabel = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:\- ]+$"),
    Field(description="A name from the user's file (unit_id or lot), kept as written."),
]

RunSource = Literal["sample", "case", "pick", "drawn", "upload"]
Dataset = Literal["secom", "wm811k", "user"]
RunStatus = Literal["queued", "running", "done", "failed"]
Station = Literal["manufacturing", "monitoring", "wafer_test", "investigation", "decision"]
StageId = Literal[
    "intake",
    "sensor_risk",
    "control_charts",
    "drift_health",
    "wafer_pattern",
    "wafer_similar",
    "lot",
    "final_test",
]
StageStatus = Literal["pending", "running", "done", "skipped", "failed"]
RunAlarmKind = Literal[
    "risk", "t2", "spe", "ewma", "cusum", "wafer_pattern", "unknown_pattern", "lot_excursion"
]
RunAlarmSeverity = Literal["warning", "alarm"]
RiskValidity = Literal["held_out", "in_training", "new_data"]
UploadKind = Literal["sensors", "wafers"]
FinalResult = Literal["pass", "fail"]

STAGE_STATION: dict[StageId, Station] = {
    "intake": "manufacturing",
    "sensor_risk": "monitoring",
    "control_charts": "monitoring",
    "drift_health": "monitoring",
    "wafer_pattern": "wafer_test",
    "wafer_similar": "wafer_test",
    "lot": "wafer_test",
    "final_test": "monitoring",
}


# ---------------------------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------------------------


class SensorUnitInput(Contract):
    """One production unit in the SECOM layout."""

    unit_id: UserLabel
    timestamp: datetime | None = Field(None, description="Time of the unit; needed for drift.")
    readings: list[float | None] = Field(
        min_length=N_SENSORS,
        max_length=N_SENSORS,
        description="S001..S590 in order; null is a missing reading.",
    )
    result: FinalResult | None = Field(None, description="Recorded final-test result, if known.")
    source_unit: UnitId | None = Field(
        None, description="The SECOM row this unit is, when it comes from the real dataset."
    )


class WaferInput(Contract):
    """One wafer map with WM-811K values (0 no die, 1 pass, 2 fail)."""

    lot: UserLabel
    wafer: int = Field(ge=1, le=10_000)
    map: WaferMap
    label: WaferLabel | None = Field(
        None, description="Recorded WM-811K label, when the wafer comes from the real dataset."
    )
    source_wafer: WaferId | None = Field(
        None, description="The WM-811K wafer this is, when it comes from the real dataset."
    )


class RunOrigin(Contract):
    """Where the input came from, in words the page can show as is."""

    source: RunSource
    datasets: list[Dataset] = Field(min_length=1)
    title: str = Field(max_length=200, examples=["A random real sample"])
    rule: str = Field(
        max_length=600,
        description="How the input was chosen or built, e.g. the selection rule and its seed.",
    )
    case_id: str | None = None
    filename: str | None = Field(None, max_length=255)
    seed: int | None = None


class SampleRunCreate(Contract):
    """One click: the server picks real SECOM units and a real WM-811K lot at random."""

    source: Literal["sample"]
    seed: int | None = Field(
        None, ge=0, le=2**31 - 1, description="Repeat an earlier pick; omitted picks a new one."
    )


class CaseRunCreate(Contract):
    source: Literal["case"]
    case_id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]{1,40}$")]


class PickRunCreate(Contract):
    """Real items the user chose from the dataset browsers."""

    source: Literal["pick"]
    unit_ids: list[UnitId] = Field(default_factory=list, max_length=MAX_UNITS)
    wafer_ids: list[WaferId] = Field(default_factory=list, max_length=MAX_WAFERS)
    lot: LotId | None = Field(None, description="All demo wafers of this lot.")


class DrawnRunCreate(Contract):
    """Wafers the user painted; each map is labelled as the user's drawing on the page."""

    source: Literal["drawn"]
    wafers: list[WaferInput] = Field(min_length=1, max_length=25)


class UploadRunCreate(Contract):
    source: Literal["upload"]
    upload_id: UploadId


RunCreatePayload = (
    SampleRunCreate | CaseRunCreate | PickRunCreate | DrawnRunCreate | UploadRunCreate
)


class RunCreate(RootModel[Annotated[RunCreatePayload, Field(discriminator="source")]]):
    """Body of POST /runs, discriminated by `source`."""


class RunCreated(Contract):
    run_id: RunId
    events_url: str = Field(examples=["/api/v1/runs/run_01jaf3k9x2m4q7r8s0t1v2w3x4/events"])
    origin: RunOrigin


class RunCase(Contract):
    """A real situation found in the data by a fixed rule (not made up)."""

    case_id: str
    title: str
    description: str
    rule: str = Field(description="The rule that found it in the data.")
    datasets: list[Dataset]
    units: Count
    wafers: Count
    stations: list[Station] = Field(description="Stations this case exercises.")


class RunCaseList(Contract):
    items: list[RunCase]


class DrawLayoutItem(Contract):
    """An empty wafer to draw on: the die layout (0 no die, 1 pass) of a real WM-811K wafer."""

    layout_id: str
    map: WaferMap
    source_wafer: WaferId
    rule: str = Field(description="How this layout was chosen from the data.")


class DrawLayoutList(Contract):
    items: list[DrawLayoutItem]


class UploadIssue(Contract):
    severity: Literal["error", "warning"]
    row: int | None = Field(description="1-based row in the file (the header is row 1).")
    column: str | None
    message: str


class UploadSummary(Contract):
    """A parsed and validated file, ready to run. Errors block the run; warnings do not."""

    upload_id: UploadId
    kind: UploadKind
    filename: str
    units: Count
    wafers: Count
    lots: Count
    missing_readings: Count
    issues: list[UploadIssue]
    runnable: bool
    expires_at: datetime


# ---------------------------------------------------------------------------------------------
# Stage results
# ---------------------------------------------------------------------------------------------


class IntakeResult(Contract):
    stage: Literal["intake"] = "intake"
    units: Count
    wafers: Count
    lots: Count
    sensors: Count = Field(description="Sensor columns per unit (590 in the SECOM layout).")
    missing_readings: Count
    missing_share: Share
    first_timestamp: datetime | None
    last_timestamp: datetime | None
    in_time_order: bool = Field(description="Units carry timestamps that never go back.")
    two_sources: bool = Field(
        description="Both SECOM units and WM-811K wafers are present: they are different chips."
    )
    unmonitored_sensors: list[SensorId] = Field(
        description="Sensors the models do not use (constant or empty in training)."
    )


class RiskFeature(Contract):
    feature: str
    sensor: SensorId
    indicator: bool = Field(description="True for a missingness indicator feature.")
    value: float | None
    shap: float = Field(description="TreeSHAP contribution in log-odds.")
    group_id: str | None


class UnitRiskResult(Contract):
    index: Count = Field(description="Position of the unit in the run input.")
    unit_id: UserLabel
    risk: Probability
    band: RiskBand
    above_threshold: bool
    validity: RiskValidity = Field(
        description="held_out: a SECOM unit the model never saw; in_training: a SECOM unit the "
        "model was fitted on (in-sample); new_data: not a SECOM unit."
    )
    raw_score: float
    base_value: float
    top: list[RiskFeature] = Field(description="Largest |shap| first.", max_length=15)


class SensorRiskResult(Contract):
    stage: Literal["sensor_risk"] = "sensor_risk"
    units: list[UnitRiskResult]
    threshold: Probability = Field(description="Operating point chosen on the validation block.")
    operating_point: str = Field(examples=["5% false-alarm rate on the validation block"])
    elevated_threshold: Probability = Field(
        description="Lower edge of the elevated band (10% false-alarm rate on the validation block)."
    )
    skill: list[MetricValue] = Field(
        description="Held-out test skill of this model (ROC-AUC, PR-AUC): shown next to every risk."
    )
    caution: str = Field(description="Plain sentence on how weak the risk is.")
    model: BundleRef


class FdcContributionItem(Contract):
    sensor: SensorId
    contribution: float
    share: Share


class UnitChartResult(Contract):
    index: Count
    unit_id: UserLabel
    timestamp: datetime | None = Field(None, description="The unit's time, when the input has it.")
    t2: float = Field(ge=0)
    spe: float = Field(ge=0)
    level: FdcAlarmLevel
    top_t2: list[FdcContributionItem] = Field(max_length=10)
    top_spe: list[FdcContributionItem] = Field(max_length=10)
    z: list[float | None] | None = Field(
        None,
        description="Standardised reading of each monitored sensor (order of `features`), null "
        "where missing. Sent for at most the first 200 units; GET the run for the rest.",
    )


class ControlChartsResult(Contract):
    stage: Literal["control_charts"] = "control_charts"
    limits: FdcLimits
    n_components: Count
    explained_variance: Share
    features: list[SensorId] = Field(description="Monitored sensors, in model order.")
    units: list[UnitChartResult]
    method: str
    model: BundleRef


class GroupDrift(Contract):
    group_id: str
    sensors: list[SensorId]
    ewma: list[float] = Field(description="EWMA of the standardised group score, per unit.")
    ewma_limit: float
    cusum_upper: list[float]
    cusum_lower: list[float]
    cusum_h: float
    first_ewma_alarm: Count | None = Field(description="Index of the first unit over the limit.")
    first_cusum_alarm: Count | None


class SensorHealthItem(Contract):
    sensor: SensorId
    status: SensorStatus
    reasons: list[str]


class DriftHealthResult(Contract):
    stage: Literal["drift_health"] = "drift_health"
    groups: list[GroupDrift]
    ewma_lambda: float
    ewma_width: float
    cusum_k: float
    health: list[SensorHealthItem] = Field(description="Sensors not ok; ok sensors are omitted.")
    health_counts: dict[SensorStatus, Count]
    rules: list[str]
    method: str


class ClassProbabilityItem(Contract):
    label: WaferLabel
    probability: Probability


class WaferPatternItem(Contract):
    index: Count = Field(description="Position of the wafer in the run input.")
    lot: UserLabel
    wafer: int
    map: WaferMap = Field(
        description="The map as processed: the run's input grid (0 no die, 1 pass, 2 fail)."
    )
    source_wafer: WaferId | None = Field(
        None, description="The WM-811K wafer this is, when it comes from the real dataset."
    )
    top_label: WaferLabel
    top_probability: Probability
    probabilities: list[ClassProbabilityItem] = Field(description="Calibrated, highest first.")
    auto_accepted: bool = Field(
        description="Top probability clears the threshold set for 99% precision on validation."
    )
    unknown_score: float
    unknown_threshold: float
    is_unknown: bool
    energy_score: float
    spatial: SpatialTest | None
    recorded_label: WaferLabel | None


class WaferPatternResult(Contract):
    stage: Literal["wafer_pattern"] = "wafer_pattern"
    wafers: list[WaferPatternItem]
    accept_threshold: Probability
    temperature: float = Field(gt=0)
    method: str
    model: BundleRef


class SimilarItem(Contract):
    wafer_id: WaferId
    recorded_label: WaferLabel | None
    predicted_label: WaferLabel
    similarity: float = Field(ge=-1.0, le=1.0)
    map: WaferMap


class WaferSimilarItem(Contract):
    index: Count
    similar: list[SimilarItem] = Field(max_length=10, description="Most similar first.")


class WaferSimilarResult(Contract):
    stage: Literal["wafer_similar"] = "wafer_similar"
    wafers: list[WaferSimilarItem]
    searched: Count = Field(description="Real WM-811K wafers searched.")
    precision_at_10: Estimate | None
    causes: PatternCauses = Field(
        description="Literature causes for the predicted patterns in this run: hypotheses to "
        "check, not a diagnosis."
    )
    method: str


class LotItem(Contract):
    lot: UserLabel
    wafers: Count
    pattern_counts: dict[WaferLabel, Count]
    tests: list[PatternTest]
    flagged: bool
    stacked: StackedMap | None


class LotResult(Contract):
    stage: Literal["lot"] = "lot"
    lots: list[LotItem]
    method: str


class FinalTestUnit(Contract):
    index: Count = Field(description="Position of the unit in the run input.")
    unit_id: UserLabel
    result: FinalResult
    flagged: bool = Field(description="Risk was above the threshold.")


class FinalTestWafer(Contract):
    index: Count = Field(description="Position of the wafer in the run input.")
    recorded_label: WaferLabel
    predicted_label: WaferLabel
    agrees: bool


class FinalTestResult(Contract):
    """How the warnings compare with the recorded results, when the input has them."""

    stage: Literal["final_test"] = "final_test"
    units: list[FinalTestUnit] = Field(description="Only units with a recorded result.")
    wafers: list[FinalTestWafer] = Field(description="Only wafers with a recorded label.")
    units_with_result: Count
    failed_units: Count
    failed_flagged: Count = Field(description="Failed units whose risk was above the threshold.")
    passed_flagged: Count = Field(description="Passed units whose risk was above the threshold.")
    wafers_with_label: Count
    wafers_agreeing: Count = Field(description="Predicted pattern equals the recorded label.")
    summary: str


StageResult = Annotated[
    IntakeResult
    | SensorRiskResult
    | ControlChartsResult
    | DriftHealthResult
    | WaferPatternResult
    | WaferSimilarResult
    | LotResult
    | FinalTestResult,
    Field(discriminator="stage"),
]


# ---------------------------------------------------------------------------------------------
# Alarms, run state and events
# ---------------------------------------------------------------------------------------------


class RunAlarm(Contract):
    """An alarm raised by a rule during the run. Messages are written by code."""

    alarm_id: RunAlarmId
    run_id: RunId
    stage: StageId
    kind: RunAlarmKind
    severity: RunAlarmSeverity
    unit_index: Count | None = None
    unit_id: UserLabel | None = None
    wafer_index: Count | None = None
    lot: UserLabel | None = None
    value: float | None
    limit: float | None
    title: str = Field(max_length=120, examples=["Sensor relationships broke (SPE)"])
    meaning: str = Field(max_length=400, description="One plain sentence.")
    sensors: list[SensorId] = Field(default_factory=list, max_length=10)
    investigation_id: str | None = None


class StageState(Contract):
    stage: StageId
    station: Station
    status: StageStatus
    needs: str | None = Field(None, description="Why the stage was skipped, in plain words.")
    elapsed_ms: float | None = None
    result: StageResult | None = None
    problem: Problem | None = None


class Run(Contract):
    run_id: RunId
    created_at: datetime
    status: RunStatus
    origin: RunOrigin
    units: Count
    wafers: Count
    stages: list[StageState]
    alarms: list[RunAlarm]
    alarms_not_listed: Count = Field(
        0,
        description="Alarms the rules raised beyond the per-run cap (most severe are listed); "
        "the stage results hold every value.",
    )
    expires_at: datetime | None = Field(
        description="When the run is deleted (24 h after creation); null while an "
        "investigation uses it, so the evidence behind a decision stays openable."
    )


class _Event(Contract):
    seq: Count
    at: datetime


class RunStartedEvent(_Event):
    type: Literal["run_started"] = "run_started"
    run_id: RunId
    origin: RunOrigin
    stages: list[StageState] = Field(description="Every stage, pending or skipped with `needs`.")


class StageStartedEvent(_Event):
    type: Literal["stage_started"] = "stage_started"
    stage: StageId


class StageResultEvent(_Event):
    type: Literal["stage_result"] = "stage_result"
    stage: StageId
    elapsed_ms: float = Field(ge=0, description="Server compute time of the stage.")
    result: StageResult


class StageSkippedEvent(_Event):
    type: Literal["stage_skipped"] = "stage_skipped"
    stage: StageId
    needs: str


class StageFailedEvent(_Event):
    type: Literal["stage_failed"] = "stage_failed"
    stage: StageId
    problem: Problem


class AlarmEvent(_Event):
    type: Literal["alarm"] = "alarm"
    alarm: RunAlarm


class RunDoneEvent(_Event):
    type: Literal["run_done"] = "run_done"
    status: Literal["done", "failed"]
    alarms: Count
    alarms_not_listed: Count = Field(
        0, description="Alarms raised but not listed because of the cap."
    )


RunEventPayload = (
    RunStartedEvent
    | StageStartedEvent
    | StageResultEvent
    | StageSkippedEvent
    | StageFailedEvent
    | AlarmEvent
    | RunDoneEvent
)


class RunEvent(RootModel[Annotated[RunEventPayload, Field(discriminator="type")]]):
    """An event on GET /runs/{id}/events (SSE: `event` is the type, `id` is `seq`)."""
