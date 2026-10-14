"""Root-cause narrowing: TreeSHAP, correlated sensor groups, stability and chance checks.

Definitions used throughout (all on the development period, that is the train and
validation blocks; test labels are never used here):

- **Sensor SHAP**: TreeSHAP values of LightGBM in log-odds (``pred_contrib``, exact for
  trees; Lundberg et al., 2020). A sensor's value is the sum of its raw column and its
  missingness indicator, so it measures everything the model takes from that sensor.
- **Groups**: hierarchical clustering of the model's sensors with distance
  ``1 - |Spearman rho|`` (pairwise-complete observations, at least ``min_pairs`` pairs,
  otherwise distance 1) and average linkage, cut at distance ``1 - threshold``: inside a
  group, sensors are linked at an average |rho| of at least the threshold.
- **Group importance**: sum over member sensors of the mean |SHAP| over the fitting rows
  of the model (the development period for the reported value).
- **Stability**: share of refits on stratified bootstrap resamples of the development period in
  which a group is among the ``top_k`` most important; stable at ``>= stability_threshold``
  (Meinshausen and Buehlmann, 2010, with bootstrap resamples in place of half-samples).
  Preprocessing is held fixed so that only the model fit is perturbed; each refit gets
  its own seed.
- **Chance check**: the development-period labels are permuted, the full label-dependent
  procedure (missingness-indicator selection and the LightGBM fit with the tuned
  parameters and the same seed) is re-run, and group importance is recomputed. The
  p-value is ``(1 + #{null >= observed}) / (1 + permutations)`` (Phipson and Smyth, 2010);
  q-values by Benjamini-Hochberg across all groups (Altmann et al., 2010, for the
  permutation-importance idea).
- **Univariate screen**: Mann-Whitney U per sensor (failed versus passed, missing readings
  excluded), two-sided, Benjamini-Hochberg across tested sensors.

Lundberg, S. M. et al. (2020). From local explanations to global understanding with
explainable AI for trees. Nature Machine Intelligence, 2, 56-67.
Meinshausen, N. and Buehlmann, P. (2010). Stability selection. JRSS B, 72(4), 417-473.
Altmann, A. et al. (2010). Permutation importance: a corrected feature importance
measure. Bioinformatics, 26(10), 1340-1347.
Phipson, B. and Smyth, G. K. (2010). Permutation p-values should never be zero.
Statistical Applications in Genetics and Molecular Biology, 9(1), article 39.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import lightgbm as lgb
import numpy as np
import numpy.typing as npt
import pandas as pd
from joblib import Parallel, delayed
from scipy import stats
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from yg_common.bootstrap import stratified_resample_indices
from yg_common.multiple_testing import benjamini_hochberg

from yg_secom.models import lgbm_params
from yg_secom.preprocess import Preprocessor, sensor_of

FloatArray = npt.NDArray[np.float64]


def sensor_shap(values: FloatArray, columns: Sequence[str], sensors: Sequence[str]) -> FloatArray:
    """Sum SHAP columns into sensors (an indicator joins its sensor); unknown sensors dropped."""
    index = {s: i for i, s in enumerate(sensors)}
    out = np.zeros((values.shape[0], len(sensors)), dtype=np.float64)
    for j, column in enumerate(columns):
        i = index.get(sensor_of(column))
        if i is not None:
            out[:, i] += values[:, j]
    return out


def _shap(booster: lgb.Booster, X: FloatArray) -> FloatArray:
    contrib = np.asarray(booster.predict(X, pred_contrib=True), dtype=np.float64)
    return contrib[:, :-1]


def group_importance(
    sensor_mean_abs: FloatArray, membership: npt.NDArray[np.intp], n_groups: int
) -> FloatArray:
    return np.bincount(membership, weights=sensor_mean_abs, minlength=n_groups).astype(np.float64)


def top_k_mask(importance: FloatArray, k: int) -> npt.NDArray[np.bool_]:
    """The ``k`` most important groups (ties by group index); zero importance never counts."""
    order = np.lexsort((np.arange(importance.size), -importance))
    chosen = order[:k]
    mask = np.zeros(importance.size, dtype=np.bool_)
    mask[chosen[importance[chosen] > 0]] = True
    return mask


@dataclass(frozen=True)
class Grouping:
    """Correlated sensor groups."""

    sensors: list[str]
    membership: npt.NDArray[np.intp]  # group index per sensor
    n_groups: int
    spearman: pd.DataFrame
    record: dict[str, Any]


def correlated_groups(
    X_train: pd.DataFrame, sensors: Sequence[str], threshold: float, min_pairs: int
) -> Grouping:
    """Average-linkage clusters on 1 - |Spearman rho| over the given rows."""
    block = X_train.loc[:, list(sensors)]
    rho = block.corr(method="spearman", min_periods=min_pairs)
    absolute = rho.abs().to_numpy(dtype=np.float64, copy=True)
    undefined = int(np.isnan(absolute[np.triu_indices_from(absolute, k=1)]).sum())
    distance = 1.0 - np.nan_to_num(absolute, nan=0.0)
    np.fill_diagonal(distance, 0.0)
    distance = np.clip((distance + distance.T) / 2.0, 0.0, 1.0)
    if len(sensors) > 1:
        tree = linkage(squareform(distance, checks=False), method="average")
        labels = fcluster(tree, t=1.0 - threshold + 1e-12, criterion="distance")
    else:
        labels = np.ones(1, dtype=np.int64)
    # Renumber groups 0..G-1 in order of their first sensor (source order).
    first_seen: dict[int, int] = {}
    for label in labels:
        first_seen.setdefault(int(label), len(first_seen))
    membership = np.array([first_seen[int(label)] for label in labels], dtype=np.intp)
    sizes = np.bincount(membership)
    record = {
        "correlation": "spearman, pairwise-complete observations",
        "min_pairs": min_pairs,
        "pairs_undefined": undefined,
        "undefined_pairs_rule": "treated as uncorrelated (distance 1)",
        "linkage": "average",
        "threshold_abs_rho": threshold,
        "sensors": len(sensors),
        "groups": int(sizes.size),
        "singletons": int(np.sum(sizes == 1)),
        "largest_group": int(sizes.max()),
    }
    return Grouping(list(sensors), membership, int(sizes.size), rho, record)


def _fit_and_importance(
    X: FloatArray,
    y: npt.NDArray[np.int64],
    columns: list[str],
    sensors: list[str],
    membership: npt.NDArray[np.intp],
    n_groups: int,
    tuned: dict[str, Any],
    seed: int,
    max_bin: int,
) -> tuple[FloatArray, FloatArray]:
    params, rounds = lgbm_params(tuned, y, seed, 1, max_bin)
    data = lgb.Dataset(
        X,
        label=y.astype(np.float64),
        feature_name=columns,
        params={"max_bin": max_bin, "verbosity": -1, "feature_pre_filter": False},
    )
    booster = lgb.train(params, data, num_boost_round=rounds)
    per_sensor = np.abs(sensor_shap(_shap(booster, X), columns, sensors)).mean(axis=0)
    return group_importance(per_sensor, membership, n_groups), per_sensor


def _stability_task(
    X: FloatArray,
    y: npt.NDArray[np.int64],
    rows: npt.NDArray[np.intp],
    columns: list[str],
    sensors: list[str],
    membership: npt.NDArray[np.intp],
    n_groups: int,
    tuned: dict[str, Any],
    seed: int,
    max_bin: int,
) -> FloatArray:
    importance, _ = _fit_and_importance(
        X[rows], y[rows], columns, sensors, membership, n_groups, tuned, seed, max_bin
    )
    return importance


def _permutation_task(
    X_raw: FloatArray,
    raw_columns: list[str],
    y_perm: npt.NDArray[np.int64],
    fdr: float,
    sensors: list[str],
    membership: npt.NDArray[np.intp],
    n_groups: int,
    tuned: dict[str, Any],
    seed: int,
    max_bin: int,
) -> FloatArray:
    frame = pd.DataFrame(X_raw, columns=raw_columns)
    pre = Preprocessor(fdr=fdr).fit(frame, y_perm)
    X = pre.transform(frame)
    importance, _ = _fit_and_importance(
        X.to_numpy(dtype=np.float64),
        y_perm,
        pre.output_columns,
        sensors,
        membership,
        n_groups,
        tuned,
        seed,
        max_bin,
    )
    return importance


def stability_selection(
    X_model: pd.DataFrame,
    y: npt.NDArray[np.int64],
    grouping: Grouping,
    tuned: dict[str, Any],
    *,
    refits: int,
    top_k: int,
    resample_seed: int,
    model_seeds: Sequence[int],
    max_bin: int,
    n_jobs: int,
) -> tuple[FloatArray, FloatArray]:
    """Selection frequency per group and the importance matrix [refits, groups]."""
    rows = stratified_resample_indices(y, refits, resample_seed)
    X = X_model.to_numpy(dtype=np.float64)
    columns = [str(c) for c in X_model.columns]
    results = Parallel(n_jobs=n_jobs, backend="loky")(
        delayed(_stability_task)(
            X,
            y,
            rows[b],
            columns,
            grouping.sensors,
            grouping.membership,
            grouping.n_groups,
            tuned,
            int(model_seeds[b]),
            max_bin,
        )
        for b in range(refits)
    )
    importance = np.vstack(results)
    selected = np.vstack([top_k_mask(row, top_k) for row in importance])
    return selected.mean(axis=0), importance


def permutation_null(
    X_raw: pd.DataFrame,
    y: npt.NDArray[np.int64],
    grouping: Grouping,
    tuned: dict[str, Any],
    *,
    permutations: int,
    permutation_seed: int,
    model_seed: int,
    fdr: float,
    max_bin: int,
    n_jobs: int,
) -> FloatArray:
    """Group importance under label permutation, matrix [permutations, groups]."""
    rng = np.random.default_rng(permutation_seed)
    perms = [rng.permutation(y) for _ in range(permutations)]
    X = X_raw.to_numpy(dtype=np.float64)
    raw_columns = [str(c) for c in X_raw.columns]
    results = Parallel(n_jobs=n_jobs, backend="loky")(
        delayed(_permutation_task)(
            X,
            raw_columns,
            perms[b],
            fdr,
            grouping.sensors,
            grouping.membership,
            grouping.n_groups,
            tuned,
            model_seed,
            max_bin,
        )
        for b in range(permutations)
    )
    return np.vstack(results)


def permutation_p_values(observed: FloatArray, null: FloatArray) -> FloatArray:
    """``(1 + #{null >= observed}) / (1 + B)`` per group (Phipson and Smyth, 2010)."""
    exceed = np.sum(null >= observed[np.newaxis, :] - 1e-15, axis=0)
    return np.asarray((1.0 + exceed) / (1.0 + null.shape[0]), dtype=np.float64)


def univariate_tests(
    X_train: pd.DataFrame, y: npt.NDArray[np.int64], sensors: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """Mann-Whitney U per sensor with Benjamini-Hochberg q-values."""
    fail = y == 1
    rows: dict[str, dict[str, Any]] = {}
    tested: list[str] = []
    p_values: list[float] = []
    for sensor in sensors:
        values = X_train[sensor].to_numpy(dtype=np.float64)
        present = ~np.isnan(values)
        xf = values[present & fail]
        xp = values[present & ~fail]
        entry: dict[str, Any] = {
            "sensor": sensor,
            "n_failed": int(xf.size),
            "n_passed": int(xp.size),
            "mann_whitney_p": None,
            "q_value": None,
            "auc": None,
            "direction": "not_tested",
        }
        if xf.size >= 3 and xp.size >= 3 and np.unique(np.r_[xf, xp]).size > 1:
            result = stats.mannwhitneyu(xf, xp, alternative="two-sided", method="auto")
            auc = float(result.statistic) / (xf.size * xp.size)
            entry["mann_whitney_p"] = float(result.pvalue)
            entry["auc"] = auc
            entry["direction"] = (
                "higher_in_failures"
                if auc > 0.5
                else "lower_in_failures"
                if auc < 0.5
                else "no_difference"
            )
            tested.append(sensor)
            p_values.append(float(result.pvalue))
        rows[sensor] = entry
    q = benjamini_hochberg(np.asarray(p_values, dtype=np.float64))
    for sensor, q_value in zip(tested, q, strict=True):
        rows[sensor]["q_value"] = float(q_value)
    return rows


def assemble_shap(
    n_units: int,
    features: Sequence[str],
    pieces: Sequence[tuple[npt.NDArray[np.int64], FloatArray, Sequence[str], FloatArray]],
) -> tuple[npt.NDArray[np.float32], npt.NDArray[np.float32]]:
    """Per-unit SHAP [units, model features] and per-unit base value; NaN rows where absent.

    Each piece is (unit ids, SHAP values [rows, model columns], model columns, base values).
    ``features`` must contain every column of every piece. A feature that the explaining
    model does not have contributes exactly 0 to that row, so each row still adds up to its
    model's raw score.
    """
    index = {f: i for i, f in enumerate(features)}
    values = np.full((n_units, len(features)), np.nan, dtype=np.float32)
    base = np.full(n_units, np.nan, dtype=np.float32)
    for unit_ids, shap_values, columns, base_values in pieces:
        if np.any(~np.isnan(base[unit_ids])):
            raise ValueError("a unit received SHAP values from two models")
        unknown = [c for c in columns if c not in index]
        if unknown:
            raise ValueError(f"model columns missing from the feature list: {unknown[:5]}")
        block = np.zeros((len(unit_ids), len(features)), dtype=np.float64)
        block[:, [index[c] for c in columns]] = shap_values
        values[unit_ids] = block.astype(np.float32)
        base[unit_ids] = np.asarray(base_values, dtype=np.float32)
    return values, base
