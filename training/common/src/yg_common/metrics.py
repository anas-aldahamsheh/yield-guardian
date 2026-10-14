"""Ranking, calibration and fixed false-positive-rate metrics for binary outcomes.

Conventions:

- ``y_true`` holds 1 for the event of interest (a failed unit) and 0 otherwise.
- A unit is *flagged* at threshold ``t`` when its score is ``>= t``.
- Undefined quantities (for example precision when nothing is flagged) are NaN, never 0.

``average_precision`` and ``roc_auc`` reproduce ``sklearn.metrics.average_precision_score``
and ``sklearn.metrics.roc_auc_score`` exactly (ties included); the test suite checks this.
They are reimplemented with NumPy only because bootstrap loops call them thousands of times.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy import stats

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]


def _as_binary(y_true: npt.ArrayLike) -> npt.NDArray[np.int64]:
    y = np.asarray(y_true)
    if y.ndim != 1:
        raise ValueError(f"y_true must be one-dimensional, got shape {y.shape}")
    if y.size and not np.all((y == 0) | (y == 1)):
        raise ValueError("y_true must contain only 0 and 1")
    return y.astype(np.int64)


def _as_scores(scores: npt.ArrayLike, n: int) -> FloatArray:
    s = np.asarray(scores, dtype=np.float64)
    if s.shape != (n,):
        raise ValueError(f"scores must have shape ({n},), got {s.shape}")
    if not np.all(np.isfinite(s)):
        raise ValueError("scores must be finite")
    return s


@dataclass(frozen=True, slots=True)
class BinaryCurve:
    """Confusion counts at every distinct score threshold, highest threshold first."""

    thresholds: FloatArray
    tp: IntArray
    fp: IntArray
    n_pos: int
    n_neg: int

    @property
    def recall(self) -> FloatArray:
        return self.tp / self.n_pos if self.n_pos else np.full(self.tp.shape, np.nan)

    @property
    def fpr(self) -> FloatArray:
        return self.fp / self.n_neg if self.n_neg else np.full(self.fp.shape, np.nan)

    @property
    def precision(self) -> FloatArray:
        flagged = self.tp + self.fp
        return np.asarray(self.tp / flagged, dtype=np.float64)


def binary_curve(y_true: npt.ArrayLike, scores: npt.ArrayLike) -> BinaryCurve:
    """True and false positives when flagging ``score >= t`` for each distinct score ``t``."""
    y = _as_binary(y_true)
    s = _as_scores(scores, y.size)
    if y.size == 0:
        raise ValueError("binary_curve needs at least one observation")
    order = np.argsort(-s, kind="mergesort")
    s_sorted = s[order]
    y_sorted = y[order]
    last_of_tie = np.r_[np.flatnonzero(np.diff(s_sorted)), y.size - 1]
    tp = np.cumsum(y_sorted)[last_of_tie]
    fp = (last_of_tie + 1) - tp
    n_pos = int(y.sum())
    return BinaryCurve(
        thresholds=s_sorted[last_of_tie],
        tp=tp.astype(np.int64),
        fp=fp.astype(np.int64),
        n_pos=n_pos,
        n_neg=int(y.size - n_pos),
    )


def average_precision(y_true: npt.ArrayLike, scores: npt.ArrayLike) -> float:
    """Average precision: sum over thresholds of (recall increment) x precision.

    This is the step-function area under the precision-recall curve used by scikit-learn
    (no interpolation). Its no-skill value equals the prevalence. NaN without positives.
    """
    curve = binary_curve(y_true, scores)
    if curve.n_pos == 0:
        return math.nan
    recall = curve.tp / curve.n_pos
    precision = curve.tp / (curve.tp + curve.fp)
    return float(np.sum(np.diff(recall, prepend=0.0) * precision))


def roc_auc(y_true: npt.ArrayLike, scores: npt.ArrayLike) -> float:
    """Area under the ROC curve via the Mann-Whitney statistic with mid-ranks for ties.

    Equals the probability that a random positive scores higher than a random negative,
    counting ties as one half. NaN when either class is absent.
    """
    y = _as_binary(y_true)
    s = _as_scores(scores, y.size)
    n_pos = int(y.sum())
    n_neg = int(y.size - n_pos)
    if n_pos == 0 or n_neg == 0:
        return math.nan
    ranks = stats.rankdata(s, method="average")
    rank_sum = float(ranks[y == 1].sum())
    return (rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def brier_score(y_true: npt.ArrayLike, probabilities: npt.ArrayLike) -> float:
    """Mean squared difference between predicted probability and outcome."""
    y = _as_binary(y_true)
    p = _as_scores(probabilities, y.size)
    if np.any((p < 0.0) | (p > 1.0)):
        raise ValueError("probabilities must lie in [0, 1]")
    if y.size == 0:
        return math.nan
    return float(np.mean((p - y) ** 2))


def equal_count_bins(probabilities: npt.ArrayLike, n_bins: int) -> npt.NDArray[np.intp]:
    """Assign each value to one of at most ``n_bins`` bins holding about equal counts.

    Bins are contiguous in sorted order (quantile bins). Tied values always share a bin,
    so fewer bins are returned when ties make a boundary impossible (a constant predictor
    gets a single bin). Bin indices are 0-based and consecutive.
    """
    if n_bins < 1:
        raise ValueError(f"n_bins must be at least 1, got {n_bins}")
    p = np.asarray(probabilities, dtype=np.float64)
    n = p.size
    if n == 0:
        return np.zeros(0, dtype=np.intp)
    order = np.argsort(p, kind="mergesort")
    sp = p[order]
    cuts: list[int] = []
    for k in range(1, n_bins):
        target = round(k * n / n_bins)
        if not 0 < target < n:
            continue
        cut = int(np.searchsorted(sp, sp[target], side="left"))
        if cut > 0 and (not cuts or cut > cuts[-1]):
            cuts.append(cut)
    sorted_bins = np.searchsorted(np.asarray(cuts, dtype=np.intp), np.arange(n), side="right")
    bins = np.empty(n, dtype=np.intp)
    bins[order] = sorted_bins
    return bins


@dataclass(frozen=True, slots=True)
class ReliabilityBin:
    """One bin of a reliability diagram."""

    n: int
    n_events: int
    mean_predicted: float
    observed_rate: float
    observed_ci_low: float
    observed_ci_high: float
    min_predicted: float
    max_predicted: float


def reliability_table(
    y_true: npt.ArrayLike,
    probabilities: npt.ArrayLike,
    n_bins: int,
    ci_level: float = 0.95,
) -> list[ReliabilityBin]:
    """Observed event rate against mean predicted probability in equal-count bins.

    Each observed rate carries a Wilson score interval, because bins hold few events.
    """
    y = _as_binary(y_true)
    p = _as_scores(probabilities, y.size)
    bins = equal_count_bins(p, n_bins)
    table: list[ReliabilityBin] = []
    for b in range(int(bins.max()) + 1 if bins.size else 0):
        members = bins == b
        n_b = int(members.sum())
        k_b = int(y[members].sum())
        low, high = wilson_interval(k_b, n_b, ci_level)
        table.append(
            ReliabilityBin(
                n=n_b,
                n_events=k_b,
                mean_predicted=float(p[members].mean()),
                observed_rate=k_b / n_b,
                observed_ci_low=low,
                observed_ci_high=high,
                min_predicted=float(p[members].min()),
                max_predicted=float(p[members].max()),
            )
        )
    return table


def expected_calibration_error(
    y_true: npt.ArrayLike, probabilities: npt.ArrayLike, n_bins: int
) -> float:
    """Expected calibration error with equal-count bins.

    ``ECE = sum_b (n_b / n) * |observed_rate_b - mean_predicted_b|``. The value depends on
    the binning and is biased upwards in small samples; report it with its bins.
    """
    y = _as_binary(y_true)
    p = _as_scores(probabilities, y.size)
    if y.size == 0:
        return math.nan
    bins = equal_count_bins(p, n_bins)
    counts = np.bincount(bins)
    observed = np.bincount(bins, weights=y.astype(np.float64)) / counts
    predicted = np.bincount(bins, weights=p) / counts
    return float(np.sum(counts / y.size * np.abs(observed - predicted)))


def threshold_at_fpr(y_true: npt.ArrayLike, scores: npt.ArrayLike, target_fpr: float) -> float:
    """Smallest threshold whose false-positive rate on these data is at most ``target_fpr``.

    With ``N`` negatives, at most ``k = floor(target_fpr * N)`` of them may be flagged.
    The threshold lies halfway between the (k+1)-th highest negative score, which must not
    be flagged, and the next higher distinct score in the data. Units with scores between
    those two values are therefore treated symmetrically.

    Returns:
        The threshold; flag units with ``score >= threshold``.
    """
    if not 0.0 <= target_fpr <= 1.0:
        raise ValueError(f"target_fpr must be in [0, 1], got {target_fpr}")
    y = _as_binary(y_true)
    s = _as_scores(scores, y.size)
    negatives = np.sort(s[y == 0])[::-1]
    n_neg = negatives.size
    if n_neg == 0:
        raise ValueError("threshold_at_fpr needs at least one negative")
    allowed = math.floor(target_fpr * n_neg + 1e-9)
    if allowed >= n_neg:
        return float(s.min())
    boundary = float(negatives[allowed])
    higher = s[s > boundary]
    if higher.size == 0:
        return float(np.nextafter(boundary, np.inf))
    nxt = float(higher.min())
    midpoint = boundary + (nxt - boundary) / 2.0
    return midpoint if midpoint > boundary else nxt


@dataclass(frozen=True, slots=True)
class Confusion:
    """Confusion counts at one threshold."""

    tp: int
    fp: int
    tn: int
    fn: int

    @property
    def recall(self) -> float:
        positives = self.tp + self.fn
        return self.tp / positives if positives else math.nan

    @property
    def precision(self) -> float:
        flagged = self.tp + self.fp
        return self.tp / flagged if flagged else math.nan

    @property
    def fpr(self) -> float:
        negatives = self.fp + self.tn
        return self.fp / negatives if negatives else math.nan


def confusion_at_threshold(
    y_true: npt.ArrayLike, scores: npt.ArrayLike, threshold: float
) -> Confusion:
    """Confusion counts when flagging ``score >= threshold``."""
    y = _as_binary(y_true)
    s = _as_scores(scores, y.size)
    flagged = s >= threshold
    tp = int(np.sum(flagged & (y == 1)))
    fp = int(np.sum(flagged & (y == 0)))
    fn = int(np.sum(~flagged & (y == 1)))
    tn = int(np.sum(~flagged & (y == 0)))
    return Confusion(tp=tp, fp=fp, tn=tn, fn=fn)


def recall_at_threshold(y_true: npt.ArrayLike, scores: npt.ArrayLike, threshold: float) -> float:
    return confusion_at_threshold(y_true, scores, threshold).recall


def precision_at_threshold(y_true: npt.ArrayLike, scores: npt.ArrayLike, threshold: float) -> float:
    return confusion_at_threshold(y_true, scores, threshold).precision


def fpr_at_threshold(y_true: npt.ArrayLike, scores: npt.ArrayLike, threshold: float) -> float:
    return confusion_at_threshold(y_true, scores, threshold).fpr


def _z(ci_level: float) -> float:
    if not 0.0 < ci_level < 1.0:
        raise ValueError(f"ci_level must be in (0, 1), got {ci_level}")
    return float(stats.norm.ppf(0.5 + ci_level / 2.0))


def wilson_interval(k: int, n: int, ci_level: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion ``k / n``. NaN when ``n == 0``."""
    if n < 0 or not 0 <= k <= max(n, 0):
        raise ValueError(f"need 0 <= k <= n, got k={k}, n={n}")
    if n == 0:
        return math.nan, math.nan
    z = _z(ci_level)
    phat = k / n
    denom = 1.0 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def clopper_pearson_interval(k: int, n: int, ci_level: float = 0.95) -> tuple[float, float]:
    """Exact (Clopper-Pearson) interval for a binomial proportion. NaN when ``n == 0``."""
    if n < 0 or not 0 <= k <= max(n, 0):
        raise ValueError(f"need 0 <= k <= n, got k={k}, n={n}")
    if n == 0:
        return math.nan, math.nan
    alpha = 1.0 - ci_level
    low = 0.0 if k == 0 else float(stats.beta.ppf(alpha / 2, k, n - k + 1))
    high = 1.0 if k == n else float(stats.beta.ppf(1 - alpha / 2, k + 1, n - k))
    return low, high
