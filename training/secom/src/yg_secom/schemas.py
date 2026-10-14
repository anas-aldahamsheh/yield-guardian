"""Schemas of every file in the SECOM bundle (``packages/contracts/ARTIFACTS.md``).

Files whose layout the contract defines field by field (``groups.json``, ``health.json``,
``operating_points.json``, ``calibrator.json``, ``MANIFEST.json``, ``timeline.parquet`` and
the NPZ files) are checked exactly: unknown JSON fields are errors. Files the contract
describes by content only (``metrics.json``, ``preprocess.json``, ``eda.json``) must hold
the required keys and may hold more.

``metrics.json`` must also hold the keys the API validates strictly: ``report`` (checked
against ``#/components/schemas/SecomMetrics`` of ``packages/contracts/openapi.json`` with
``bundle`` removed, by JSON Schema), ``fdc_reference``, ``fdc_explained_variance`` and
``methods``.

``validate_bundle`` raises ``BundleError`` listing every problem it finds.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import jsonschema
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from yg_common.io import load_npz
from yg_common.provenance import sha256_file

SENSOR = r"^S\d{3}$"
FEATURE = r"^S\d{3}(_missing)?$"
HEX64 = r"^[0-9a-f]{64}$"
Probability = Annotated[float, Field(ge=0.0, le=1.0)]
Sensor = Annotated[str, Field(pattern=SENSOR)]


class BundleError(ValueError):
    """The bundle does not match its contract."""


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=False)


class Open(BaseModel):
    model_config = ConfigDict(extra="allow")


class EstimateModel(Strict):
    value: float
    ci_low: float | None
    ci_high: float | None
    ci_level: Annotated[float, Field(gt=0.0, lt=1.0)]
    method: str
    n: Annotated[int, Field(ge=0)]
    note: str | None = None

    @model_validator(mode="after")
    def _note_for_missing_bound(self) -> EstimateModel:
        if (self.ci_low is None or self.ci_high is None) and not self.note:
            raise ValueError("a null interval bound needs a note")
        return self


class Univariate(Strict):
    sensor: Sensor
    mann_whitney_p: Probability | None
    q_value: Probability | None
    direction: Literal["higher_in_failures", "lower_in_failures", "no_difference", "not_tested"]


class Group(Strict):
    group_id: Annotated[str, Field(pattern=r"^G\d{2,}$")]
    sensors: Annotated[list[Sensor], Field(min_length=1)]
    representative: Sensor
    importance: Annotated[float, Field(ge=0.0)]
    stability: Probability
    p_value: Annotated[float, Field(gt=0.0, le=1.0)]
    q_value: Probability
    significant: bool
    univariate: list[Univariate]

    @model_validator(mode="after")
    def _consistent(self) -> Group:
        if self.representative not in self.sensors:
            raise ValueError(f"{self.group_id}: representative is not a member")
        if [u.sensor for u in self.univariate] != self.sensors:
            raise ValueError(f"{self.group_id}: univariate entries must follow the members")
        return self


class GroupsMethod(Strict):
    correlation: Literal["spearman"]
    threshold: Probability
    linkage: Literal["average"]
    stability_refits: Annotated[int, Field(ge=1)]
    stability_threshold: Probability
    permutations: Annotated[int, Field(ge=1)]
    fdr_q: Probability


class GroupsFile(Strict):
    method: GroupsMethod
    groups: list[Group]

    @model_validator(mode="after")
    def _unique(self) -> GroupsFile:
        ids = [g.group_id for g in self.groups]
        if len(set(ids)) != len(ids):
            raise ValueError("group ids must be unique")
        members = [s for g in self.groups for s in g.sensors]
        if len(set(members)) != len(members):
            raise ValueError("a sensor belongs to two groups")
        importance = [g.importance for g in self.groups]
        if importance != sorted(importance, reverse=True):
            raise ValueError("groups must be ordered by decreasing importance")
        return self


class HealthWindow(Strict):
    window_id: Annotated[int, Field(ge=0)]
    start: str
    end: str
    unit_ids: list[int]


class MissingVsFailure(Strict):
    odds_ratio: Annotated[float, Field(ge=0.0)] | None
    p_value: Probability | None
    q_value: Probability | None


class HealthSensor(Strict):
    sensor: Sensor
    missing_rate: Probability
    missing_by_window: list[Probability]
    flatline_windows: list[int]
    stuck_value: float | None
    jump_unit_ids: list[int]
    out_of_reference_rate: Probability | None
    missing_vs_failure: MissingVsFailure
    status: Literal["ok", "watch", "maintenance", "dead"]
    reasons: list[str]

    @model_validator(mode="after")
    def _reasons(self) -> HealthSensor:
        if (self.status == "ok") != (not self.reasons):
            raise ValueError(f"{self.sensor}: reasons must be empty exactly when status is ok")
        return self


class HealthFile(Strict):
    rules: Annotated[list[str], Field(min_length=4)]
    windows: list[HealthWindow]
    sensors: list[HealthSensor]

    @model_validator(mode="after")
    def _windows(self) -> HealthFile:
        if [w.window_id for w in self.windows] != list(range(len(self.windows))):
            raise ValueError("window ids must be 0..W-1 in order")
        for s in self.sensors:
            if len(s.missing_by_window) != len(self.windows):
                raise ValueError(f"{s.sensor}: one missing rate per window expected")
            if any(not 0 <= w < len(self.windows) for w in s.flatline_windows):
                raise ValueError(f"{s.sensor}: unknown flatline window")
        return self


class OperatingPoint(Strict):
    id: str
    label: Annotated[str, Field(min_length=1)]
    target_fpr: Probability | None
    threshold: Probability
    fpr: EstimateModel
    recall: EstimateModel
    precision: EstimateModel
    false_alarms_per_100: EstimateModel | None
    tp: Annotated[int, Field(ge=0)]
    fp: Annotated[int, Field(ge=0)]
    tn: Annotated[int, Field(ge=0)]
    fn: Annotated[int, Field(ge=0)]


class CurvePoint(Strict):
    threshold: float
    fpr: Probability
    recall: Probability
    precision: Probability


class OperatingPointsFile(Strict):
    block: Literal["test"]
    default: str
    units: Annotated[int, Field(ge=1)]
    failures: Annotated[int, Field(ge=0)]
    prevalence: Probability
    points: Annotated[list[OperatingPoint], Field(min_length=1)]
    curve: list[CurvePoint]

    @model_validator(mode="after")
    def _default(self) -> OperatingPointsFile:
        if self.default not in {p.id for p in self.points}:
            raise ValueError("default must name one of the points")
        return self


class CalibratorFile(Strict):
    method: Literal["platt"]
    a: float
    b: float


class DroppedFeature(Open):
    sensor: Sensor
    reason: str


class PreprocessFile(Open):
    model_features: Annotated[list[str], Field(min_length=1)]
    dropped: list[DroppedFeature]
    missingness_indicators: list[str]


class EdaFile(Open):
    counts: dict[str, Any]
    time_range: dict[str, Any]
    missingness: dict[str, Any]
    constant_features: dict[str, Any]
    class_balance: dict[str, Any]


class FdcReference(Strict):
    start: str
    end: str
    units: Annotated[int, Field(ge=1)]
    stationarity: Annotated[str, Field(min_length=1)]


class Methods(Strict):
    explanation: Annotated[str, Field(min_length=1)]
    fdc: Annotated[str, Field(min_length=1)]
    contributions: Annotated[str, Field(min_length=1)]


class MetricsFile(Open):
    split: dict[str, Any]
    tuning: dict[str, Any]
    models: dict[str, Any]
    comparisons: dict[str, Any]
    calibration: dict[str, Any]
    run: dict[str, Any]
    report: dict[str, Any]
    fdc_reference: FdcReference
    fdc_explained_variance: Probability
    methods: Methods


class ManifestData(Strict):
    path: str
    sha256: Annotated[str, Field(pattern=HEX64)]


class ManifestEnvironment(Strict):
    python: str
    packages: dict[str, str]


class ManifestFileEntry(Strict):
    path: str
    bytes: Annotated[int, Field(ge=0)]
    sha256: Annotated[str, Field(pattern=HEX64)]


class ManifestFile(Strict):
    name: Literal["secom"]
    version: Annotated[str, Field(pattern=r"^v\d+$")]
    created_at: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")]
    git_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    data: Annotated[list[ManifestData], Field(min_length=1)]
    environment: ManifestEnvironment
    files: Annotated[list[ManifestFileEntry], Field(min_length=1)]


TIMELINE_SCHEMA = pa.schema(
    [
        ("unit_id", pa.int32()),
        ("timestamp", pa.timestamp("us", tz="UTC")),
        ("label", pa.int8()),
        ("block", pa.string()),
        ("risk", pa.float32()),
        ("risk_source", pa.string()),
        ("risk_band", pa.string()),
        ("t2", pa.float32()),
        ("spe", pa.float32()),
        ("t2_limit_99", pa.float32()),
        ("t2_limit_999", pa.float32()),
        ("spe_limit_99", pa.float32()),
        ("spe_limit_999", pa.float32()),
        ("fdc_alarm", pa.string()),
        ("fdc_period", pa.string()),
        ("ewma_alarm", pa.bool_()),
        ("cusum_alarm", pa.bool_()),
    ]
)

JSON_MODELS: dict[str, type[BaseModel]] = {
    "groups.json": GroupsFile,
    "health.json": HealthFile,
    "operating_points.json": OperatingPointsFile,
    "calibrator.json": CalibratorFile,
    "preprocess.json": PreprocessFile,
    "eda.json": EdaFile,
    "metrics.json": MetricsFile,
    "MANIFEST.json": ManifestFile,
}

BUNDLE_FILES = (
    "timeline.parquet",
    "shap.npz",
    "fdc.npz",
    "fdc_model.npz",
    "groups.json",
    "health.json",
    "operating_points.json",
    "metrics.json",
    "model.txt",
    "calibrator.json",
    "preprocess.json",
    "eda.json",
    "model_card.md",
    "MANIFEST.json",
)


def _check_timeline(path: Path, problems: list[str]) -> int:
    table = pq.read_table(path)
    if not table.schema.equals(TIMELINE_SCHEMA, check_metadata=False):
        problems.append(f"timeline.parquet schema differs:\n{table.schema}")
        return 0
    df = table.to_pandas()
    n = len(df)
    ts = df["timestamp"]
    if not bool((ts.diff().dropna() >= pd.Timedelta(0)).all()):
        problems.append("timeline.parquet is not sorted by timestamp")
    if sorted(df["unit_id"].tolist()) != list(range(n)):
        problems.append("timeline.parquet must hold every unit exactly once")
    checks = {
        "label": set(df["label"].unique()) <= {0, 1},
        "block": set(df["block"].unique()) <= {"train", "validation", "test"},
        "risk_source": set(df["risk_source"].dropna().unique()) <= {"oof", "validation", "test"},
        "risk_band": set(df["risk_band"].dropna().unique()) <= {"low", "elevated", "high"},
        "fdc_alarm": set(df["fdc_alarm"].unique()) <= {"none", "warning", "alarm"},
        "fdc_period": set(df["fdc_period"].unique()) <= {"reference", "monitoring"},
    }
    problems += [
        f"timeline.parquet: unexpected values in {k}" for k, ok in checks.items() if not ok
    ]
    risk = df["risk"]
    if not (risk.isna() == df["risk_source"].isna()).all():
        problems.append("timeline.parquet: risk and risk_source must be null together")
    if not (risk.isna() == df["risk_band"].isna()).all():
        problems.append("timeline.parquet: risk and risk_band must be null together")
    if not risk.dropna().between(0.0, 1.0).all():
        problems.append("timeline.parquet: risk outside [0, 1]")
    for column in ("t2", "spe", "t2_limit_99", "t2_limit_999", "spe_limit_99", "spe_limit_999"):
        if df[column].isna().any():
            problems.append(f"timeline.parquet: {column} has nulls")
    return n


def _check_npz(directory: Path, n_units: int, problems: list[str]) -> None:
    shap = load_npz(directory / "shap.npz")
    shap_missing = [k for k in ("values", "base_value", "features", "unit_ids") if k not in shap]
    problems += [f"shap.npz lacks {k}" for k in shap_missing]
    if not shap_missing:
        values = shap["values"]
        if values.dtype != np.float32 or values.shape != (n_units, shap["features"].size):
            problems.append(
                f"shap.npz values must be float32 [units, features], got {values.shape}"
            )
        if shap["unit_ids"].tolist() != list(range(n_units)):
            problems.append("shap.npz unit_ids must be 0..n-1")
        if not all(re.match(FEATURE, str(f)) for f in shap["features"]):
            problems.append("shap.npz features must be sensor ids or <sensor>_missing")
        if shap["base_value"].shape != ():
            problems.append("shap.npz base_value must be a scalar")
        base_values = shap.get("base_values")
        if base_values is None or base_values.shape != (n_units,):
            problems.append("shap.npz base_values must be [units]")
        elif not np.array_equal(np.isnan(base_values), np.isnan(values).all(axis=1)):
            problems.append("shap.npz rows without a base value must be NaN, and only those")
    fdc = load_npz(directory / "fdc.npz")
    for key in ("contrib_t2", "contrib_spe", "features", "unit_ids"):
        if key not in fdc:
            problems.append(f"fdc.npz lacks {key}")
    if "contrib_t2" in fdc and fdc["contrib_t2"].shape != (n_units, fdc["features"].size):
        problems.append("fdc.npz contributions must be [units, fdc_features]")
    model = load_npz(directory / "fdc_model.npz")
    required = (
        "center",
        "scale",
        "loadings",
        "eigenvalues",
        "n_components",
        "features",
        "impute_values",
        "t2_limit_99",
        "t2_limit_999",
        "spe_limit_99",
        "spe_limit_999",
        "reference_unit_ids",
    )
    model_missing = [k for k in required if k not in model]
    problems += [f"fdc_model.npz lacks {k}" for k in model_missing]
    if not model_missing:
        p = model["features"].size
        a = int(model["n_components"])
        if model["loadings"].shape != (p, a):
            problems.append("fdc_model.npz loadings must be [features, n_components]")
        if any(model[k].shape != (p,) for k in ("center", "scale", "impute_values")):
            problems.append("fdc_model.npz center, scale and impute_values must be [features]")


def report_schema(openapi_path: Path) -> dict[str, Any]:
    """JSON Schema of ``metrics.json`` ``report``: the API's SecomMetrics without ``bundle``."""
    document = json.loads(openapi_path.read_text(encoding="utf-8"))
    components = document["components"]["schemas"]
    schema: dict[str, Any] = json.loads(json.dumps(components["SecomMetrics"]))
    schema["properties"].pop("bundle", None)
    schema["required"] = [r for r in schema["required"] if r != "bundle"]
    schema["components"] = {"schemas": components}
    return schema


