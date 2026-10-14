"""Metrics with bootstrap confidence intervals, paired comparisons and operating points.

The test block is opened exactly once per run through ``SealedLabels``; every function
here receives labels explicitly, so nothing can read test labels by accident.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
from yg_common.bootstrap import bootstrap, paired_bootstrap
from yg_common.estimates import Estimate
from yg_common.metrics import (
    average_precision,
    binary_curve,
    brier_score,
    confusion_at_threshold,
    expected_calibration_error,
    reliability_table,
    roc_auc,
)

FloatArray = npt.NDArray[np.float64]


class SealError(RuntimeError):
    """The sealed test labels were requested a second time."""


class SealedLabels:
    """Holds the test-block labels until the single final evaluation."""

    def __init__(self, labels: npt.NDArray[np.int8]) -> None:
        self._labels = np.asarray(labels).astype(np.int64).copy()
        self.opened = False

    def open(self) -> npt.NDArray[np.int64]:
        if self.opened:
            raise SealError("the test block has already been evaluated in this run")
        self.opened = True
        return self._labels.copy()


@dataclass(frozen=True)
class ScoredModel:
    """One model's scores on a block: ranking scores and calibrated probabilities."""

    name: str
    score: FloatArray
    probability: FloatArray


def _est(result: Estimate) -> dict[str, Any] | None:
    """Contract form of an estimate, or None when its value is undefined."""
    return result.to_dict() if result.defined else None


def model_metrics(
    y: npt.NDArray[np.int64],
    model: ScoredModel,
    *,
    n_resamples: int,
    seed: int,
    ci_level: float,
    n_bins: int,
) -> dict[str, Any]:
    """PR-AUC, ROC-AUC, Brier and ECE with stratified bootstrap intervals.

    A metric that is undefined on these data is None (never published as a value).
    """

    def ece(yy: FloatArray, pp: FloatArray) -> float:
        return expected_calibration_error(yy, pp, n_bins)

    out: dict[str, Any] = {}
    stats: dict[str, tuple[Callable[..., float], FloatArray]] = {
        "pr_auc": (average_precision, model.score),
        "roc_auc": (roc_auc, model.score),
        "brier": (brier_score, model.probability),
        "ece": (ece, model.probability),
    }
    for name, (fn, values) in stats.items():
        res = bootstrap(
            fn, y, values, strata=y, n_resamples=n_resamples, ci_level=ci_level, seed=seed
        )
        out[name] = _est(res.estimate)
    out["reliability"] = [
        {
            "n": b.n,
            "events": b.n_events,
            "mean_predicted": b.mean_predicted,
            "observed_rate": b.observed_rate,
            "observed_ci_low": b.observed_ci_low,
            "observed_ci_high": b.observed_ci_high,
            "min_predicted": b.min_predicted,
            "max_predicted": b.max_predicted,
        }
        for b in reliability_table(y, model.probability, n_bins, ci_level)
    ]
    return out


def paired_difference(
    y: npt.NDArray[np.int64],
    main: FloatArray,
    other: FloatArray,
    *,
    n_resamples: int,
    seed: int,
    ci_level: float,
) -> dict[str, Any]:
    """Paired stratified bootstrap of the PR-AUC difference (main minus other)."""
    res = paired_bootstrap(
        average_precision, y, main, other, n_resamples=n_resamples, ci_level=ci_level, seed=seed
    )
    return {"difference": _est(res.difference), "p_value": res.p_value}


def operating_point(
    y: npt.NDArray[np.int64],
    risk: FloatArray,
    threshold: float,
    point_id: str,
    target_fpr: float,
    *,
    n_resamples: int,
    seed: int,
    ci_level: float,
) -> dict[str, Any]:
    """Recall, precision and false-positive rate at a fixed threshold, with intervals.

    Undefined quantities (for example precision when no unit is flagged) are None.
    """
    conf = confusion_at_threshold(y, risk, threshold)

    def stat(kind: str) -> Callable[[FloatArray, FloatArray], float]:
        def fn(yy: FloatArray, ss: FloatArray) -> float:
            c = confusion_at_threshold(yy, ss, threshold)
            if kind == "recall":
                return c.recall
            if kind == "precision":
                return c.precision
            if kind == "fpr":
                return c.fpr
            return 100.0 * c.fp / yy.size

        return fn

    results = {
        kind: _est(
            bootstrap(
                stat(kind), y, risk, strata=y, n_resamples=n_resamples, ci_level=ci_level, seed=seed
            ).estimate
        )
        for kind in ("fpr", "recall", "precision", "false_alarms_per_100")
    }
    return {
        "id": point_id,
        "label": f"{100 * target_fpr:g}% false-alarm rate",
        "target_fpr": target_fpr,
        "threshold": threshold,
        "fpr": results["fpr"],
        "recall": results["recall"],
        "precision": results["precision"],
        "false_alarms_per_100": results["false_alarms_per_100"],
        "tp": conf.tp,
        "fp": conf.fp,
        "tn": conf.tn,
        "fn": conf.fn,
    }


def curve_points(y: npt.NDArray[np.int64], risk: FloatArray) -> list[dict[str, float]]:
    """Every distinct threshold on this block with its FPR, recall and precision."""
    curve = binary_curve(y, risk)
    return [
        {
            "threshold": float(t),
            "fpr": float(f),
            "recall": float(r),
            "precision": float(p),
        }
        for t, f, r, p in zip(
            curve.thresholds, curve.fpr, curve.recall, curve.precision, strict=True
        )
    ]
