"""Bootstrap confidence intervals: stratified, paired and cluster resampling.

All intervals are percentile intervals (Efron and Tibshirani, 1993, ch. 13). Resampling is
driven by ``numpy.random.default_rng(seed)``, so a given seed and input always produce the
same replicates. ``bootstrap`` and ``paired_bootstrap`` draw identical resamples for the
same seed and strata, so per-model intervals and paired differences share their resamples.

Replicates for which the statistic is undefined (NaN) are excluded from the interval; their
number is returned and written into the method description so it is never hidden.

Efron, B. and Tibshirani, R. J. (1993). An Introduction to the Bootstrap. Chapman & Hall.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from yg_common.estimates import Estimate

type Statistic = Callable[..., float]


def stratified_resample_indices(
    strata: npt.ArrayLike, n_resamples: int, seed: int
) -> npt.NDArray[np.intp]:
    """Index matrix ``[n_resamples, n]`` resampling with replacement within each stratum.

    Every resample keeps the stratum sizes of the original sample (for example the number
    of failed and passed units), so statistics such as average precision are always
    defined. Strata are processed in sorted order of their labels.
    """
    labels = np.asarray(strata)
    if labels.ndim != 1:
        raise ValueError("strata must be one-dimensional")
    if n_resamples < 1:
        raise ValueError("n_resamples must be at least 1")
    rng = np.random.default_rng(seed)
    blocks = []
    for value in np.unique(labels):
        members = np.flatnonzero(labels == value)
        draws = rng.integers(0, members.size, size=(n_resamples, members.size))
        blocks.append(members[draws])
    return np.concatenate(blocks, axis=1).astype(np.intp)


def resample_indices(n: int, n_resamples: int, seed: int) -> npt.NDArray[np.intp]:
    """Index matrix ``[n_resamples, n]`` for the ordinary (unstratified) bootstrap."""
    if n < 1 or n_resamples < 1:
        raise ValueError("n and n_resamples must be at least 1")
    rng = np.random.default_rng(seed)
    return rng.integers(0, n, size=(n_resamples, n)).astype(np.intp)


def percentile_interval(replicates: npt.ArrayLike, ci_level: float = 0.95) -> tuple[float, float]:
    """Percentile interval of the finite replicates (NaN, NaN if there are none)."""
    if not 0.0 < ci_level < 1.0:
        raise ValueError(f"ci_level must be in (0, 1), got {ci_level}")
    values = np.asarray(replicates, dtype=np.float64)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return math.nan, math.nan
    alpha = 1.0 - ci_level
    low, high = np.quantile(values, [alpha / 2.0, 1.0 - alpha / 2.0])
    return float(low), float(high)


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    """A bootstrap estimate with its replicates."""

    estimate: Estimate
    replicates: npt.NDArray[np.float64]
    n_invalid: int


@dataclass(frozen=True, slots=True)
class PairedBootstrapResult:
    """Difference ``statistic(a) - statistic(b)`` on shared resamples, with a p-value."""

    difference: Estimate
    p_value: float
    replicates: npt.NDArray[np.float64]
    n_invalid: int


def _method(kind: str, n_resamples: int, n_invalid: int) -> str:
    text = f"{kind} bootstrap, {n_resamples} resamples, percentile interval"
    if n_invalid:
        text += f", {n_invalid} resamples with undefined statistic excluded"
    return text


def _apply(
    statistic: Statistic,
    arrays: Sequence[npt.NDArray[np.generic]],
    indices: npt.NDArray[np.intp],
) -> npt.NDArray[np.float64]:
    out = np.empty(indices.shape[0], dtype=np.float64)
    for b, idx in enumerate(indices):
        out[b] = statistic(*(a[idx] for a in arrays))
    return out


def _as_arrays(arrays: Sequence[npt.ArrayLike]) -> list[npt.NDArray[np.generic]]:
    converted = [np.asarray(a) for a in arrays]
    if not converted:
        raise ValueError("at least one array is required")
    n = converted[0].shape[0]
    if any(a.shape[0] != n for a in converted):
        raise ValueError("all arrays must have the same first dimension")
    return converted


def bootstrap(
    statistic: Statistic,
    *arrays: npt.ArrayLike,
    strata: npt.ArrayLike | None = None,
    n_resamples: int = 2000,
    ci_level: float = 0.95,
    seed: int = 0,
) -> BootstrapResult:
    """Bootstrap percentile interval for ``statistic(*arrays)``.

    Args:
        statistic: Function of the (resampled) arrays returning a float; NaN = undefined.
        *arrays: Arrays aligned on their first dimension (for example labels and scores).
        strata: Optional labels to resample within (stratified bootstrap).
        n_resamples: Number of bootstrap resamples.
        ci_level: Confidence level of the interval.
        seed: Seed of the resampling generator.
    """
    data = _as_arrays(arrays)
    n = data[0].shape[0]
    if strata is None:
        indices = resample_indices(n, n_resamples, seed)
        kind = "ordinary"
    else:
        indices = stratified_resample_indices(strata, n_resamples, seed)
        kind = "stratified"
    point = float(statistic(*data))
    replicates = _apply(statistic, data, indices)
    n_invalid = int(np.sum(~np.isfinite(replicates)))
    low, high = percentile_interval(replicates, ci_level)
    estimate = Estimate(point, low, high, ci_level, _method(kind, n_resamples, n_invalid), n)
    return BootstrapResult(estimate, replicates, n_invalid)


def paired_bootstrap(
    statistic: Callable[[npt.NDArray[np.generic], npt.NDArray[np.generic]], float],
    y_true: npt.ArrayLike,
    scores_a: npt.ArrayLike,
    scores_b: npt.ArrayLike,
    *,
    stratified: bool = True,
    n_resamples: int = 2000,
    ci_level: float = 0.95,
    seed: int = 0,
) -> PairedBootstrapResult:
    """Paired bootstrap of ``statistic(y, a) - statistic(y, b)`` on the same resamples.

    The two-sided p-value for "no difference" inverts the percentile interval:
    ``p = min(1, 2 * min((1 + #{d* <= 0}) / (B + 1), (1 + #{d* >= 0}) / (B + 1)))``, the
    smallest level at which a percentile interval would exclude 0. The +1 terms keep the
    p-value away from an impossible 0, as for Monte Carlo tests (Davison and Hinkley, 1997,
    ch. 4).

    Davison, A. C. and Hinkley, D. V. (1997). Bootstrap Methods and their Application.
    Cambridge University Press.
    """
    y, a, b = _as_arrays([y_true, scores_a, scores_b])
    n = y.shape[0]
    if stratified:
        indices = stratified_resample_indices(y, n_resamples, seed)
        kind = "paired stratified"
    else:
        indices = resample_indices(n, n_resamples, seed)
        kind = "paired ordinary"
    point = float(statistic(y, a) - statistic(y, b))
    replicates = np.empty(n_resamples, dtype=np.float64)
    for i, idx in enumerate(indices):
        yi = y[idx]
        replicates[i] = statistic(yi, a[idx]) - statistic(yi, b[idx])
    finite = replicates[np.isfinite(replicates)]
    n_invalid = int(n_resamples - finite.size)
    low, high = percentile_interval(finite, ci_level)
    if finite.size:
        below = (1 + np.sum(finite <= 0.0)) / (finite.size + 1)
        above = (1 + np.sum(finite >= 0.0)) / (finite.size + 1)
        p_value = float(min(1.0, 2.0 * min(below, above)))
    else:
        p_value = math.nan
    estimate = Estimate(point, low, high, ci_level, _method(kind, n_resamples, n_invalid), n)
    return PairedBootstrapResult(estimate, p_value, replicates, n_invalid)


def cluster_bootstrap(
    statistic: Statistic,
    *arrays: npt.ArrayLike,
    clusters: npt.ArrayLike,
    n_resamples: int = 2000,
    ci_level: float = 0.95,
    seed: int = 0,
) -> BootstrapResult:
    """Cluster bootstrap: resample whole clusters with replacement.

    Use it when observations within a cluster (for example units produced on the same day)
    are correlated, so resampling single observations would understate the uncertainty.
    Each resample draws as many clusters as there are in the data and concatenates their
    members, so its size varies. ``n`` in the estimate is the number of observations; the
    method text states the number of clusters.
    """
    data = _as_arrays(arrays)
    labels = np.asarray(clusters)
    if labels.shape[0] != data[0].shape[0]:
        raise ValueError("clusters must align with the arrays")
    if n_resamples < 1:
        raise ValueError("n_resamples must be at least 1")
    unique = np.unique(labels)
    members = [np.flatnonzero(labels == c) for c in unique]
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, unique.size, size=(n_resamples, unique.size))
    point = float(statistic(*data))
    replicates = np.empty(n_resamples, dtype=np.float64)
    for b, chosen in enumerate(draws):
        idx = np.concatenate([members[c] for c in chosen])
        replicates[b] = statistic(*(a[idx] for a in data))
    n_invalid = int(np.sum(~np.isfinite(replicates)))
    low, high = percentile_interval(replicates, ci_level)
    method = _method(f"cluster ({unique.size} clusters)", n_resamples, n_invalid)
    estimate = Estimate(point, low, high, ci_level, method, int(data[0].shape[0]))
    return BootstrapResult(estimate, replicates, n_invalid)