def report_problems(report: Any, openapi_path: Path) -> list[str]:
    """Every way ``report`` departs from the API schema (empty when it matches)."""
    schema = report_schema(openapi_path)
    validator = jsonschema.Draft202012Validator(schema)
    problems = [
        f"metrics.json report at {'/'.join(str(p) for p in e.absolute_path) or '<root>'}: "
        f"{e.message}"
        for e in sorted(
            validator.iter_errors(report), key=lambda e: list(map(str, e.absolute_path))
        )
    ]
    problems += _date_time_problems(report, schema, schema["components"]["schemas"])
    return problems


def _date_time_problems(
    value: Any, schema: dict[str, Any], components: dict[str, Any], path: str = ""
) -> list[str]:
    """JSON Schema does not enforce ``format: date-time`` by default; check it here."""
    if "$ref" in schema:
        name = str(schema["$ref"]).rsplit("/", 1)[-1]
        return _date_time_problems(value, components[name], components, path)
    out: list[str] = []
    if schema.get("format") == "date-time" and isinstance(value, str):
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            out.append(f"metrics.json report at {path}: {value!r} is not an ISO date-time")
    for option in schema.get("anyOf", []):
        if option.get("type") != "null":
            out += _date_time_problems(value, option, components, path)
    if isinstance(value, dict):
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                out += _date_time_problems(value[key], sub, components, f"{path}/{key}")
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for i, item in enumerate(value):
            out += _date_time_problems(item, schema["items"], components, f"{path}/{i}")
    return out


