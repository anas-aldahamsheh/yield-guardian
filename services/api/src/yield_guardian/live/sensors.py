"""The SECOM models applied live to any sensor units: risk, TreeSHAP, T²/SPE, drift and health.

`SecomSensorEngine` implements `SensorEngine` (live/protocols.py) on the loaded SECOM bundle.
Every number is computed from the input readings when a stage runs, with the deployed models and
the training pipeline's own formulas (training/secom/src/yg_secom). The bundle's stored per-unit
results (the risk, statistics and alarms in timeline.parquet, shap.npz, fdc.npz, health.json)
are never read here; they exist so the parity tests can prove that live equals training. Of the
timeline the engine uses only the time order and each unit's block (for `validity` and the
sampler). What it takes from the bundle is the fitted state and its fixed parameters:

- risk: model.txt (LightGBM), preprocess.json (kept sensors and missingness indicators),
  calibrator.json (Platt a and b), operating_points.json (thresholds) and the held-out test
  skill in metrics.json;
- control charts: fdc_model.npz (imputation medians, centre, scale, loadings, eigenvalues,
  number of components and limits);
- drift and health: the run's configuration recorded in metrics.json (lambda, L, k, h, the
  health thresholds), groups.json (which groups lead), and the FDC reference units listed in
  metrics.json. Statistics the bundle does not store (the group-score mean and SD, the sign
  of each group member, every per-sensor reference statistic of the health rules, the jump
  threshold) are derived once at start-up from those reference units and the SECOM source
  readings, by the same formulas training used, and checked against what metrics.json
  recorded (see `_leading_groups` and `_derive_health_reference`).
"""

import json
import math
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from random import Random
from typing import Any

import lightgbm as lgb
import numpy as np
import numpy.typing as npt
import pandas as pd
from pydantic import BaseModel, ConfigDict, ValidationError

from yield_guardian.bundles.manifest import BundleError
from yield_guardian.bundles.secom import (
    INDICATOR_SUFFIX,
    N_SENSORS,
    FloatArray,
    IntArray,
    SecomBundle,
    sensor_column,
    sensor_id,
)
from yield_guardian.contracts.base import SensorId, UnitId
from yield_guardian.contracts.line import FdcAlarmLevel, RiskBand
from yield_guardian.contracts.runs import (
    MIN_UNITS_FOR_DRIFT,
    ControlChartsResult,
    DriftHealthResult,
    RiskValidity,
    SensorRiskResult,
    SensorUnitInput,
)
from yield_guardian.contracts.secom import FdcLimits, MetricValue, SensorStatus
from yield_guardian.contracts.services import InvalidArgumentError
from yield_guardian.live.protocols import NeedsInput, Picked

BoolArray = npt.NDArray[np.bool_]

TOP_FEATURES = 15
TOP_CONTRIBUTIONS = 10
SAMPLE_UNITS = 40
MAD_TO_SD = 1.482602218505602  # 1 / Phi^-1(3/4), as yg_secom.fdc
STATUSES: tuple[SensorStatus, ...] = ("ok", "watch", "maintenance", "dead")


class _RunConfig(BaseModel):
    """The configuration keys of metrics.json (`run.config`) the live stages use."""

    model_config = ConfigDict(extra="ignore", frozen=True, allow_inf_nan=False)

    ewma_lambda: float
    ewma_l: float
    cusum_k: float
    cusum_h: float
    leading_groups: int
    stability_threshold: float
    correlation_min_pairs: int
    fdr_q: float
    health_min_window_readings: int
    health_flatline_probability: float
    health_stuck_family_alpha: float
    health_jump_reference_share: float
    health_watch_out_of_reference: float
    health_maintenance_out_of_reference: float
    health_watch_window_missing: float
    health_maintenance_window_missing: float
    health_normal_missing: float


# ---------------------------------------------------------------------------------------------
# Formulas (each the same as its yg_secom counterpart, named in the docstring)
# ---------------------------------------------------------------------------------------------


def platt(raw: FloatArray, a: float, b: float) -> FloatArray:
    """``p = 1 / (1 + exp(a z + b))`` (yg_secom.calibration.PlattCalibrator.predict)."""
    x = -(a * raw + b)
    out = np.empty_like(x)
    positive = x >= 0
    out[positive] = 1.0 / (1.0 + np.exp(-x[positive]))
    e = np.exp(x[~positive])
    out[~positive] = e / (1.0 + e)
    return out


def ewma_chart(u: FloatArray, lam: float, width: float) -> tuple[FloatArray, float, BoolArray]:
    """EWMA from zero with asymptotic limits +/- L sqrt(lam / (2 - lam)) (yg_secom.fdc)."""
    z = np.empty(u.size)
    current = 0.0
    for t, value in enumerate(u.tolist()):
        current = lam * value + (1.0 - lam) * current
        z[t] = current
    limit = width * math.sqrt(lam / (2.0 - lam))
    return z, limit, np.abs(z) > limit


def cusum_chart(u: FloatArray, k: float, h: float) -> tuple[FloatArray, FloatArray, BoolArray]:
    """Two-sided tabular CUSUM; both sums restart at zero after a signal (yg_secom.fdc)."""
    upper = np.empty(u.size)
    lower = np.empty(u.size)
    alarm = np.zeros(u.size, dtype=np.bool_)
    cp = cm = 0.0
    for t, value in enumerate(u.tolist()):
        cp = max(0.0, cp + value - k)
        cm = max(0.0, cm - value - k)
        upper[t], lower[t] = cp, cm
        if cp > h or cm > h:
            alarm[t] = True
            cp = cm = 0.0
    return upper, lower, alarm


def benjamini_hochberg(p_values: FloatArray) -> FloatArray:
    """Benjamini-Hochberg q-values in input order (yg_common.multiple_testing)."""
    m = p_values.size
    if m == 0:
        return np.empty(0)
    order = np.argsort(p_values, kind="mergesort")
    scaled = p_values[order] * m / np.arange(1, m + 1, dtype=np.float64)
    adjusted = np.minimum(np.minimum.accumulate(scaled[::-1])[::-1], 1.0)
    out = np.empty(m, dtype=np.float64)
    out[order] = adjusted
    return out


