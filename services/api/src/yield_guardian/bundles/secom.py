"""The SECOM bundle and the SECOM source files, loaded once, cross-checked and held in memory."""

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pyarrow.parquet as pq
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from yield_guardian.bundles.manifest import BundleError, VerifiedBundle
from yield_guardian.contracts.base import Probability, SensorId, Share
from yield_guardian.contracts.line import Block, FdcAlarmLevel, FdcPeriod, RiskBand, RiskSource
from yield_guardian.contracts.secom import (
    GroupingMethod,
    OperatingPoints,
    ReferencePeriod,
    SecomMetrics,
    SensorStatus,
    UnivariateTest,
)

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]
BoolArray = npt.NDArray[np.bool_]

SENSOR = re.compile(r"^S(\d{3})$")
INDICATOR_SUFFIX = "_missing"
N_SENSORS = 590


def sensor_id(column: int) -> str:
    return f"S{column + 1:03d}"


def sensor_column(sensor: str) -> int:
    match = SENSOR.match(sensor)
    if not match or not 1 <= int(match.group(1)) <= N_SENSORS:
        raise ValueError(f"not a SECOM sensor: {sensor!r}")
    return int(match.group(1)) - 1


def feature_sensor(feature: str) -> tuple[str, bool]:
    """The sensor behind a model feature, and whether the feature is its missingness indicator."""
    indicator = feature.endswith(INDICATOR_SUFFIX)
    sensor = feature.removesuffix(INDICATOR_SUFFIX)
    sensor_column(sensor)
    return sensor, indicator


