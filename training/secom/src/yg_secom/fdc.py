"""Fault detection and classification (FDC): PCA-based multivariate monitoring.

Reference period
    The earliest stretch of *passing* units of the development period (everything before
    the test block). Candidate stretches (the passing units within the first 50%, 40%, ...
    of the development period) are tested for
    stationarity in turn and the longest that passes is kept. The test: KPSS (null
    hypothesis: level stationarity; Kwiatkowski et al., 1992) on each of the first five
    principal-component scores of the candidate, in time order, with a Bonferroni-corrected
    family level of 5% (each test at 1%, against the tabulated 1% critical value). The
    chosen stretch is split in time: the earlier half fits the model, the later half is
    held out to measure the false-alarm rate.

Model (fitted on the earlier half only)
    Features with more than 50% missing readings, a single distinct reading, or a zero
    median absolute deviation (more than half the readings identical) in the reference are
    left out. Missing readings are replaced by the reference median (FDC only). Each
    feature is scaled by its normal-consistent MAD (1.4826 x MAD) and centred at its
    reference mean (after imputation), so reference scores have mean zero as the limits
    assume. PCA keeps the fewest components reaching 90% of the variance; Horn's parallel
    analysis (95th percentile of eigenvalues of column-permuted data) is reported as a
    cross-check.

Statistics and limits (for new observations)
    Hotelling T^2 = sum_a t_a^2 / lambda_a over the kept components, with the Phase II limit
    A (n^2 - 1) / (n (n - A)) F(1 - alpha; A, n - A) (Tracy, Young and Mason, 1992).
    SPE (Q) = squared norm of the residual, with the Jackson-Mudholkar (1979) limit from the
    discarded eigenvalues. Both at alpha = 0.01 and 0.001.

Contributions
    SPE: squared residual per feature (they sum to SPE). T^2: the complete decomposition
    c_j = z_j * (P Lambda^-1 t)_j (they sum to T^2; individual terms can be negative;
    Westerhuis, Gurden and Smilde, 2000).

Small, slow shifts
    EWMA and two-sided tabular CUSUM on standardised scores of the leading sensor groups.
    In-control average run lengths are computed with Markov chains (Brook and Evans, 1972;
    Lucas and Saccucci, 1990) under normality.
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy import stats
from statsmodels.tools.sm_exceptions import InterpolationWarning
from statsmodels.tsa.stattools import kpss

FloatArray = npt.NDArray[np.float64]
MAD_TO_SD = 1.482602218505602  # 1 / Phi^-1(3/4)
KPSS_LEVELS = {0.10: "10%", 0.05: "5%", 0.025: "2.5%", 0.01: "1%"}


def robust_scale(values: FloatArray) -> FloatArray:
    """Normal-consistent median absolute deviation per column, ignoring missing values."""
    median = np.nanmedian(values, axis=0)
    return np.asarray(MAD_TO_SD * np.nanmedian(np.abs(values - median), axis=0), np.float64)


def t2_limit(n_components: int, n_reference: int, alpha: float) -> float:
    """Phase II Hotelling T^2 limit for a new observation (F distribution)."""
    a, n = n_components, n_reference
    if not 0 < a < n:
        raise ValueError(f"need 0 < components < reference size, got A={a}, n={n}")
    return float(a * (n * n - 1) / (n * (n - a)) * stats.f.ppf(1.0 - alpha, a, n - a))


def spe_limit(residual_eigenvalues: FloatArray, alpha: float) -> tuple[float, str]:
    """Jackson-Mudholkar SPE limit; Box's chi-square approximation if h0 <= 0."""
    lam = np.asarray(residual_eigenvalues, dtype=np.float64)
    lam = lam[lam > 0]
    if lam.size == 0:
        return 0.0, "no residual variance"
    th1, th2, th3 = float(lam.sum()), float(np.sum(lam**2)), float(np.sum(lam**3))
    h0 = 1.0 - 2.0 * th1 * th3 / (3.0 * th2 * th2)
    if h0 <= 0:
        g, h = th2 / th1, th1 * th1 / th2
        return float(g * stats.chi2.ppf(1.0 - alpha, h)), "Box chi-square approximation"
    c = float(stats.norm.ppf(1.0 - alpha))
    inner = c * math.sqrt(2.0 * th2 * h0 * h0) / th1 + 1.0 + th2 * h0 * (h0 - 1.0) / (th1 * th1)
    return float(th1 * inner ** (1.0 / h0)), "Jackson-Mudholkar"