def binomial_upper_tail(k: int, m: int, p: float) -> float:
    """``P(X >= k)`` for ``X ~ Binomial(m, p)``, summed exactly in log space.

    The same quantity as ``scipy.stats.binom.sf(k - 1, m, p)`` in yg_secom.health; summing the
    upper tail directly keeps tiny tails accurate (no ``1 - cdf`` cancellation).
    """
    if k <= 0:
        return 1.0
    if k > m:
        return 0.0
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    log_factorial = _log_factorials(m)
    i = np.arange(k, m + 1)
    terms = (
        log_factorial[m]
        - log_factorial[i]
        - log_factorial[m - i]
        + i * math.log(p)
        + (m - i) * math.log1p(-p)
    )
    top = float(terms.max())
    return min(1.0, math.exp(top) * float(np.sum(np.exp(terms - top))))


_LOG_FACTORIALS: FloatArray = np.zeros(1)


def _log_factorials(n: int) -> FloatArray:
    """``log(i!)`` for i = 0..n (at least), from math.lgamma, grown on demand."""
    global _LOG_FACTORIALS
    table = _LOG_FACTORIALS
    if table.size <= n:
        table = np.array([math.lgamma(i + 1.0) for i in range(max(n + 1, 2 * table.size))])
        _LOG_FACTORIALS = table
    return table


def _runs(values: FloatArray, min_length: int) -> list[tuple[int, int, float]]:
    """(start, length, value) of the runs of identical consecutive values at least `min_length`
    long, in order (yg_secom.health._runs, keeping only the runs the rules can use)."""
    if values.size == 0:
        return []
    change = np.flatnonzero(np.diff(values) != 0) + 1
    starts = np.r_[0, change]
    lengths = np.diff(np.r_[starts, values.size])
    long_runs = np.flatnonzero(lengths >= min_length)
    return [(int(starts[r]), int(lengths[r]), float(values[starts[r]])) for r in long_runs.tolist()]


def _utc(stamp: datetime) -> datetime:
    """Timestamps without a zone are UTC, as SECOM's own (stored as UTC without conversion)."""
    return stamp.replace(tzinfo=UTC) if stamp.tzinfo is None else stamp.astimezone(UTC)


def _week_start(stamp: datetime) -> date:
    """Monday of the stamp's ISO calendar week, in UTC (yg_secom.eda.week_start)."""
    day = _utc(stamp).date()
    return day - timedelta(days=day.weekday())


# ---------------------------------------------------------------------------------------------
# Reference state derived at start-up
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _LeadingGroup:
    group_id: str
    sensors: list[SensorId]  # members that reach the FDC model, in group order
    columns: IntArray  # their positions among the FDC features
    signs: FloatArray
    mean: float  # of the group score over the FDC reference fit set
    sd: float


@dataclass(frozen=True, slots=True)
class _SensorReference:
    """One sensor in the FDC reference fit set (yg_secom.health, first pass)."""

    present: FloatArray
    missing_rate: float
    value_share: dict[float, float]
    unseen_share: float
    repeat_rate: float
    diff_scale: tuple[float, float] | None  # median and robust SD of reference differences


@dataclass(frozen=True, slots=True)
class _HealthReference:
    sensors: list[_SensorReference]
    jump_z: float | None
    in_control_share: float | None


@dataclass(frozen=True, slots=True)
class SensorHealthDetail:
    """Everything the health rules found for one sensor on one input (health.json's fields)."""

    sensor: SensorId
    status: SensorStatus
    reasons: list[str]
    missing_rate: float
    missing_by_window: list[float]
    flatline_windows: list[int]
    stuck_value: float | None
    jump_units: list[int]  # input positions of the second reading of each flagged difference
    out_of_reference_rate: float | None


@dataclass(frozen=True, slots=True)
class HealthWindow:
    window_id: int
    start: date
    units: list[int]  # input positions


@dataclass(frozen=True, slots=True)
class GroupSeries:
    group_id: str
    sensors: list[SensorId]
    ewma: FloatArray
    ewma_limit: float
    ewma_alarm: BoolArray
    cusum_upper: FloatArray
    cusum_lower: FloatArray
    cusum_alarm: BoolArray


@dataclass(frozen=True, slots=True)
class FdcScores:
    t2: FloatArray
    spe: FloatArray
    contrib_t2: FloatArray
    contrib_spe: FloatArray
    z: FloatArray  # standardised readings after imputation
    missing: BoolArray  # readings that were imputed


@dataclass(frozen=True, slots=True)
class RiskScores:
    raw: FloatArray
    risk: FloatArray
    shap: FloatArray  # [units, model features]
    base: FloatArray