class _File(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class GroupRecord(_File):
    group_id: str
    sensors: list[SensorId] = Field(min_length=1)
    representative: SensorId
    importance: float = Field(ge=0)
    stability: Share
    p_value: Probability
    q_value: Probability
    significant: bool
    univariate: list[UnivariateTest]


class GroupsFile(_File):
    method: GroupingMethod
    groups: list[GroupRecord]


class HealthWindowRecord(_File):
    window_id: int = Field(ge=0)
    start: datetime
    end: datetime
    unit_ids: list[int]


class MissingVsFailureRecord(_File):
    odds_ratio: float | None = Field(ge=0)
    p_value: Probability | None
    q_value: Probability | None


class HealthSensorRecord(_File):
    sensor: SensorId
    status: SensorStatus
    reasons: list[str]
    missing_rate: Share
    missing_by_window: list[Share]
    flatline_windows: list[int]
    stuck_value: float | None
    jump_unit_ids: list[int]
    out_of_reference_rate: Share | None
    missing_vs_failure: MissingVsFailureRecord | None


class HealthFile(_File):
    rules: list[str] = Field(min_length=1)
    windows: list[HealthWindowRecord]
    sensors: list[HealthSensorRecord]


class MethodSentences(_File):
    explanation: str
    fdc: str
    contributions: str


class MetricsKeys(BaseModel):
    """The keys of metrics.json the API reads; the rest of the file is the pipeline's record."""

    model_config = ConfigDict(extra="ignore", frozen=True, allow_inf_nan=False)

    report: dict[str, Any]
    fdc_reference: ReferencePeriod
    fdc_explained_variance: Share
    methods: MethodSentences


class CalibratorFile(_File):
    method: str
    a: float
    b: float


@dataclass(frozen=True, slots=True)
class SourceData:
    """secom.data and secom_labels.data: readings [units, 590], timestamps and final-test labels."""

    readings: FloatArray
    timestamps: list[datetime]
    failed: BoolArray

    @classmethod
    def load(cls, directory: Path) -> "SourceData":
        readings = np.loadtxt(directory / "secom.data", dtype=np.float64)
        timestamps: list[datetime] = []
        failed: list[bool] = []
        for line in (directory / "secom_labels.data").read_text(encoding="ascii").splitlines():
            label, stamp = line.split(" ", 1)
            timestamps.append(
                datetime.strptime(stamp.strip().strip('"'), "%d/%m/%Y %H:%M:%S").replace(tzinfo=UTC)
            )
            failed.append(label == "1")
        if readings.shape != (len(timestamps), N_SENSORS):
            raise BundleError(f"secom.data shape {readings.shape} does not match the labels file.")
        return cls(readings=readings, timestamps=timestamps, failed=np.array(failed))


@dataclass(frozen=True, slots=True)
class Timeline:
    """timeline.parquet in time order: index i is sequence number i."""

    unit_id: IntArray
    sequence_of: IntArray
    timestamp: list[datetime]
    failed: BoolArray
    block: list[Block]
    risk: FloatArray
    risk_source: list[RiskSource | None]
    risk_band: list[RiskBand | None]
    t2: FloatArray
    spe: FloatArray
    t2_limit_99: FloatArray
    t2_limit_999: FloatArray
    spe_limit_99: FloatArray
    spe_limit_999: FloatArray
    fdc_alarm: list[FdcAlarmLevel]
    fdc_period: list[FdcPeriod]
    ewma_alarm: BoolArray
    cusum_alarm: BoolArray

    def __len__(self) -> int:
        return len(self.unit_id)


@dataclass(frozen=True, slots=True)
class Shap:
    values: npt.NDArray[np.float32]
    base_values: FloatArray
    features: list[str]
    feature_sensors: list[str]
    feature_is_indicator: list[bool]


@dataclass(frozen=True, slots=True)
class Fdc:
    contrib_t2: npt.NDArray[np.float32]
    contrib_spe: npt.NDArray[np.float32]
    features: list[str]
    reference_medians: FloatArray
    n_components: int
    limits: tuple[float, float, float, float]
    reference_unit_ids: IntArray


@dataclass(frozen=True, slots=True)
class SecomBundle:
    bundle: VerifiedBundle
    source: SourceData
    timeline: Timeline
    shap: Shap
    fdc: Fdc
    groups: GroupsFile
    health: HealthFile
    operating_points: OperatingPoints
    metrics: SecomMetrics
    fdc_reference: ReferencePeriod
    fdc_explained_variance: float
    methods: MethodSentences
    calibrator: CalibratorFile
    model_features: list[str]
    model_card: str


def _json[M: BaseModel](bundle: VerifiedBundle, name: str, model: type[M]) -> M:
    try:
        return model.model_validate(json.loads(bundle.file(name).read_text(encoding="utf-8")))
    except (OSError, ValueError, ValidationError) as error:
        raise BundleError(f"secom/{bundle.path.name}/{name}: {error}") from error


def _npz(bundle: VerifiedBundle, name: str, keys: tuple[str, ...]) -> dict[str, Any]:
    with np.load(bundle.file(name), allow_pickle=False) as data:
        missing = [k for k in keys if k not in data.files]
        if missing:
            raise BundleError(f"secom/{bundle.path.name}/{name} lacks {', '.join(missing)}.")
        return {k: data[k] for k in data.files}


def _strings(values: Any) -> list[str]:
    return [str(v) for v in np.asarray(values).tolist()]


def _load_timeline(bundle: VerifiedBundle, source: SourceData) -> Timeline:
    frame = pq.read_table(bundle.file("timeline.parquet")).to_pandas()
    n = len(source.timestamps)
    if sorted(frame["unit_id"].tolist()) != list(range(n)):
        raise BundleError("timeline.parquet must hold every SECOM unit exactly once.")
    frame = frame.assign(_ts=frame["timestamp"]).sort_values(["_ts", "unit_id"], kind="stable")
    unit_id = frame["unit_id"].to_numpy(dtype=np.int64)
    timestamps = [t.to_pydatetime().astimezone(UTC) for t in frame["timestamp"]]
    failed = frame["label"].to_numpy() == 1
    for unit, stamp, fail in zip(unit_id.tolist(), timestamps, failed.tolist(), strict=True):
        if stamp != source.timestamps[unit] or fail != bool(source.failed[unit]):
            raise BundleError(f"timeline.parquet disagrees with secom_labels.data for unit {unit}.")
    sequence_of = np.empty(n, dtype=np.int64)
    sequence_of[unit_id] = np.arange(n)

    def nullable(column: str) -> list[Any]:
        return [None if v is None or v != v else str(v) for v in frame[column].tolist()]

    def numbers(column: str) -> FloatArray:
        return np.asarray(frame[column].to_numpy(dtype=np.float64, na_value=np.nan))

    return Timeline(
        unit_id=unit_id,
        sequence_of=sequence_of,
        timestamp=timestamps,
        failed=failed,
        block=[str(v) for v in frame["block"]],  # type: ignore[misc]
        risk=numbers("risk"),
        risk_source=nullable("risk_source"),
        risk_band=nullable("risk_band"),
        t2=numbers("t2"),
        spe=numbers("spe"),
        t2_limit_99=numbers("t2_limit_99"),
        t2_limit_999=numbers("t2_limit_999"),
        spe_limit_99=numbers("spe_limit_99"),
        spe_limit_999=numbers("spe_limit_999"),
        fdc_alarm=[str(v) for v in frame["fdc_alarm"]],  # type: ignore[misc]
        fdc_period=[str(v) for v in frame["fdc_period"]],  # type: ignore[misc]
        ewma_alarm=frame["ewma_alarm"].to_numpy(dtype=bool),
        cusum_alarm=frame["cusum_alarm"].to_numpy(dtype=bool),
    )


def _check_timeline_values(timeline: Timeline) -> None:
    allowed: dict[str, tuple[list[Any], set[Any]]] = {
        "block": (list(timeline.block), {"train", "validation", "test"}),
        "risk_source": (list(timeline.risk_source), {None, "oof", "validation", "test"}),
        "risk_band": (list(timeline.risk_band), {None, "low", "elevated", "high"}),
        "fdc_alarm": (list(timeline.fdc_alarm), {"none", "warning", "alarm"}),
        "fdc_period": (list(timeline.fdc_period), {"reference", "monitoring"}),
    }
    for column, (values, permitted) in allowed.items():
        if not set(values) <= permitted:
            raise BundleError(f"timeline.parquet: unexpected values in {column}.")
    risk_null = np.isnan(timeline.risk)
    if any(risk_null[i] != (timeline.risk_source[i] is None) for i in range(len(timeline))):
        raise BundleError("timeline.parquet: risk and risk_source must be null together.")
    if np.any((timeline.risk[~risk_null] < 0) | (timeline.risk[~risk_null] > 1)):
        raise BundleError("timeline.parquet: risk outside [0, 1].")
    for name in ("t2", "spe", "t2_limit_99", "t2_limit_999", "spe_limit_99", "spe_limit_999"):
        statistic: FloatArray = getattr(timeline, name)
        if not np.all(np.isfinite(statistic)) or np.any(statistic < 0):
            raise BundleError(f"timeline.parquet: {name} must be finite and non-negative.")


def load_secom_bundle(bundle: VerifiedBundle, data_dir: Path) -> SecomBundle:
    """Load a verified SECOM bundle against the SECOM source files; raise BundleError if they disagree."""
    source = SourceData.load(data_dir)
    n = len(source.timestamps)
    timeline = _load_timeline(bundle, source)
    _check_timeline_values(timeline)

    raw_shap = _npz(bundle, "shap.npz", ("values", "base_value", "features", "unit_ids"))
    features = _strings(raw_shap["features"])
    try:
        mapped = [feature_sensor(f) for f in features]
    except ValueError as error:
        raise BundleError(f"shap.npz: {error}") from error
    values = np.asarray(raw_shap["values"], dtype=np.float32)
    if values.shape != (n, len(features)) or raw_shap["unit_ids"].tolist() != list(range(n)):
        raise BundleError("shap.npz: values must be [units, features] with unit_ids 0..n-1.")
    base_values = (
        np.asarray(raw_shap["base_values"], dtype=np.float64)
        if "base_values" in raw_shap
        else np.full(n, float(raw_shap["base_value"]))
    )
    if base_values.shape != (n,):
        raise BundleError("shap.npz: base_values must be [units].")
    shap = Shap(
        values=values,
        base_values=base_values,
        features=features,
        feature_sensors=[s for s, _ in mapped],
        feature_is_indicator=[i for _, i in mapped],
    )

    raw_fdc = _npz(bundle, "fdc.npz", ("contrib_t2", "contrib_spe", "features", "unit_ids"))
    model = _npz(
        bundle,
        "fdc_model.npz",
        (
            "features",
            "n_components",
            "impute_values",
            "t2_limit_99",
            "t2_limit_999",
            "spe_limit_99",
            "spe_limit_999",
            "reference_unit_ids",
        ),
    )
    fdc_features = _strings(raw_fdc["features"])
    if fdc_features != _strings(model["features"]):
        raise BundleError("fdc.npz and fdc_model.npz list different features.")
    for feature in fdc_features:
        sensor_column(feature)
    contrib_t2 = np.asarray(raw_fdc["contrib_t2"], dtype=np.float32)
    contrib_spe = np.asarray(raw_fdc["contrib_spe"], dtype=np.float32)
    shape = (n, len(fdc_features))
    if contrib_t2.shape != shape or contrib_spe.shape != shape:
        raise BundleError("fdc.npz: contributions must be [units, fdc_features].")
    fdc = Fdc(
        contrib_t2=contrib_t2,
        contrib_spe=contrib_spe,
        features=fdc_features,
        reference_medians=np.asarray(model["impute_values"], dtype=np.float64),
        n_components=int(model["n_components"]),
        limits=(
            float(model["t2_limit_99"]),
            float(model["t2_limit_999"]),
            float(model["spe_limit_99"]),
            float(model["spe_limit_999"]),
        ),
        reference_unit_ids=np.asarray(model["reference_unit_ids"], dtype=np.int64),
    )

    keys = _json(bundle, "metrics.json", MetricsKeys)
    try:
        metrics = SecomMetrics.model_validate({**keys.report, "bundle": bundle.info.bundle})
    except ValidationError as error:
        raise BundleError(f"metrics.json report: {error}") from error
    preprocess = json.loads(bundle.file("preprocess.json").read_text(encoding="utf-8"))
    return SecomBundle(
        bundle=bundle,
        source=source,
        timeline=timeline,
        shap=shap,
        fdc=fdc,
        groups=_json(bundle, "groups.json", GroupsFile),
        health=_json(bundle, "health.json", HealthFile),
        operating_points=_json(bundle, "operating_points.json", OperatingPoints),
        metrics=metrics,
        fdc_reference=keys.fdc_reference,
        fdc_explained_variance=keys.fdc_explained_variance,
        methods=keys.methods,
        calibrator=_json(bundle, "calibrator.json", CalibratorFile),
        model_features=[str(f) for f in preprocess.get("model_features", [])],
        model_card=bundle.file("model_card.md").read_text(encoding="utf-8"),
    )
