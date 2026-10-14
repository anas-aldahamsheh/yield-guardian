"""SECOM science results: risk, explanations, FDC, sensor groups, sensor health and metrics."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from yield_guardian.contracts.base import (
    BundleRef,
    Contract,
    Count,
    Estimate,
    InvestigationId,
    Probability,
    SensorId,
    SequenceNo,
    Share,
    UnitId,
)
from yield_guardian.contracts.line import (
    Alarm,
    Block,
    FdcAlarmLevel,
    FdcPeriod,
    OperatingPointRef,
    RiskBand,
    RiskSource,
    UnitSummary,
)

FdcStatistic = Literal["t2", "spe"]
SensorStatus = Literal["ok", "watch", "maintenance", "dead"]
FeatureKind = Literal["reading", "missing_indicator"]
Direction = Literal["higher_in_failures", "lower_in_failures", "no_difference", "not_tested"]


class UnitPage(Contract):
    items: list[UnitSummary]
    next_cursor: str | None = None
    total: Count


class UnitRisk(Contract):
    unit_id: UnitId
    block: Block
    risk: Probability | None
    risk_source: RiskSource | None
    risk_band: RiskBand | None
    operating_point: OperatingPointRef
    above_threshold: bool | None
    calibration: Literal["platt"] = "platt"
    note: str | None = Field(
        None,
        description="For example why risk is null (warm-up) or why calibration is in-sample (validation block).",
    )


class UnitDetail(UnitSummary):
    """A unit with its risk context, data completeness and related records."""

    risk_detail: UnitRisk
    sensors_measured: Count
    sensors_missing: Count
    explanation_available: bool
    alarms: list[Alarm]
    investigation_ids: list[InvestigationId]


class ShapContribution(Contract):
    feature: str = Field(
        description="Model feature: a sensor ID, or the missingness indicator of a sensor."
    )
    sensor: SensorId
    kind: FeatureKind
    value: float | None = Field(
        description="The unit's reading (null if not measured); 0 or 1 for an indicator."
    )
    shap: float = Field(description="TreeSHAP contribution in log-odds.")
    group_id: str | None


class GroupContribution(Contract):
    group_id: str
    sensors: list[SensorId]
    shap: float = Field(description="Sum of the members' SHAP values, in log-odds.")


class Explanation(Contract):
    """TreeSHAP explanation of one unit's risk, in log-odds (exact for tree models)."""

    unit_id: UnitId
    risk: Probability | None
    base_value: float = Field(description="Expected model output in log-odds.")
    raw_score: float = Field(
        description="base_value plus every contribution, in log-odds, before calibration."
    )
    contributions: list[ShapContribution] = Field(description="Largest |shap| first.")
    other_features: Count
    other_shap: float = Field(description="Sum of the contributions not listed.")
    groups: list[GroupContribution] = Field(description="Largest |shap| first.")
    units: Literal["log-odds"] = "log-odds"
    method: str


class FdcLimits(Contract):
    t2_99: float
    t2_999: float
    spe_99: float
    spe_999: float


class FdcPoint(Contract):
    unit_id: UnitId
    sequence: SequenceNo
    timestamp: datetime
    t2: float
    spe: float
    fdc_alarm: FdcAlarmLevel
    fdc_period: FdcPeriod
    ewma_alarm: bool
    cusum_alarm: bool


class ReferencePeriod(Contract):
    start: datetime
    end: datetime
    units: Count
    stationarity: str = Field(description="Test used and its result.")


class FdcSeries(Contract):
    """Multivariate control chart data (PCA on the reference period)."""

    limits: FdcLimits
    n_components: Count
    explained_variance: Share
    features: Count
    reference: ReferencePeriod
    points: list[FdcPoint]
    method: str


class FdcContribution(Contract):
    sensor: SensorId
    contribution: float
    share: Share = Field(description="Share of the statistic explained by this sensor.")
    value: float | None = Field(description="The unit's reading (null if not measured).")
    reference_median: float | None


class FdcContributions(Contract):
    unit_id: UnitId
    statistic: FdcStatistic
    value: float
    limit_99: float
    limit_999: float
    alarm: FdcAlarmLevel
    contributions: list[FdcContribution] = Field(description="Largest contribution first.")
    other_share: Share
    method: str


class UnivariateTest(Contract):
    sensor: SensorId
    mann_whitney_p: Probability | None = Field(description="Null when the test was not run.")
    q_value: Probability | None = Field(description="Null when the test was not run.")
    direction: Direction


class GroupingMethod(Contract):
    correlation: Literal["spearman"]
    threshold: float
    linkage: str
    stability_refits: Count
    stability_threshold: Share
    permutations: Count
    fdr_q: Probability