def parallel_analysis(
    Z: FloatArray, iterations: int, seed: int, quantile: float = 0.95
) -> tuple[int, FloatArray]:
    """Horn's parallel analysis: components whose eigenvalue beats permuted data.

    Each column is permuted independently (marginals kept, correlations destroyed); a
    component is retained while its eigenvalue exceeds the ``quantile`` of the same-rank
    eigenvalues of the permuted data.
    """
    n = Z.shape[0]
    rng = np.random.default_rng(seed)
    k = min(Z.shape)
    null = np.empty((iterations, k))
    for i in range(iterations):
        Zp = rng.permuted(Z, axis=0)
        Zp = Zp - Zp.mean(axis=0)
        null[i] = np.linalg.svd(Zp, compute_uv=False)[:k] ** 2 / (n - 1)
    threshold = np.quantile(null, quantile, axis=0)
    observed = np.linalg.svd(Z - Z.mean(axis=0), compute_uv=False)[:k] ** 2 / (n - 1)
    below = np.flatnonzero(observed <= threshold)
    retained = int(below[0]) if below.size else k
    return retained, threshold


@dataclass
class FdcModel:
    """A fitted PCA monitoring model (enough to score new units with NumPy only)."""

    features: list[str]
    impute_values: FloatArray
    center: FloatArray
    scale: FloatArray
    loadings: FloatArray
    eigenvalues: FloatArray
    n_components: int
    reference_unit_ids: npt.NDArray[np.int64]
    alphas: tuple[float, float]
    t2_limits: dict[float, float] = field(default_factory=dict)
    spe_limits: dict[float, float] = field(default_factory=dict)
    spe_limit_method: str = ""
    dropped: list[dict[str, str]] = field(default_factory=list)
    explained_variance: float = 0.0

    def standardize(self, X: pd.DataFrame) -> FloatArray:
        values = X.loc[:, self.features].to_numpy(dtype=np.float64)
        values = np.where(np.isnan(values), self.impute_values, values)
        return np.asarray((values - self.center) / self.scale, dtype=np.float64)

    def score(self, X: pd.DataFrame) -> dict[str, FloatArray]:
        Z = self.standardize(X)
        P = self.loadings
        lam = self.eigenvalues[: self.n_components]
        T = Z @ P
        residual = Z - T @ P.T
        return {
            "t2": np.sum(T**2 / lam, axis=1),
            "spe": np.sum(residual**2, axis=1),
            "contrib_t2": Z * ((T / lam) @ P.T),
            "contrib_spe": residual**2,
        }


def fdc_feature_filter(
    X_ref: pd.DataFrame, max_missing: float
) -> tuple[list[str], list[dict[str, str]]]:
    """Features usable for FDC in this reference, and the reasons for the others."""
    keep: list[str] = []
    dropped: list[dict[str, str]] = []
    values = X_ref.to_numpy(dtype=np.float64)
    missing = np.isnan(values).mean(axis=0)
    nunique = X_ref.nunique(dropna=True).to_numpy()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mad = robust_scale(values)
    for j, column in enumerate(X_ref.columns):
        name = str(column)
        if missing[j] > max_missing:
            dropped.append({"sensor": name, "reason": f"more than {max_missing:.0%} missing"})
        elif nunique[j] <= 1:
            dropped.append({"sensor": name, "reason": "constant"})
        elif not mad[j] > 0:
            dropped.append(
                {"sensor": name, "reason": "zero MAD (more than half the readings identical)"}
            )
        else:
            keep.append(name)
    return keep, dropped


def fit_fdc(
    X_ref: pd.DataFrame,
    reference_ids: npt.NDArray[np.int64],
    *,
    max_missing: float,
    variance_target: float,
    alphas: tuple[float, float],
) -> FdcModel:
    features, dropped = fdc_feature_filter(X_ref, max_missing)
    raw = X_ref.loc[:, features].to_numpy(dtype=np.float64)
    medians = np.nanmedian(raw, axis=0)
    scale = robust_scale(raw)
    filled = np.where(np.isnan(raw), medians, raw)
    center = filled.mean(axis=0)
    Z = (filled - center) / scale
    n = Z.shape[0]
    _, s, vt = np.linalg.svd(Z, full_matrices=False)
    eigenvalues = s**2 / (n - 1)
    cumulative = np.cumsum(eigenvalues) / eigenvalues.sum()
    n_components = int(np.searchsorted(cumulative, variance_target - 1e-12, side="left") + 1)
    n_components = min(n_components, n - 2)
    model = FdcModel(
        features=features,
        impute_values=medians,
        center=center,
        scale=scale,
        loadings=vt[:n_components].T.copy(),
        eigenvalues=eigenvalues,
        n_components=n_components,
        reference_unit_ids=np.asarray(reference_ids, dtype=np.int64),
        alphas=alphas,
        dropped=dropped,
        explained_variance=float(cumulative[n_components - 1]),
    )
    methods = set()
    for alpha in alphas:
        model.t2_limits[alpha] = t2_limit(n_components, n, alpha)
        limit, method = spe_limit(eigenvalues[n_components:], alpha)
        model.spe_limits[alpha] = limit
        methods.add(method)
    model.spe_limit_method = ", ".join(sorted(methods))
    return model