class SecomSensorEngine:
    """The live SECOM engine (`SensorEngine`), built once from the loaded `SecomBundle`.

    Risk validity. The deployed model (model.txt) is the "final model" of
    yg_secom.pipeline.run, step 8: ``Preprocessor.fit(X.iloc[dev])`` and ``fit_lgbm(X_dev,
    ...)`` with ``dev = blocks.development``, the train and validation blocks of
    yg_secom.split.chronological_blocks (every unit before the test block in time order). The
    test block is scored only in step 11, and the rolling-origin fold models that produced the
    validation block's stored risks are not deployed. So a SECOM unit is ``in_training`` when
    the bundle's timeline puts it in the train or validation block, and ``held_out`` when it
    is in the test block; any other unit is ``new_data``. Start-up checks this against the
    bundle: the number of train and validation units must equal preprocess.json's
    ``n_fit_rows`` (the rows the deployed preprocessor and model were fitted on), and the test
    block must be the last stretch of the time order.
    """

    def __init__(self, bundle: SecomBundle) -> None:
        self.bundle = bundle
        files = bundle.bundle
        raw_metrics = _read_json(files.file("metrics.json"))
        preprocess = _read_json(files.file("preprocess.json"))
        try:
            self.config = _RunConfig.model_validate(raw_metrics["run"]["config"])
        except (KeyError, TypeError, ValidationError) as error:
            raise BundleError(f"metrics.json run.config: {error}") from error
        try:
            kept = [str(s) for s in preprocess["kept_sensors"]]
            indicators = [
                str(f).removesuffix(INDICATOR_SUFFIX) for f in preprocess["missingness_indicators"]
            ]
            n_fit_rows = int(preprocess["n_fit_rows"])
        except (KeyError, TypeError, ValueError) as error:
            raise BundleError(f"preprocess.json: {error}") from error
        timeline = bundle.timeline
        self._time_order = np.asarray(timeline.unit_id, dtype=np.int64)
        self._sequence_of = np.asarray(timeline.sequence_of, dtype=np.int64)
        n_units = len(timeline)

        # Blocks and validity.
        blocks = np.array([timeline.block[s] for s in range(n_units)])
        test_positions = np.flatnonzero(blocks == "test")
        if test_positions.size == 0 or not np.array_equal(
            test_positions, np.arange(n_units - test_positions.size, n_units)
        ):
            raise BundleError("timeline.parquet: the test block must be the last units in time.")
        if n_fit_rows != n_units - test_positions.size:
            raise BundleError(
                "preprocess.json n_fit_rows does not match the train and validation blocks."
            )
        self._test_positions = test_positions
        self._block_of_unit = blocks[self._sequence_of]

        # Risk model.
        self._booster = lgb.Booster(model_file=str(files.file("model.txt")))
        self._lock = threading.Lock()
        self.model_features = [*kept, *(f"{s}{INDICATOR_SUFFIX}" for s in indicators)]
        if list(self._booster.feature_name()) != self.model_features or (
            self.model_features != bundle.model_features
        ):
            raise BundleError("model.txt and preprocess.json list different model features.")
        self._kept_columns = np.array([sensor_column(s) for s in kept], dtype=np.int64)
        self._indicator_columns = np.array([sensor_column(s) for s in indicators], dtype=np.int64)
        self._feature_sensor = [*kept, *indicators]
        self._feature_column = np.r_[self._kept_columns, self._indicator_columns]
        self._feature_is_indicator = np.r_[
            np.zeros(len(kept), dtype=np.bool_), np.ones(len(indicators), dtype=np.bool_)
        ]
        group_of = {s: g.group_id for g in bundle.groups.groups for s in g.sensors}
        self._feature_fields = [
            {
                "feature": feature,
                "sensor": sensor,
                "indicator": bool(indicator),
                "group_id": group_of.get(sensor),
            }
            for feature, sensor, indicator in zip(
                self.model_features, self._feature_sensor, self._feature_is_indicator, strict=True
            )
        ]
        splits = np.asarray(self._booster.feature_importance(importance_type="split"))
        self._used_features = np.flatnonzero(splits > 0).astype(np.int64)
        points = bundle.operating_points
        self._default_point = next(p for p in points.points if p.id == points.default)
        self._elevated_point = max(
            (p for p in points.points if p.target_fpr is not None),
            key=lambda p: float(p.target_fpr or 0.0),
        )
        self._skill = self._skill_estimates()
        self._caution = self._caution_sentence()

        # Control charts.
        with np.load(files.file("fdc_model.npz"), allow_pickle=False) as model:
            self.fdc_features = [str(f) for f in model["features"].tolist()]
            self._fdc_columns = np.array(
                [sensor_column(s) for s in self.fdc_features], dtype=np.int64
            )
            self._impute = np.asarray(model["impute_values"], dtype=np.float64)
            self._center = np.asarray(model["center"], dtype=np.float64)
            self._scale = np.asarray(model["scale"], dtype=np.float64)
            self._loadings = np.asarray(model["loadings"], dtype=np.float64)
            self.n_components = int(model["n_components"])
            self._lambda = np.asarray(model["eigenvalues"], dtype=np.float64)[: self.n_components]
            self.limits = FdcLimits(
                t2_99=float(model["t2_limit_99"]),
                t2_999=float(model["t2_limit_999"]),
                spe_99=float(model["spe_limit_99"]),
                spe_999=float(model["spe_limit_999"]),
            )
            model_reference = np.asarray(model["reference_unit_ids"], dtype=np.int64)
        if self._loadings.shape != (len(self.fdc_features), self.n_components):
            raise BundleError("fdc_model.npz: loadings must be [features, n_components].")
        if not np.all(self._scale > 0) or not np.all(self._lambda > 0):
            raise BundleError("fdc_model.npz: scales and kept eigenvalues must be positive.")

        # Reference units (FDC fit set, and the held-out later half of the stationary stretch).
        try:
            reference = raw_metrics["fdc"]["reference"]
            fit_ids = np.asarray(reference["fit_unit_ids"], dtype=np.int64)
            held_ids = np.asarray(reference["held_out_unit_ids"], dtype=np.int64)
        except (KeyError, TypeError) as error:
            raise BundleError(f"metrics.json fdc.reference: {error}") from error
        if not np.array_equal(fit_ids, model_reference):
            raise BundleError("metrics.json and fdc_model.npz list different reference units.")
        self.reference_units = frozenset(fit_ids.tolist())
        readings = bundle.source.readings
        self._leading = self._leading_groups(readings, fit_ids, raw_metrics, blocks)
        self._health_reference = self._derive_health_reference(
            readings, fit_ids, held_ids, raw_metrics
        )
        used = set(self._feature_sensor) | set(self.fdc_features)
        self._unmonitored = [sensor_id(c) for c in range(N_SENSORS) if sensor_id(c) not in used]

    # SensorEngine ------------------------------------------------------------------------------

    def unmonitored_sensors(self) -> list[SensorId]:
        """Sensors that reach neither the risk model nor the control charts."""
        return list(self._unmonitored)

    def risk(self, units: Sequence[SensorUnitInput]) -> SensorRiskResult:
        if not units:
            raise NeedsInput("The failure risk needs at least one sensor unit.")
        values = readings_matrix(units)
        scores = self.risk_scores(values)
        high, elevated = self._default_point.threshold, self._elevated_point.threshold
        # Features no tree splits on have a SHAP value of exactly zero for every unit, and a
        # zero contribution is never listed, so the ranking only needs the features in use.
        used = self._used_features
        shap_used = scores.shap[:, used]
        ranked = used[top_indices(np.abs(shap_used), min(TOP_FEATURES, used.size))]
        top_shap = np.take_along_axis(scores.shap, ranked, axis=1).tolist()
        top_value = np.take_along_axis(values, self._feature_column[ranked], axis=1)
        top_value = np.where(self._feature_is_indicator[ranked], np.isnan(top_value), top_value)
        top_values = _nullable(top_value, np.isnan(top_value))
        items: list[dict[str, Any]] = []
        for i, unit in enumerate(units):
            risk = float(scores.risk[i])
            band: RiskBand = "high" if risk >= high else "elevated" if risk >= elevated else "low"
            top = [
                {**self._feature_fields[j], "value": value, "shap": contribution}
                for j, value, contribution in zip(
                    ranked[i].tolist(), top_values[i], top_shap[i], strict=True
                )
                if contribution != 0.0
            ]
            items.append(
                {
                    "index": i,
                    "unit_id": unit.unit_id,
                    "risk": risk,
                    "band": band,
                    "above_threshold": risk >= high,
                    "validity": self.validity(unit),
                    "raw_score": float(scores.raw[i]),
                    "base_value": float(scores.base[i]),
                    "top": top,
                }
            )
        return SensorRiskResult.model_validate(
            {
                "units": items,
                "threshold": high,
                "operating_point": f"{self._default_point.label} on the validation block",
                "elevated_threshold": elevated,
                "skill": self._skill,
                "caution": self._caution,
                "model": self.bundle.bundle.info.bundle,
            }
        )

    def control_charts(self, units: Sequence[SensorUnitInput]) -> ControlChartsResult:
        """T², SPE, level, top contributions and `z` for every unit.

        `z` is filled for every unit because this is the stored stage result that GET /runs/{id}
        returns (RunReader: "z for every unit"); the stream event carries it for at most the
        first 200 units (UnitChartResult.z), and that cut is made where the event is built.
        """
        if not units:
            raise NeedsInput("The control charts need at least one sensor unit.")
        scores = self.fdc_scores(readings_matrix(units))
        limits = self.limits
        top_t2 = _top_contributions(scores.contrib_t2, self.fdc_features)
        top_spe = _top_contributions(scores.contrib_spe, self.fdc_features)
        z_values = _nullable(scores.z, scores.missing)
        items: list[dict[str, Any]] = []
        for i, (unit, t2, spe) in enumerate(
            zip(units, scores.t2.tolist(), scores.spe.tolist(), strict=True)
        ):
            level: FdcAlarmLevel = (
                "alarm"
                if t2 > limits.t2_999 or spe > limits.spe_999
                else "warning"
                if t2 > limits.t2_99 or spe > limits.spe_99
                else "none"
            )
            items.append(
                {
                    "index": i,
                    "unit_id": unit.unit_id,
                    "timestamp": None if unit.timestamp is None else _utc(unit.timestamp),
                    "t2": t2,
                    "spe": spe,
                    "level": level,
                    "top_t2": top_t2[i],
                    "top_spe": top_spe[i],
                    "z": z_values[i],
                }
            )
        methods = self.bundle.methods
        return ControlChartsResult.model_validate(
            {
                "limits": limits,
                "n_components": self.n_components,
                "explained_variance": self.bundle.fdc_explained_variance,
                "features": self.fdc_features,
                "units": items,
                "method": f"{methods.fdc} {methods.contributions}",
                "model": self.bundle.bundle.info.bundle,
            }
        )

    def drift_health(self, units: Sequence[SensorUnitInput]) -> DriftHealthResult:
        stamps = _time_order_or_needs(units)
        values = readings_matrix(units)
        is_reference = np.array(
            [u.source_unit is not None and u.source_unit in self.reference_units for u in units],
            dtype=np.bool_,
        )
        series = self.drift_series(values)
        windows, health = self.health(values, stamps, is_reference)
        config = self.config
        counts = dict.fromkeys(STATUSES, 0)
        for item in health:
            counts[item.status] += 1
        limit = series[0].ewma_limit if series else None
        return DriftHealthResult.model_validate(
            {
                "groups": [
                    {
                        "group_id": g.group_id,
                        "sensors": g.sensors,
                        "ewma": g.ewma.tolist(),
                        "ewma_limit": g.ewma_limit,
                        "cusum_upper": g.cusum_upper.tolist(),
                        "cusum_lower": g.cusum_lower.tolist(),
                        "cusum_h": config.cusum_h,
                        "first_ewma_alarm": _first(g.ewma_alarm),
                        "first_cusum_alarm": _first(g.cusum_alarm),
                    }
                    for g in series
                ],
                "ewma_lambda": config.ewma_lambda,
                "ewma_width": config.ewma_l,
                "cusum_k": config.cusum_k,
                "health": [
                    {"sensor": h.sensor, "status": h.status, "reasons": h.reasons}
                    for h in health
                    if h.status != "ok"
                ],
                "health_counts": counts,
                "rules": self.bundle.health.rules,
                "method": self._drift_method(limit, len(windows)),
            }
        )

    def from_secom(self, unit_ids: Sequence[UnitId]) -> list[SensorUnitInput]:
        n = len(self._sequence_of)
        wrong = [u for u in unit_ids if not 0 <= int(u) < n]
        if wrong:
            raise InvalidArgumentError(
                f"SECOM has units 0 to {n - 1}; {wrong[0]} is not one of them."
            )
        chosen = sorted({int(u) for u in unit_ids}, key=lambda u: int(self._sequence_of[u]))
        source = self.bundle.source
        out: list[SensorUnitInput] = []
        for unit in chosen:
            row = source.readings[unit]
            out.append(
                SensorUnitInput(
                    unit_id=str(unit),
                    timestamp=source.timestamps[unit],
                    readings=_nullable(row, np.isnan(row)),
                    result="fail" if bool(source.failed[unit]) else "pass",
                    source_unit=unit,
                )
            )
        return out

    def sample(self, rng: Random) -> Picked[SensorUnitInput]:
        block = self._test_positions
        length = min(SAMPLE_UNITS, int(block.size))
        windows = int(block.size) - length + 1
        start = rng.randrange(windows)
        positions = block[start : start + length]
        units = self.from_secom(self._time_order[positions].tolist())
        stamps = self.bundle.timeline.timestamp
        first, last = stamps[int(block[0])], stamps[int(block[-1])]
        rule = (
            f"{length} consecutive real SECOM units from the test block, the {block.size} units "
            f"from {first:%Y-%m-%d %H:%M} to {last:%Y-%m-%d %H:%M} that the risk model never "
            f"saw: units {start + 1} to {start + length} of that block in time order "
            f"({stamps[int(positions[0])]:%Y-%m-%d %H:%M} to "
            f"{stamps[int(positions[-1])]:%Y-%m-%d %H:%M}). The first unit was drawn uniformly "
            f"at random, with the run's seed, from the {windows} possible windows."
        )
        return Picked(items=units, rule=rule)

    # Computations (public for the parity tests) ------------------------------------------------

    def validity(self, unit: SensorUnitInput) -> RiskValidity:
        """See the class docstring."""
        if unit.source_unit is None or not 0 <= unit.source_unit < len(self._block_of_unit):
            return "new_data"
        return "held_out" if self._block_of_unit[unit.source_unit] == "test" else "in_training"

    def model_inputs(self, values: FloatArray) -> FloatArray:
        """yg_secom.preprocess.Preprocessor.transform: kept sensors as read (missing stays
        missing), then a 0/1 missingness indicator per selected sensor."""
        return np.column_stack(
            [
                values[:, self._kept_columns],
                np.isnan(values[:, self._indicator_columns]).astype(np.float64),
            ]
        )

    def risk_scores(self, values: FloatArray) -> RiskScores:
        """Raw log-odds (yg_secom.models.lgbm_raw), Platt risk and TreeSHAP (lgbm_shap)."""
        features = self.model_inputs(values)
        with self._lock:
            raw = np.asarray(self._booster.predict(features, raw_score=True), dtype=np.float64)
            contrib = np.asarray(
                self._booster.predict(features, pred_contrib=True), dtype=np.float64
            )
        calibrator = self.bundle.calibrator
        return RiskScores(
            raw=raw,
            risk=platt(raw, calibrator.a, calibrator.b),
            shap=contrib[:, :-1],
            base=contrib[:, -1],
        )

    def fdc_scores(self, values: FloatArray) -> FdcScores:
        """yg_secom.fdc.FdcModel.standardize and score."""
        raw = values[:, self._fdc_columns]
        missing = np.isnan(raw)
        z = (np.where(missing, self._impute, raw) - self._center) / self._scale
        loadings, lam = self._loadings, self._lambda
        scores = z @ loadings
        residual = z - scores @ loadings.T
        return FdcScores(
            t2=np.sum(scores**2 / lam, axis=1),
            spe=np.sum(residual**2, axis=1),
            contrib_t2=z * ((scores / lam) @ loadings.T),
            contrib_spe=residual**2,
            z=z,
            missing=missing,
        )

    def drift_series(self, values: FloatArray) -> list[GroupSeries]:
        """EWMA and CUSUM of each leading group's standardised score, units in input order
        (yg_secom.pipeline._fdc, small-shift charts)."""
        z = self.fdc_scores(values).z
        config = self.config
        out = []
        for group in self._leading:
            score = np.mean(z[:, group.columns] * group.signs, axis=1)
            u = (score - group.mean) / group.sd
            ewma, limit, ewma_alarm = ewma_chart(u, config.ewma_lambda, config.ewma_l)
            upper, lower, cusum_alarm = cusum_chart(u, config.cusum_k, config.cusum_h)
            out.append(
                GroupSeries(
                    group_id=group.group_id,
                    sensors=group.sensors,
                    ewma=ewma,
                    ewma_limit=limit,
                    ewma_alarm=ewma_alarm,
                    cusum_upper=upper,
                    cusum_lower=lower,
                    cusum_alarm=cusum_alarm,
                )
            )
        return out

    def health(
        self, values: FloatArray, stamps: Sequence[datetime], is_reference: BoolArray
    ) -> tuple[list[HealthWindow], list[SensorHealthDetail]]:
        """yg_secom.health.analyse_health on this input: its own calendar weeks and its own
        readings in the given (time) order, judged against the SECOM reference fit set.

        `is_reference` marks the input units that are reference units themselves (real SECOM
        units of the FDC fit set); every other unit is "after the reference".
        """
        n = values.shape[0]
        weeks = [_week_start(s) for s in stamps]
        starts = sorted(set(weeks))
        index = {w: i for i, w in enumerate(starts)}
        unit_window = np.array([index[w] for w in weeks], dtype=np.int64)
        windows = [
            HealthWindow(i, w, np.flatnonzero(unit_window == i).tolist())
            for i, w in enumerate(starts)
        ]
        n_windows = len(starts)
        per_window = np.bincount(unit_window, minlength=n_windows).astype(np.float64)
        rules = self.config
        reference = self._health_reference
        z_star, p0 = reference.jump_z, reference.in_control_share
        positions = np.arange(n)

        evidence: list[dict[str, Any]] = []
        jump_tests: dict[int, float] = {}
        for j in range(N_SENSORS):
            ref = reference.sensors[j]
            series = values[:, j]
            present = ~np.isnan(series)
            readings = series[present]
            reading_windows = unit_window[present]
            reading_units = positions[present]
            missing_by_window = (
                np.bincount(unit_window, weights=(~present).astype(np.float64), minlength=n_windows)
                / per_window
            ).tolist()

            flatline: list[tuple[int, float, int]] = []
            counts = np.bincount(reading_windows, minlength=n_windows)
            for i in np.flatnonzero(counts >= rules.health_min_window_readings).tolist():
                w_values = readings[reading_windows == i]
                if np.all(w_values == w_values[0]):
                    value = float(w_values[0])
                    p_v = ref.value_share.get(value, ref.unseen_share)
                    if p_v ** int(w_values.size) < rules.health_flatline_probability:
                        flatline.append((i, value, int(w_values.size)))

            stuck: tuple[float, int, float, float] | None = None
            for _, length, value in _runs(readings, rules.health_min_window_readings):
                bound = readings.size * ref.repeat_rate ** (length - 1)
                if bound < rules.health_stuck_family_alpha and (stuck is None or bound < stuck[2]):
                    stuck = (value, length, bound, ref.repeat_rate)

            jumps: list[int] = []
            jump_k = jump_m = 0
            if z_star is not None and ref.diff_scale is not None and readings.size > 1:
                centre, spread = ref.diff_scale
                z = np.abs((np.diff(readings) - centre) / spread)
                ends = reading_units[1:]
                flagged = z > z_star
                jumps = ends[flagged].tolist()
                after = ~is_reference[ends]
                jump_m = int(after.sum())
                jump_k = int(np.sum(flagged & after))
                if jump_m and p0 is not None:
                    jump_tests[j] = binomial_upper_tail(jump_k, jump_m, p0) if jump_k else 1.0

            outside: float | None = None
            if ref.present.size:
                low, high = float(ref.present.min()), float(ref.present.max())
                monitored = series[present & ~is_reference]
                if monitored.size:
                    outside = float(np.mean((monitored < low) | (monitored > high)))
            evidence.append(
                {
                    "present": present,
                    "readings": readings,
                    "missing_by_window": missing_by_window,
                    "flatline": flatline,
                    "stuck": stuck,
                    "jumps": jumps,
                    "jump_k": jump_k,
                    "jump_m": jump_m,
                    "outside": outside,
                }
            )

        jump_columns = sorted(jump_tests)
        jump_q = dict(
            zip(
                jump_columns,
                benjamini_hochberg(np.array([jump_tests[c] for c in jump_columns])).tolist(),
                strict=True,
            )
        )
        details = [
            self._status(j, evidence[j], windows, jump_q.get(j), p0) for j in range(N_SENSORS)
        ]
        return windows, details

    # Internals ----------------------------------------------------------------------------------

    def _status(
        self,
        j: int,
        ev: dict[str, Any],
        windows: list[HealthWindow],
        q_jump: float | None,
        p0: float | None,
    ) -> SensorHealthDetail:
        """yg_secom.health.analyse_health, second pass: the first matching level wins."""
        rules = self.config
        ref = self._health_reference.sensors[j]
        readings: FloatArray = ev["readings"]
        window_missing = np.asarray(ev["missing_by_window"])
        normally_measured = ref.missing_rate <= rules.health_normal_missing
        outside: float | None = ev["outside"]
        dead: list[str] = []
        if readings.size == 0:
            dead.append("never measured")
        elif np.unique(readings).size == 1:
            dead.append(f"a single distinct value ({float(readings[0]):g}) over the whole period")
        maintenance: list[str] = []
        for i, value, n_read in ev["flatline"]:
            maintenance.append(
                f"flatline in week {i} ({windows[i].start.isoformat()}): all {n_read} "
                f"readings equal {value:g}"
            )
        if ev["stuck"] is not None:
            value, length, bound, repeat = ev["stuck"]
            maintenance.append(
                f"stuck value {value:g}: {length} identical consecutive readings; reference "
                f"repeat rate {repeat:.3g}, union bound {bound:.2g} < "
                f"{rules.health_stuck_family_alpha:g}"
            )
        if normally_measured:
            for w in np.flatnonzero(
                window_missing >= rules.health_maintenance_window_missing
            ).tolist():
                maintenance.append(
                    f"week {w} ({windows[w].start.isoformat()}) missing "
                    f"{window_missing[w]:.0%} of readings (reference misses "
                    f"{ref.missing_rate:.0%})"
                )
        if outside is not None and outside >= rules.health_maintenance_out_of_reference:
            maintenance.append(
                f"{outside:.1%} of readings after the reference outside the reference range"
            )
        watch: list[str] = []
        if q_jump is not None and q_jump <= rules.fdr_q and p0 is not None:
            watch.append(
                f"{ev['jump_k']} jumps in {ev['jump_m']} differences after the "
                f"reference (in-control share {p0:.3%}; q = {q_jump:.2g})"
            )
        if normally_measured:
            hits = np.flatnonzero(
                (window_missing >= rules.health_watch_window_missing)
                & (window_missing < rules.health_maintenance_window_missing)
            )
            for w in hits.tolist():
                watch.append(
                    f"week {w} ({windows[w].start.isoformat()}) missing "
                    f"{window_missing[w]:.0%} of readings (reference misses "
                    f"{ref.missing_rate:.0%})"
                )
        if outside is not None and (
            rules.health_watch_out_of_reference
            <= outside
            < rules.health_maintenance_out_of_reference
        ):
            watch.append(
                f"{outside:.1%} of readings after the reference outside the reference range"
            )
        status: SensorStatus
        if dead:
            status, reasons = "dead", dead
        elif maintenance:
            status, reasons = "maintenance", maintenance
        elif watch:
            status, reasons = "watch", watch
        else:
            status, reasons = "ok", []
        return SensorHealthDetail(
            sensor=sensor_id(j),
            status=status,
            reasons=reasons,
            missing_rate=float(np.mean(~ev["present"])),
            missing_by_window=ev["missing_by_window"],
            flatline_windows=[i for i, _, _ in ev["flatline"]],
            stuck_value=ev["stuck"][0] if ev["stuck"] is not None else None,
            jump_units=ev["jumps"],
            out_of_reference_rate=outside,
        )

    def _leading_groups(
        self,
        readings: FloatArray,
        fit_ids: IntArray,
        raw_metrics: dict[str, Any],
        blocks: npt.NDArray[np.str_],
    ) -> list[_LeadingGroup]:
        """The groups the small-shift charts follow, as yg_secom.pipeline._fdc chose them.

        Groups ranked stable first, then by importance; a group is used when at least one
        member reaches the FDC model and its reference score varies; the first
        `leading_groups` are kept. A member's sign is -1 when its Spearman correlation with the
        group's representative over the development period (pairwise-complete, at least
        `correlation_min_pairs` pairs, yg_secom.rootcause.correlated_groups) is negative. The
        score's mean and SD (ddof 1) are taken over the FDC reference fit set. Neither the signs
        nor the mean and SD are stored in the bundle, so they are derived here from the SECOM
        readings; the chosen groups and members must equal metrics.json's record.
        """
        config = self.config
        feature_index = {f: i for i, f in enumerate(self.fdc_features)}
        development = self._time_order[blocks != "test"]
        frame = pd.DataFrame(
            readings[np.sort(development)], columns=[sensor_id(c) for c in range(N_SENSORS)]
        )
        z_fit = self.fdc_scores(readings[fit_ids]).z
        ranked = sorted(
            self.bundle.groups.groups,
            key=lambda g: (g.stability < config.stability_threshold, -g.importance),
        )
        leading: list[_LeadingGroup] = []
        for g in ranked:
            if len(leading) >= config.leading_groups:
                break
            rep = g.representative
            rho = (
                frame[g.sensors]
                .corr(method="spearman", min_periods=config.correlation_min_pairs)
                .to_numpy(dtype=np.float64)
            )
            with_rep = rho[:, g.sensors.index(rep)]
            # An undefined correlation (NaN) is not negative, so it keeps the sign +1.
            signs = [-1.0 if s != rep and with_rep[i] < 0 else 1.0 for i, s in enumerate(g.sensors)]
            used = [
                (feature_index[s], sign, s)
                for s, sign in zip(g.sensors, signs, strict=True)
                if s in feature_index
            ]
            if not used:
                continue
            columns = np.array([c for c, _, _ in used], dtype=np.int64)
            sign_array = np.array([sign for _, sign, _ in used], dtype=np.float64)
            score = np.mean(z_fit[:, columns] * sign_array, axis=1)
            mean, sd = float(score.mean()), float(score.std(ddof=1))
            if not sd > 0:
                continue
            leading.append(
                _LeadingGroup(
                    group_id=g.group_id,
                    sensors=[s for _, _, s in used],
                    columns=columns,
                    signs=sign_array,
                    mean=mean,
                    sd=sd,
                )
            )
        try:
            recorded = [
                (str(r["group_id"]), [str(s) for s in r["members_used"]])
                for r in raw_metrics["fdc"]["small_shift_charts"]["leading_groups"]
            ]
        except (KeyError, TypeError) as error:
            raise BundleError(f"metrics.json leading groups: {error}") from error
        if [(g.group_id, g.sensors) for g in leading] != recorded:
            raise BundleError("The leading groups do not match metrics.json's record.")
        return leading

    def _derive_health_reference(
        self,
        readings: FloatArray,
        fit_ids: IntArray,
        held_ids: IntArray,
        raw_metrics: dict[str, Any],
    ) -> _HealthReference:
        """Per-sensor reference statistics and the jump threshold (yg_secom.health).

        The reference is the FDC fit set in time order. The jump threshold z* is the smallest
        |robust z| of a first difference exceeded by at most `health_jump_reference_share` of
        the pooled reference differences (`calibrate_jumps`); the in-control share used by the
        jump test is the larger of that share and the share flagged on the held-out half. Both
        must equal what metrics.json recorded.
        """
        config = self.config
        order = self._time_order
        fit_in_time = order[np.isin(order, fit_ids)]
        held_in_time = order[np.isin(order, held_ids)]
        sensors: list[_SensorReference] = []
        pooled: list[FloatArray] = []
        held: list[FloatArray] = []
        for j in range(N_SENSORS):
            ref_values = readings[fit_in_time, j]
            present = ref_values[~np.isnan(ref_values)]
            values, counts = np.unique(present, return_counts=True)
            n = present.size
            diffs = np.diff(present)
            scale: tuple[float, float] | None = None
            if diffs.size >= config.health_min_window_readings:
                centre = float(np.median(diffs))
                spread = MAD_TO_SD * float(np.median(np.abs(diffs - centre)))
                if spread > 0:
                    scale = (centre, spread)
                    pooled.append(np.abs((diffs - centre) / spread))
                    ho = readings[held_in_time, j]
                    ho = ho[~np.isnan(ho)]
                    if ho.size > 1:
                        held.append(np.abs((np.diff(ho) - centre) / spread))
            sensors.append(
                _SensorReference(
                    present=present,
                    missing_rate=float(np.mean(np.isnan(ref_values))) if ref_values.size else 1.0,
                    value_share={float(v): int(c) / n for v, c in zip(values, counts, strict=True)},
                    unseen_share=1.0 / n if n else 1.0,
                    repeat_rate=(int(np.sum(diffs == 0)) + 1.0) / (diffs.size + 2.0),
                    diff_scale=scale,
                )
            )
        jump_z: float | None = None
        in_control: float | None = None
        if pooled:
            z_ref = np.sort(np.concatenate(pooled))[::-1]
            allowed = math.floor(config.health_jump_reference_share * z_ref.size + 1e-9)
            jump_z = float(z_ref[min(allowed, z_ref.size - 1)])
            z_held = np.concatenate(held) if held else np.empty(0)
            held_share = float(np.sum(z_held > jump_z)) / z_held.size if z_held.size else 0.0
            in_control = max(config.health_jump_reference_share, held_share)
        try:
            recorded = raw_metrics["health"]["rules"]["jump"]
            recorded_z, recorded_p0 = (
                recorded["threshold_z"],
                recorded["in_control_share_used_by_status_test"],
            )
        except (KeyError, TypeError) as error:
            raise BundleError(f"metrics.json health.rules.jump: {error}") from error
        if not _same(jump_z, recorded_z) or not _same(in_control, recorded_p0):
            raise BundleError(
                "The jump threshold derived from the reference differs from metrics.json."
            )
        return _HealthReference(sensors=sensors, jump_z=jump_z, in_control_share=in_control)

    def _skill_estimates(self) -> list[MetricValue]:
        """Held-out test ROC-AUC and PR-AUC of the deployed model, as metrics.json has them."""
        main = next((m for m in self.bundle.metrics.models if m.main), None)
        if main is None:
            raise BundleError("metrics.json names no main model.")
        by_metric = {m.metric: m for m in main.metrics}
        missing = [m for m in ("roc_auc", "pr_auc") if m not in by_metric]
        if missing:
            raise BundleError(f"metrics.json lacks the main model's test {', '.join(missing)}.")
        return [by_metric["roc_auc"], by_metric["pr_auc"]]

    def _caution_sentence(self) -> str:
        roc, pr = (m.estimate for m in self._skill)
        points = self.bundle.operating_points
        point = self._default_point
        if roc.ci_low is not None and roc.ci_high is not None:
            interval = f", 95% CI {roc.ci_low:.2f} to {roc.ci_high:.2f}"
            weak = (
                "ranks failures no better than chance within its uncertainty"
                if roc.ci_low <= 0.5
                else "ranks failures better than chance, but weakly"
            )
        else:
            interval = ""
            weak = "ranks failures only weakly"
        return (
            f"Weak signal: on the {points.units} held-out test units this model {weak} "
            f"(ROC-AUC {roc.value:.2f}{interval}; PR-AUC {pr.value:.3f} where the failure "
            f"rate is {points.prevalence:.1%}), and at the {point.label} threshold it caught "
            f"{point.tp} of {point.tp + point.fn} test failures. Use it to decide where to "
            "look, not whether a unit will fail."
        )

    def _drift_method(self, limit: float | None, n_windows: int) -> str:
        config = self.config
        limit_text = f" (limits ±{limit:.3f})" if limit is not None else ""
        return (
            f"EWMA (lambda {config.ewma_lambda:g}, L {config.ewma_l:g}, asymptotic limits"
            f"{limit_text}) and two-sided tabular CUSUM (k {config.cusum_k:g}, h "
            f"{config.cusum_h:g}, both sums restart after a signal) on each leading sensor "
            "group's score: the sign-aligned mean of its members' FDC-standardised readings, "
            f"standardised by the mean and SD of the {len(self.reference_units)} SECOM "
            "reference units. The charts start at zero at the first unit of this input. "
            "Sensor health applies the rules to this input's readings in time order and its "
            f"{n_windows} calendar week{'s' if n_windows != 1 else ''}, against the same "
            "reference units."
        )