def validate_bundle(
    directory: Path, check_manifest: bool = True, openapi_path: Path | None = None
) -> None:
    """Validate every bundle file against its schema; raise ``BundleError`` on problems."""
    problems: list[str] = []
    for name in BUNDLE_FILES:
        if not (directory / name).is_file():
            problems.append(f"missing file {name}")
    if problems:
        raise BundleError("\n".join(problems))
    for name, model in JSON_MODELS.items():
        try:
            model.model_validate(json.loads((directory / name).read_text(encoding="utf-8")))
        except ValidationError as error:
            problems.append(f"{name}: {error}")
    if openapi_path is not None:
        metrics = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
        problems += report_problems(metrics.get("report"), openapi_path)
    n_units = _check_timeline(directory / "timeline.parquet", problems)
    if n_units:
        _check_npz(directory, n_units, problems)
    if check_manifest and not problems:
        manifest = json.loads((directory / "MANIFEST.json").read_text(encoding="utf-8"))
        listed = {f["path"] for f in manifest["files"]}
        expected = set(BUNDLE_FILES) - {"MANIFEST.json"}
        if listed != expected:
            problems.append(f"MANIFEST.json lists {sorted(listed ^ expected)} incorrectly")
        for entry in manifest["files"]:
            path = directory / entry["path"]
            if path.is_file() and sha256_file(path) != entry["sha256"]:
                problems.append(f"MANIFEST.json: checksum mismatch for {entry['path']}")
            if path.is_file() and path.stat().st_size != entry["bytes"]:
                problems.append(f"MANIFEST.json: size mismatch for {entry['path']}")
    if problems:
        raise BundleError("\n".join(problems))
