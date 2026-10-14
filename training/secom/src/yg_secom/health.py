"""Sensor health: deterministic rules per sensor and calendar-week window.

Windows are ISO calendar weeks (Monday 00:00 to the next Monday 00:00, UTC as stored).
Units are taken in time order. The reference is the FDC reference fit set (the earlier
half of the stationary early stretch of passing development units); the later half of
that stretch is held out to check the rules on in-control data they were not calibrated
on.

Rules (thresholds in ``PipelineConfig``):

- **Missing rate**: share of units with no reading, overall and per window.
- **Flatline window**: at least ``min_readings`` readings in the window, all identical, and
  improbable under the sensor's reference value frequencies: ``p_v ** n < flatline_p``,
  where ``p_v`` is the reference share of that value (a value never seen in the reference
  counts as seen once).
- **Stuck value**: a run of ``R >= min_readings`` identical consecutive readings with
  ``n_readings * r ** (R - 1) < stuck_alpha`` (a union bound over start positions), where
  ``r = (repeats + 1) / (consecutive pairs + 2)`` is the sensor's own rate of repeating its
  previous reading in the reference (a first-order Markov null). The value of the least
  probable run is reported. An independence null (``p_v`` of the value) was used first and
  rejected: in SECOM identical runs occur in many sensors at exactly the same units (as if
  a reading were recorded once and assigned to several consecutive units), so it flagged
  most continuous sensors. Runs whose unit span is shared by another sensor are counted
  in the summary.
- **Jump**: robust z of the first difference between consecutive readings,
  ``(d - median(d_ref)) / (1.4826 MAD(d_ref))``, beyond a threshold ``z*`` in absolute
  value. ``z*`` is calibrated on the reference: it is the smallest value that at most a
  stated share (``jump_reference_share``) of the reference first differences, pooled over
  every sensor with a computable z, exceed. The share actually flagged on the held-out
  half of the reference is reported as the out-of-sample check. Not computable when
  MAD(d_ref) is zero (mostly discrete sensors).
- **Jump frequency** (status): after the reference fit period, a sensor's number of
  jumps is compared with the in-control share ``p0 = max(target share, held-out share)``
  by a one-sided exact binomial test; Benjamini-Hochberg across sensors. Consecutive
  differences share a reading, so a single spike makes two jumps; the test is therefore
  approximate (anti-conservative for spiky sensors), which the q threshold tempers.
- **Out-of-reference rate**: share of readings of units outside the reference that fall
  outside the reference range [min, max]. For exchangeable continuous data the expected
  rate is 2 / (n_ref + 1); the held-out reference rate is reported as the check.
- **Missingness versus failure**: Fisher's exact test on the development period only
  (missing or not, failed or passed), Benjamini-Hochberg across testable sensors. Test
  labels are never used.

Status (first matching level wins; ``reasons`` lists every rule of that level that fired,
with the values that fired it):

1. ``dead``: no reading at all, or one distinct value over the whole period.
2. ``maintenance``: a flatline window, a stuck value, a window missing at least
   ``maintenance_window_missing`` of readings while the reference missing rate is at most
   ``normal_missing``, or an out-of-reference rate of at least
   ``maintenance_out_of_reference``.
3. ``watch``: jumps more frequent than in control (q <= fdr_q), a window missing at least
   ``watch_window_missing`` while the reference missing rate is at most
   ``normal_missing``, or an out-of-reference rate of at least ``watch_out_of_reference``.
4. ``ok``: none of the above.

Status uses no labels; the failure association is reported beside it, never inside it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy import stats
from yg_common.estimates import Estimate
from yg_common.metrics import clopper_pearson_interval
from yg_common.multiple_testing import benjamini_hochberg

from yg_secom.eda import iso_utc, week_start
from yg_secom.fdc import MAD_TO_SD

FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True)
class HealthRules:
    min_readings: int
    flatline_probability: float
    stuck_alpha: float
    jump_reference_share: float
    jump_fdr_q: float
    watch_out_of_reference: float
    maintenance_out_of_reference: float
    watch_window_missing: float
    maintenance_window_missing: float
    normal_missing: float

    def status_rules(self, jump_z: float | None, jump_p0: float | None) -> list[str]:
        """The status rules in words, with every threshold (as in the model card)."""
        jump = (
            f"jumps (|robust z of a first difference| > {jump_z:.2f}, a threshold exceeded by "
            f"{self.jump_reference_share:.1%} of reference differences) more frequent after the "
            f"reference than the in-control share {jump_p0:.3%} allows (one-sided exact binomial "
            f"test, Benjamini-Hochberg q <= {self.jump_fdr_q:g})"
            if jump_z is not None and jump_p0 is not None
            else "jumps: not computable on these data"
        )
        return [
            "dead: never measured, or a single distinct value over the whole period",
            "maintenance: a flatline window (at least "
            f"{self.min_readings} readings in a calendar week, all identical, with reference "
            f"probability p_v ** n < {self.flatline_probability:g}); or a stuck value (a run of "
            f"R >= {self.min_readings} identical consecutive readings with n_readings * "
            f"r ** (R - 1) < {self.stuck_alpha:g}, r = the sensor's reference rate of "
            "repeating its previous reading, (repeats + 1) / (pairs + 2)); or a week missing "
            "at least "
            f"{self.maintenance_window_missing:.0%} of readings while the reference misses at "
            f"most {self.normal_missing:.0%}; or at least {self.maintenance_out_of_reference:.0%} "
            "of readings after the reference outside the reference range",
            f"watch: {jump}; or a week missing at least {self.watch_window_missing:.0%} of "
            f"readings while the reference misses at most {self.normal_missing:.0%}; or at "
            f"least {self.watch_out_of_reference:.0%} of readings after the reference outside "
            "the reference range",
            "ok: none of the above",
        ]


@dataclass(frozen=True)
class JumpCalibration:
    """The calibrated jump threshold and its checks."""

    threshold_z: float | None
    target_share: float
    reference_differences: int
    reference_share: float | None
    held_out_differences: int
    held_out_flagged: int
    in_control_share: float | None
    sensors_computable: int

    def to_dict(self, ci_level: float = 0.95) -> dict[str, Any]:
        held: dict[str, Any] | None = None
        if self.held_out_differences and self.threshold_z is not None:
            low, high = clopper_pearson_interval(
                self.held_out_flagged, self.held_out_differences, ci_level
            )
            held = Estimate(
                self.held_out_flagged / self.held_out_differences,
                low,
                high,
                ci_level,
                "Clopper-Pearson exact interval (treats differences as independent)",
                self.held_out_differences,
            ).to_dict()
        return {
            "statistic": "robust z of the first difference between consecutive readings: "
            "(d - median of reference differences) / (1.4826 x MAD of reference "
            "differences), per sensor",
            "threshold_z": self.threshold_z,
            "calibration": (
                "smallest |z| exceeded by at most the target share of the first differences "
                "of the reference fit set, pooled over every sensor with a computable z"
            ),
            "target_reference_share": self.target_share,
            "reference_differences": self.reference_differences,
            "reference_share_flagged": self.reference_share,
            "held_out_differences": self.held_out_differences,
            "held_out_share_flagged": held,
            "in_control_share_used_by_status_test": self.in_control_share,
            "sensors_with_computable_z": self.sensors_computable,
        }


def _value_probability(reference: FloatArray) -> tuple[dict[float, float], float]:
    values, counts = np.unique(reference, return_counts=True)
    n = reference.size
    return {float(v): c / n for v, c in zip(values, counts, strict=True)}, (1.0 / n if n else 1.0)


def _repeat_rate(reference: FloatArray) -> float:
    """Smoothed share of consecutive reference readings that repeat the previous one."""
    diffs = np.diff(reference)
    return (int(np.sum(diffs == 0)) + 1.0) / (diffs.size + 2.0)


def _runs(values: FloatArray) -> list[tuple[int, int, float]]:
    """(start, length, value) of runs of identical consecutive values."""
    if values.size == 0:
        return []
    change = np.flatnonzero(np.diff(values) != 0) + 1
    starts = np.r_[0, change]
    ends = np.r_[change, values.size]
    return [(int(s), int(e - s), float(values[s])) for s, e in zip(starts, ends, strict=True)]


def _diff_scale(ref_present: FloatArray, min_readings: int) -> tuple[float, float] | None:
    """Median and robust SD of reference first differences, or None if not computable."""
    diffs = np.diff(ref_present)
    if diffs.size < min_readings:
        return None
    centre = float(np.median(diffs))
    spread = MAD_TO_SD * float(np.median(np.abs(diffs - centre)))
    return (centre, spread) if spread > 0 else None


def calibrate_jumps(
    values: FloatArray,
    fit_in_time: npt.NDArray[np.int64],
    held_in_time: npt.NDArray[np.int64],
    rules: HealthRules,
) -> tuple[JumpCalibration, dict[int, tuple[float, float]]]:
    """Calibrate ``z*`` on the reference fit set; check it on the held-out half.

    Returns the calibration and, per sensor column with a computable z, its (median, scale).
    """
    scales: dict[int, tuple[float, float]] = {}
    pooled: list[FloatArray] = []
    held: list[FloatArray] = []
    for j in range(values.shape[1]):
        ref = values[fit_in_time, j]
        ref = ref[~np.isnan(ref)]
        scale = _diff_scale(ref, rules.min_readings)
        if scale is None:
            continue
        scales[j] = scale
        centre, spread = scale
        pooled.append(np.abs((np.diff(ref) - centre) / spread))
        ho = values[held_in_time, j]
        ho = ho[~np.isnan(ho)]
        if ho.size > 1:
            held.append(np.abs((np.diff(ho) - centre) / spread))
    if not pooled:
        return JumpCalibration(None, rules.jump_reference_share, 0, None, 0, 0, None, 0), scales
    z_ref = np.sort(np.concatenate(pooled))[::-1]
    allowed = math.floor(rules.jump_reference_share * z_ref.size + 1e-9)
    threshold = float(z_ref[min(allowed, z_ref.size - 1)])
    ref_share = float(np.mean(z_ref > threshold))
    z_held = np.concatenate(held) if held else np.empty(0)
    flagged = int(np.sum(z_held > threshold))
    held_share = flagged / z_held.size if z_held.size else 0.0
    calibration = JumpCalibration(
        threshold_z=threshold,
        target_share=rules.jump_reference_share,
        reference_differences=int(z_ref.size),
        reference_share=ref_share,
        held_out_differences=int(z_held.size),
        held_out_flagged=flagged,
        in_control_share=max(rules.jump_reference_share, held_share),
        sensors_computable=len(scales),
    )
    return calibration, scales


def analyse_health(
    X: pd.DataFrame,
    timestamps: pd.Series,
    labels: npt.NDArray[np.int8],
    order: npt.NDArray[np.int64],
    label_ids: npt.NDArray[np.int64],
    reference_ids: npt.NDArray[np.int64],
    held_out_ids: npt.NDArray[np.int64],
    rules: HealthRules,
    fdr_q: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (health.json content, summary for metrics.json).

    ``label_ids`` are the units whose labels may be used (the development period).
    """
    sensors = [str(c) for c in X.columns]
    values = X.to_numpy(dtype=np.float64)
    ordered = values[order]
    weeks = week_start(timestamps)
    week_of_unit = weeks.to_numpy()
    window_starts = np.sort(np.unique(week_of_unit))
    window_index = {w: i for i, w in enumerate(window_starts)}
    unit_window = np.array([window_index[w] for w in week_of_unit], dtype=np.int64)
    windows: list[dict[str, Any]] = []
    for i, w in enumerate(window_starts):
        members = order[unit_window[order] == i]
        start = pd.Timestamp(w)
        windows.append(
            {
                "window_id": i,
                "start": iso_utc(start),
                "end": iso_utc(start + pd.Timedelta(days=7)),
                "unit_ids": [int(u) for u in members],
            }
        )
    ordered_window = unit_window[order]
    n_windows = len(windows)
    is_reference = np.zeros(values.shape[0], dtype=np.bool_)
    is_reference[reference_ids] = True
    ref_in_time = order[np.isin(order, reference_ids)]
    held_in_time = order[np.isin(order, held_out_ids)]
    is_held = np.zeros(values.shape[0], dtype=np.bool_)
    is_held[held_out_ids] = True

    # Missingness versus failure on the development period only.
    lab_missing = np.isnan(values[label_ids])
    lab_fail = labels[label_ids] == 1
    fisher: dict[str, dict[str, Any]] = {}
    tested: list[str] = []
    p_values: list[float] = []
    for j, sensor in enumerate(sensors):
        miss = lab_missing[:, j]
        if 0 < miss.sum() < miss.size:
            table = [
                [int(np.sum(miss & lab_fail)), int(np.sum(miss & ~lab_fail))],
                [int(np.sum(~miss & lab_fail)), int(np.sum(~miss & ~lab_fail))],
            ]
            result = stats.fisher_exact(table)
            odds = float(result.statistic)
            fisher[sensor] = {
                "odds_ratio": odds if np.isfinite(odds) else None,
                "p_value": float(result.pvalue),
                "q_value": None,
            }
            tested.append(sensor)
            p_values.append(float(result.pvalue))
        else:
            fisher[sensor] = {"odds_ratio": None, "p_value": None, "q_value": None}
    for sensor, q in zip(tested, benjamini_hochberg(np.asarray(p_values)), strict=True):
        fisher[sensor]["q_value"] = float(q)

    jump_cal, scales = calibrate_jumps(values, ref_in_time, held_in_time, rules)
    z_star = jump_cal.threshold_z
    p0 = jump_cal.in_control_share

    # First pass: per-sensor evidence.
    evidence: list[dict[str, Any]] = []
    jump_tests: dict[int, float] = {}
    held_outside: list[float] = []
    spans: dict[tuple[int, int], set[int]] = {}
    for j in range(len(sensors)):
        series = ordered[:, j]
        present = ~np.isnan(series)
        readings = series[present]
        reading_windows = ordered_window[present]
        reading_units = order[present]
        missing_by_window = [
            float(np.mean(~present[ordered_window == i])) for i in range(n_windows)
        ]
        ref_values = values[ref_in_time, j]
        ref_present = ref_values[~np.isnan(ref_values)]
        ref_missing_rate = float(np.mean(np.isnan(ref_values))) if ref_values.size else 1.0
        probs, unseen = _value_probability(ref_present)

        flatline: list[tuple[int, float, int]] = []
        for i in range(n_windows):
            w_values = readings[reading_windows == i]
            if w_values.size >= rules.min_readings and np.all(w_values == w_values[0]):
                p_v = probs.get(float(w_values[0]), unseen)
                if p_v**w_values.size < rules.flatline_probability:
                    flatline.append((i, float(w_values[0]), int(w_values.size)))

        stuck: tuple[float, int, float, float] | None = None
        repeat = _repeat_rate(ref_present)
        varies = np.unique(readings).size > 1
        for run_start, length, value in _runs(readings):
            if length < rules.min_readings:
                continue
            if varies:
                spans.setdefault(
                    (int(reading_units[run_start]), int(reading_units[run_start + length - 1])),
                    set(),
                ).add(j)
            bound = readings.size * repeat ** (length - 1)
            if bound < rules.stuck_alpha and (stuck is None or bound < stuck[2]):
                stuck = (value, length, bound, repeat)

        jumps: list[int] = []
        jump_k = jump_m = 0
        if z_star is not None and j in scales and readings.size > 1:
            centre, spread = scales[j]
            z = np.abs((np.diff(readings) - centre) / spread)
            ends = reading_units[1:]
            flagged = z > z_star
            jumps = [int(u) for u in ends[flagged]]
            after = ~is_reference[ends]
            jump_m = int(after.sum())
            jump_k = int(np.sum(flagged & after))
            if jump_m and p0 is not None:
                jump_tests[j] = float(stats.binom.sf(jump_k - 1, jump_m, p0)) if jump_k else 1.0

        outside = None
        if ref_present.size:
            lo, hi = float(ref_present.min()), float(ref_present.max())
            monitored = series[present & ~is_reference[order]]
            if monitored.size:
                outside = float(np.mean((monitored < lo) | (monitored > hi)))
            held_vals = values[held_out_ids, j]
            held_vals = held_vals[~np.isnan(held_vals)]
            if held_vals.size and np.unique(readings).size > 1:
                held_outside.append(float(np.mean((held_vals < lo) | (held_vals > hi))))
        evidence.append(
            {
                "present": present,
                "readings": readings,
                "missing_by_window": missing_by_window,
                "ref_missing_rate": ref_missing_rate,
                "flatline": flatline,
                "stuck": stuck,
                "jumps": jumps,
                "jump_k": jump_k,
                "jump_m": jump_m,
                "outside": outside,
            }
        )

    jump_cols = sorted(jump_tests)
    jump_q = (
        dict(
            zip(
                jump_cols,
                benjamini_hochberg(np.array([jump_tests[c] for c in jump_cols])),
                strict=True,
            )
        )
        if jump_cols
        else {}
    )

    rows = []
    counts = {"ok": 0, "watch": 0, "maintenance": 0, "dead": 0}
    for j, sensor in enumerate(sensors):
        ev = evidence[j]
        readings = ev["readings"]
        window_missing = np.asarray(ev["missing_by_window"])
        normally_measured = ev["ref_missing_rate"] <= rules.normal_missing
        outside = ev["outside"]
        dead: list[str] = []
        if readings.size == 0:
            dead.append("never measured")
        elif np.unique(readings).size == 1:
            dead.append(f"a single distinct value ({readings[0]:g}) over the whole period")
        maintenance: list[str] = []
        for i, value, n_read in ev["flatline"]:
            maintenance.append(
                f"flatline in week {i} ({windows[i]['start'][:10]}): all {n_read} "
                f"readings equal {value:g}"
            )
        if ev["stuck"] is not None:
            value, length, bound, repeat = ev["stuck"]
            maintenance.append(
                f"stuck value {value:g}: {length} identical consecutive readings; reference "
                f"repeat rate {repeat:.3g}, union bound {bound:.2g} < {rules.stuck_alpha:g}"
            )
        if normally_measured:
            for w in np.flatnonzero(window_missing >= rules.maintenance_window_missing):
                maintenance.append(
                    f"week {int(w)} ({windows[int(w)]['start'][:10]}) missing "
                    f"{window_missing[w]:.0%} of readings (reference misses "
                    f"{ev['ref_missing_rate']:.0%})"
                )
        if outside is not None and outside >= rules.maintenance_out_of_reference:
            maintenance.append(
                f"{outside:.1%} of readings after the reference outside the reference range"
            )
        watch: list[str] = []
        q_jump = jump_q.get(j)
        if q_jump is not None and q_jump <= rules.jump_fdr_q:
            watch.append(
                f"{ev['jump_k']} jumps in {ev['jump_m']} differences after the "
                f"reference (in-control share {p0:.3%}; q = {q_jump:.2g})"
            )
        if normally_measured:
            hits = np.flatnonzero(
                (window_missing >= rules.watch_window_missing)
                & (window_missing < rules.maintenance_window_missing)
            )
            for w in hits:
                watch.append(
                    f"week {int(w)} ({windows[int(w)]['start'][:10]}) missing "
                    f"{window_missing[w]:.0%} of readings (reference misses "
                    f"{ev['ref_missing_rate']:.0%})"
                )
        if outside is not None and (
            rules.watch_out_of_reference <= outside < rules.maintenance_out_of_reference
        ):
            watch.append(
                f"{outside:.1%} of readings after the reference outside the reference range"
            )
        if dead:
            status, reasons = "dead", dead
        elif maintenance:
            status, reasons = "maintenance", maintenance
        elif watch:
            status, reasons = "watch", watch
        else:
            status, reasons = "ok", []
        counts[status] += 1
        rows.append(
            {
                "sensor": sensor,
                "missing_rate": float(np.mean(~ev["present"])),
                "missing_by_window": ev["missing_by_window"],
                "flatline_windows": [i for i, _, _ in ev["flatline"]],
                "stuck_value": ev["stuck"][0] if ev["stuck"] is not None else None,
                "jump_unit_ids": ev["jumps"],
                "out_of_reference_rate": outside,
                "missing_vs_failure": fisher[sensor],
                "status": status,
                "reasons": reasons,
            }
        )
    significant = [s for s in tested if (fisher[s]["q_value"] or 1.0) <= fdr_q]
    status_rules = rules.status_rules(z_star, p0)
    live = [r for r in rows if r["status"] != "dead"]
    summary = {
        "rules": {
            "status": status_rules,
            "windows": "ISO calendar weeks, Monday 00:00 to next Monday 00:00 (exclusive)",
            "reference": "FDC reference fit set (earlier half of the stationary early stretch "
            "of passing development units); the later half is held out",
            "jump": jump_cal.to_dict(),
            "out_of_reference_check": {
                "expected_rate_exchangeable_continuous": 2.0 / (reference_ids.size + 1),
                "held_out_reference_rate_median_over_sensors": (
                    float(np.median(held_outside)) if held_outside else None
                ),
                "held_out_sensors_at_or_above_watch_rate": int(
                    np.sum(np.asarray(held_outside) >= rules.watch_out_of_reference)
                ),
                "sensors_checked": len(held_outside),
            },
            "missing_vs_failure": "Fisher exact test on the development period (test labels "
            "never used), Benjamini-Hochberg across testable sensors",
        },
        "reference_units": int(reference_ids.size),
        "held_out_reference_units": int(held_out_ids.size),
        "windows": n_windows,
        "status_counts": counts,
        "live_sensors": len(live),
        "sensors_with_any_jump": int(sum(bool(r["jump_unit_ids"]) for r in live)),
        "sensors_with_jump_rule_not_computable": int(
            sum(1 for j, r in enumerate(rows) if r["status"] != "dead" and j not in scales)
        ),
        "jump_frequency_tests": len(jump_cols),
        "identical_runs": {
            "min_length": rules.min_readings,
            "runs": sum(len(v) for v in spans.values()),
            "sensors": len(set().union(*spans.values())) if spans else 0,
            "runs_sharing_their_unit_span_with_another_sensor": sum(
                len(v) for v in spans.values() if len(v) > 1
            ),
            "largest_number_of_sensors_sharing_one_span": max(
                (len(v) for v in spans.values()), default=0
            ),
        },
        "missingness_associated_with_failure": {
            "tested": len(tested),
            "significant_at_q": fdr_q,
            "sensors": significant,
            "smallest_q": min((fisher[s]["q_value"] for s in tested), default=None),
        },
    }
    document = {"rules": status_rules, "windows": windows, "sensors": rows}
    return document, summary


def status_rank(statuses: Sequence[str]) -> list[int]:
    order = {"dead": 0, "maintenance": 1, "watch": 2, "ok": 3}
    return [order[s] for s in statuses]