# ---------------------------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------------------------


def readings_matrix(units: Sequence[SensorUnitInput]) -> FloatArray:
    """[units, 590] float64 readings; null (and anything not finite) is missing (NaN)."""
    if not units:
        return np.empty((0, N_SENSORS))
    values = np.array([u.readings for u in units], dtype=np.float64)
    values[~np.isfinite(values)] = np.nan
    return values


def _time_order_or_needs(units: Sequence[SensorUnitInput]) -> list[datetime]:
    """The units' UTC timestamps when they allow drift and health, else NeedsInput."""
    if len(units) < MIN_UNITS_FOR_DRIFT:
        raise NeedsInput(
            f"Drift and sensor health need at least {MIN_UNITS_FOR_DRIFT} units in time "
            f"order; this input has {len(units)}."
        )
    undated = [u for u in units if u.timestamp is None]
    if undated:
        raise NeedsInput(
            "Drift and sensor health need a timestamp on every unit; "
            f"{len(undated)} of {len(units)} units have none (the first is unit "
            f"{undated[0].unit_id})."
        )
    stamps = [_utc(u.timestamp) for u in units if u.timestamp is not None]
    for i in range(1, len(stamps)):
        if stamps[i] < stamps[i - 1]:
            raise NeedsInput(
                "Drift and sensor health need the units in time order: unit "
                f"{units[i].unit_id} ({stamps[i]:%Y-%m-%d %H:%M:%S}) comes after unit "
                f"{units[i - 1].unit_id} ({stamps[i - 1]:%Y-%m-%d %H:%M:%S}) but is earlier. "
                "Sort the file by timestamp and run it again."
            )
    return stamps