def _standardise_candidate(X: pd.DataFrame, max_missing: float) -> FloatArray:
    features, _ = fdc_feature_filter(X, max_missing)
    raw = X.loc[:, features].to_numpy(dtype=np.float64)
    medians = np.nanmedian(raw, axis=0)
    filled = np.where(np.isnan(raw), medians, raw)
    return np.asarray((filled - filled.mean(axis=0)) / robust_scale(raw), dtype=np.float64)


def stationarity_check(Z: FloatArray, n_components: int, family_alpha: float) -> dict[str, Any]:
    """KPSS on the leading PC scores (time order), Bonferroni across components."""
    per_test = family_alpha / n_components
    level = next((v for k, v in KPSS_LEVELS.items() if math.isclose(k, per_test)), None)
    if level is None:
        raise ValueError(f"no tabulated KPSS critical value for level {per_test}")
    u, s, _ = np.linalg.svd(Z - Z.mean(axis=0), full_matrices=False)
    scores = u[:, :n_components] * s[:n_components]
    tests = []
    for i in range(min(n_components, scores.shape[1])):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", InterpolationWarning)
            statistic, p_value, lags, critical = kpss(
                scores[:, i], regression="c", nlags="auto", result_object=False
            )
        trend = stats.spearmanr(np.arange(scores.shape[0]), scores[:, i])
        tests.append(
            {
                "component": i + 1,
                "kpss_statistic": float(statistic),
                "kpss_p_value_bounded": float(p_value),
                "kpss_lags": int(lags),
                "critical_value": float(critical[level]),
                "rejects_stationarity": bool(statistic > critical[level]),
                "spearman_trend_rho": float(trend.statistic),
                "spearman_trend_p": float(trend.pvalue),
            }
        )
    return {
        "test": (
            "KPSS level-stationarity test (statsmodels, regression='c', automatic lags) on "
            f"the first {n_components} principal-component scores, each at level "
            f"{per_test:g} (Bonferroni, family level {family_alpha:g}); statsmodels reports "
            "p-values only within [0.01, 0.10]"
        ),
        "components": tests,
        "stationary": not any(t["rejects_stationarity"] for t in tests),
    }


def select_reference(
    candidate_ids: npt.NDArray[np.int64],
    labels: npt.NDArray[np.int8],
    X: pd.DataFrame,
    *,
    fractions: Sequence[float],
    max_missing: float,
    n_components: int,
    family_alpha: float,
) -> tuple[npt.NDArray[np.int64], dict[str, Any]]:
    """Longest early stretch of passing units that passes the stationarity check.

    ``candidate_ids`` are the development-period units in time order.
    """
    candidates = []
    chosen: npt.NDArray[np.int64] | None = None
    for fraction in fractions:
        prefix = candidate_ids[: round(fraction * candidate_ids.size)]
        passing = prefix[labels[prefix] == 0]
        check = stationarity_check(
            _standardise_candidate(X.iloc[passing], max_missing), n_components, family_alpha
        )
        candidates.append({"fraction": fraction, "passing_units": int(passing.size), **check})
        if check["stationary"]:
            chosen = passing
            break
    stationary = chosen is not None
    if chosen is None:
        fraction = fractions[-1]
        prefix = candidate_ids[: round(fraction * candidate_ids.size)]
        chosen = prefix[labels[prefix] == 0]
    record = {
        "rule": (
            "candidate references are the passing units within the first "
            + ", ".join(f"{f:.0%}" for f in fractions)
            + " of the development period (in time order); the longest stationary one is used"
        ),
        "candidates": candidates,
        "stationary": stationary,
        "units": int(chosen.size),
    }
    return np.asarray(chosen, dtype=np.int64), record