class SensorGroup(Contract):
    """Correlated sensors reported together, because SHAP splits credit between near-duplicates."""

    group_id: str
    sensors: list[SensorId]
    representative: SensorId
    importance: float = Field(description="Sum of the members' mean |SHAP| (log-odds).")
    stability: Share = Field(
        description="Share of bootstrap refits in which the group ranked in the top set."
    )
    p_value: Probability = Field(description="Label-permutation p-value of the group importance.")
    q_value: Probability = Field(description="Benjamini-Hochberg adjusted p-value.")
    significant: bool
    stable: bool
    univariate: list[UnivariateTest]


class SensorGroups(Contract):
    method: GroupingMethod
    groups: list[SensorGroup] = Field(description="Most important first.")
    sensors_total: Count
    significant_groups: Count
    sensors_in_significant_groups: Count
    wording: str = Field(
        description="How the result may be described (association, not causation)."
    )


class HealthWindow(Contract):
    window_id: Count
    start: datetime
    end: datetime
    units: Count


class MissingnessTest(Contract):
    """Fisher exact test of missingness versus failure, with Benjamini-Hochberg correction."""

    odds_ratio: float | None
    p_value: Probability | None
    q_value: Probability | None


class SensorHealth(Contract):
    sensor: SensorId
    status: SensorStatus
    reasons: list[str] = Field(description="Which written rules set the status.")
    missing_rate: Share
    missing_by_window: list[Share | None]
    flatline_windows: list[Count]
    stuck_value: float | None
    jump_unit_ids: list[UnitId]
    out_of_reference_rate: Share | None
    missing_vs_failure: MissingnessTest | None


class HealthCounts(Contract):
    ok: Count
    watch: Count
    maintenance: Count
    dead: Count


class SensorHealthReport(Contract):
    windows: list[HealthWindow]
    sensors: list[SensorHealth]
    counts: HealthCounts
    rules: list[str] = Field(description="The status rules, as written in the model card.")


class SensorPoint(Contract):
    unit_id: UnitId
    sequence: SequenceNo
    timestamp: datetime
    value: float | None


class SensorReference(Contract):
    """Range of the sensor in the FDC reference period."""

    median: float
    q01: float
    q99: float


class SensorSeries(Contract):
    sensor: SensorId
    status: SensorStatus
    group_id: str | None
    reference: SensorReference | None
    points: list[SensorPoint]


class OperatingPoint(Contract):
    """Test-block performance at a threshold chosen on the validation block."""

    id: str = Field(examples=["fpr_0.05"])
    label: str = Field(examples=["5% false-alarm rate"])
    threshold: Probability
    target_fpr: Probability | None
    fpr: Estimate
    recall: Estimate
    precision: Estimate
    false_alarms_per_100: Estimate | None
    tp: Count
    fp: Count
    tn: Count
    fn: Count


class CurvePoint(Contract):
    threshold: Probability
    fpr: Probability
    recall: Probability
    precision: Probability


class OperatingPoints(Contract):
    block: Block
    default: str
    units: Count
    failures: Count
    prevalence: Probability
    points: list[OperatingPoint]
    curve: list[CurvePoint]


class BlockInfo(Contract):
    block: Block
    start: datetime
    end: datetime
    units: Count
    failures: Count


class MetricValue(Contract):
    metric: str = Field(examples=["pr_auc"])
    label: str = Field(examples=["PR-AUC"])
    estimate: Estimate


class ModelResult(Contract):
    model: str = Field(examples=["lightgbm"])
    label: str = Field(examples=["LightGBM (class weights, Optuna)"])
    main: bool
    metrics: list[MetricValue]


class PairedComparison(Contract):
    baseline: str
    metric: str
    difference: Estimate = Field(description="Main model minus baseline.")
    p_value: Probability


class ReliabilityBin(Contract):
    bin: Count
    mean_predicted: Probability
    observed_rate: Probability
    units: Count


class Calibration(Contract):
    method: Literal["platt"]
    a: float
    b: float
    brier: Estimate
    ece: Estimate
    bins: list[ReliabilityBin]
    caveat: str


class CvFold(Contract):
    fold: Count
    train_units: Count
    validation_start: datetime
    validation_end: datetime
    validation_units: Count
    validation_failures: Count
    average_precision: float


class Tuning(Contract):
    sampler: str
    trials: Count
    objective: str
    best_value: float
    best_params: dict[str, float | int | str | bool]
    folds: list[CvFold]


class FdcValidation(Contract):
    holdout_units: Count
    false_alarm_rate_99: Estimate
    false_alarm_rate_999: Estimate
    ewma: str = Field(description="Parameters (lambda, L) and in-control run length.")
    cusum: str = Field(description="Parameters (k, h) and in-control run length.")


class SecomMetrics(Contract):
    bundle: BundleRef
    blocks: list[BlockInfo]
    models: list[ModelResult]
    comparisons: list[PairedComparison]
    calibration: Calibration
    tuning: Tuning | None
    fdc: FdcValidation | None
    limitations: list[str]