def top_indices(values: FloatArray, k: int) -> IntArray:
    """Per row, the columns of the `k` largest values, largest first and ties by lower column.

    The same as ``np.argsort(-values, axis=1, kind="stable")[:, :k]`` (how SecomInference
    ranks), in linear time per row: a partial partition, then a sort of the `k` picked. A row
    where the partition may have left out a value equal to the k-th largest is ranked by the
    full stable sort instead, so ties resolve exactly as the full sort resolves them.
    """
    n, p = values.shape
    if k <= 0:
        return np.empty((n, 0), dtype=np.int64)
    if k >= p:
        return np.argsort(-values, axis=1, kind="stable").astype(np.int64)
    part = np.argpartition(-values, k - 1, axis=1)[:, :k]
    picked = np.take_along_axis(values, part, axis=1)
    order = np.lexsort((part, -picked), axis=1)
    out = np.take_along_axis(part, order, axis=1).astype(np.int64)
    kth = picked.min(axis=1, keepdims=True)
    ambiguous = np.flatnonzero((values == kth).sum(axis=1) > (picked == kth).sum(axis=1))
    if ambiguous.size:
        out[ambiguous] = np.argsort(-values[ambiguous], axis=1, kind="stable")[:, :k]
    return out


def _top_contributions(
    contributions: FloatArray, features: list[str]
) -> list[list[dict[str, Any]]]:
    """The largest contributions per unit with their shares of the statistic: positive parts
    over their sum (as SecomInference.get_contributions)."""
    top = top_indices(contributions, TOP_CONTRIBUTIONS)
    positive = np.clip(contributions, 0.0, None)
    total = positive.sum(axis=1, keepdims=True)
    shares = np.divide(positive, total, out=np.zeros_like(positive), where=total > 0)
    values = np.take_along_axis(contributions, top, axis=1).tolist()
    top_shares = np.take_along_axis(shares, top, axis=1).tolist()
    names = [[features[j] for j in row] for row in top.tolist()]
    return [
        [
            {"sensor": s, "contribution": c, "share": h}
            for s, c, h in zip(names[i], values[i], top_shares[i], strict=True)
        ]
        for i in range(contributions.shape[0])
    ]


def _nullable(values: FloatArray, missing: BoolArray) -> list[Any]:
    """`values` as nested lists, with None where `missing`."""
    out = values.astype(object)
    out[missing] = None
    result: list[Any] = out.tolist()
    return result


def _first(flags: BoolArray) -> int | None:
    hits = np.flatnonzero(flags)
    return int(hits[0]) if hits.size else None


def _same(a: float | None, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(a, float(b), rel_tol=1e-9, abs_tol=1e-12)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise BundleError(f"{path}: {error}") from error
    if not isinstance(data, dict):
        raise BundleError(f"{path}: expected a JSON object.")
    return data