def split_reference(
    reference_ids: npt.NDArray[np.int64], timestamps: pd.Series
) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.int64]]:
    """Earlier half (fit) and later half (held out), never splitting a timestamp."""
    from yg_secom.split import epoch_us  # local import keeps module dependencies one-way

    t = epoch_us(timestamps)[reference_ids]
    cut = reference_ids.size // 2
    cut = int(np.searchsorted(t, t[cut], side="left")) if 0 < cut < t.size else cut
    return reference_ids[:cut], reference_ids[cut:]


def ewma_chart(
    u: FloatArray, lam: float, width: float
) -> tuple[FloatArray, float, npt.NDArray[np.bool_]]:
    """EWMA of standardised data with asymptotic limits +/- L sqrt(lam / (2 - lam))."""
    z = np.empty(u.size)
    current = 0.0
    for t, value in enumerate(u):
        current = lam * value + (1.0 - lam) * current
        z[t] = current
    limit = width * math.sqrt(lam / (2.0 - lam))
    return z, limit, np.abs(z) > limit


def cusum_chart(
    u: FloatArray, k: float, h: float
) -> tuple[FloatArray, FloatArray, npt.NDArray[np.bool_]]:
    """Two-sided tabular CUSUM; both sums restart at zero after a signal."""
    upper = np.empty(u.size)
    lower = np.empty(u.size)
    alarm = np.zeros(u.size, dtype=np.bool_)
    cp = cm = 0.0
    for t, value in enumerate(u):
        cp = max(0.0, cp + value - k)
        cm = max(0.0, cm - value - k)
        upper[t], lower[t] = cp, cm
        if cp > h or cm > h:
            alarm[t] = True
            cp = cm = 0.0
    return upper, lower, alarm


def cusum_arl_one_sided(k: float, h: float, shift: float = 0.0, states: int = 400) -> float:
    """ARL of an upper CUSUM for N(shift, 1) data, Brook-Evans Markov chain."""
    w = 2.0 * h / (2 * states - 1)
    centres = np.arange(states) * w
    upper_edges = centres + w / 2.0
    lower_edges = centres - w / 2.0
    R = np.empty((states, states))
    for i, ci in enumerate(centres):
        R[i, 0] = stats.norm.cdf(w / 2.0 - ci + k - shift)
        R[i, 1:] = stats.norm.cdf(upper_edges[1:] - ci + k - shift) - stats.norm.cdf(
            lower_edges[1:] - ci + k - shift
        )
    arl = np.linalg.solve(np.eye(states) - R, np.ones(states))
    return float(arl[0])


def cusum_arl_two_sided(k: float, h: float, shift: float = 0.0, states: int = 400) -> float:
    """Two-sided CUSUM ARL via 1/ARL = 1/ARL+ + 1/ARL- (standard approximation)."""
    up = cusum_arl_one_sided(k, h, shift, states)
    down = cusum_arl_one_sided(k, h, -shift, states)
    return 1.0 / (1.0 / up + 1.0 / down)


def ewma_arl(lam: float, width: float, shift: float = 0.0, states: int = 301) -> float:
    """ARL of a two-sided EWMA with asymptotic limits, Lucas-Saccucci Markov chain."""
    if states % 2 == 0:
        raise ValueError("use an odd number of states so that zero is a state centre")
    half = width * math.sqrt(lam / (2.0 - lam))
    w = 2.0 * half / states
    centres = -half + (np.arange(states) + 0.5) * w
    R = np.empty((states, states))
    for i, ci in enumerate(centres):
        hi = (centres + w / 2.0 - (1.0 - lam) * ci) / lam
        lo = (centres - w / 2.0 - (1.0 - lam) * ci) / lam
        R[i] = stats.norm.cdf(hi - shift) - stats.norm.cdf(lo - shift)
    arl = np.linalg.solve(np.eye(states) - R, np.ones(states))
    return float(arl[states // 2])


def group_scores(
    Z: FloatArray,
    feature_index: dict[str, int],
    members: Sequence[str],
    signs: Sequence[float],
) -> FloatArray | None:
    """Sign-aligned mean of the members' FDC-standardised values (None if none usable)."""
    columns = [
        (feature_index[m], s) for m, s in zip(members, signs, strict=True) if m in feature_index
    ]
    if not columns:
        return None
    stacked = np.column_stack([Z[:, j] * s for j, s in columns])
    return np.asarray(stacked.mean(axis=1), dtype=np.float64)
