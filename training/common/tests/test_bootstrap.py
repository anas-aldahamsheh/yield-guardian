"""Bootstrap mechanics: determinism, stratification, pairing, clusters, coverage.

All data here are SYNTHETIC test inputs, not results.
"""

from __future__ import annotations

import numpy as np
import pytest

from yg_common.bootstrap import (
    bootstrap,
    cluster_bootstrap,
    paired_bootstrap,
    percentile_interval,
    resample_indices,
    stratified_resample_indices,
)
from yg_common.metrics import average_precision


def _labels_scores(seed: int = 0, n: int = 313) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    y = (rng.random(n) < 0.07).astype(int)
    y[:3] = 1
    a = rng.normal(size=n) + 1.5 * y
    b = rng.normal(size=n) + 0.3 * y
    return y, a, b


def test_same_seed_same_replicates() -> None:
    y, a, _ = _labels_scores()
    r1 = bootstrap(average_precision, y, a, strata=y, n_resamples=300, seed=11)
    r2 = bootstrap(average_precision, y, a, strata=y, n_resamples=300, seed=11)
    r3 = bootstrap(average_precision, y, a, strata=y, n_resamples=300, seed=12)
    np.testing.assert_array_equal(r1.replicates, r2.replicates)
    assert r1.estimate == r2.estimate
    assert not np.array_equal(r1.replicates, r3.replicates)


def test_stratified_indices_keep_class_counts() -> None:
    y = np.array([1] * 7 + [0] * 93)
    idx = stratified_resample_indices(y, 500, seed=3)
    assert idx.shape == (500, 100)
    assert np.all(y[idx].sum(axis=1) == 7)
    # Resampling is with replacement inside each class.
    assert np.any([np.unique(row[:7]).size < 7 for row in idx])


def test_ordinary_indices_shape_and_range() -> None:
    idx = resample_indices(50, 20, seed=1)
    assert idx.shape == (20, 50)
    assert idx.min() >= 0
    assert idx.max() < 50


def test_estimate_fields_and_point_value() -> None:
    y, a, _ = _labels_scores()
    result = bootstrap(average_precision, y, a, strata=y, n_resamples=200, seed=0)
    est = result.estimate
    assert est.value == pytest.approx(average_precision(y, a))
    assert est.ci_low <= est.value <= est.ci_high
    assert est.n == y.size
    assert est.ci_level == 0.95
    assert est.method == "stratified bootstrap, 200 resamples, percentile interval"
    assert result.n_invalid == 0


def test_paired_uses_the_same_resamples_as_single() -> None:
    y, a, b = _labels_scores(1)
    ra = bootstrap(average_precision, y, a, strata=y, n_resamples=250, seed=5)
    rb = bootstrap(average_precision, y, b, strata=y, n_resamples=250, seed=5)
    paired = paired_bootstrap(average_precision, y, a, b, n_resamples=250, seed=5)
    np.testing.assert_allclose(paired.replicates, ra.replicates - rb.replicates, atol=1e-12)


def test_paired_identical_scores_give_zero_difference_and_p_one() -> None:
    y, a, _ = _labels_scores(2)
    paired = paired_bootstrap(average_precision, y, a, a.copy(), n_resamples=200, seed=0)
    assert paired.difference.value == 0.0
    assert paired.difference.ci_low == 0.0
    assert paired.difference.ci_high == 0.0
    assert paired.p_value == 1.0


def test_paired_clear_difference_has_small_p() -> None:
    y, a, b = _labels_scores(3, n=600)
    paired = paired_bootstrap(average_precision, y, a, b, n_resamples=999, seed=0)
    assert paired.difference.value > 0
    assert paired.difference.ci_low > 0
    assert paired.p_value == pytest.approx(2.0 / 1000.0)  # floor: 2 * (1 + 0) / (B + 1)


def test_undefined_replicates_are_counted_not_hidden() -> None:
    y = np.array([1, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    s = np.linspace(0.0, 1.0, 10)
    result = bootstrap(average_precision, y, s, strata=None, n_resamples=400, seed=0)
    assert result.n_invalid > 0  # resamples without the single positive
    assert f"{result.n_invalid} resamples with undefined statistic excluded" in (
        result.estimate.method
    )


def test_cluster_bootstrap_with_singletons_equals_ordinary() -> None:
    rng = np.random.default_rng(4)
    x = rng.normal(size=40)
    ordinary = bootstrap(np.mean, x, n_resamples=300, seed=9)
    clustered = cluster_bootstrap(np.mean, x, clusters=np.arange(40), n_resamples=300, seed=9)
    np.testing.assert_allclose(clustered.replicates, ordinary.replicates)


def test_cluster_bootstrap_is_wider_for_correlated_clusters() -> None:
    rng = np.random.default_rng(5)
    cluster_effect = np.repeat(rng.normal(size=20), 25)
    x = cluster_effect + 0.2 * rng.normal(size=500)
    clusters = np.repeat(np.arange(20), 25)
    naive = bootstrap(np.mean, x, n_resamples=1000, seed=1).estimate
    clustered = cluster_bootstrap(np.mean, x, clusters=clusters, n_resamples=1000, seed=1)
    width_naive = naive.ci_high - naive.ci_low
    width_cluster = clustered.estimate.ci_high - clustered.estimate.ci_low
    assert width_cluster > 2.0 * width_naive
    assert "20 clusters" in clustered.estimate.method


def test_percentile_interval_coverage_on_normal_mean() -> None:
    # Deterministic coverage check: 200 synthetic samples of size 60, 500 resamples each.
    rng = np.random.default_rng(2024)
    covered = 0
    for i in range(200):
        x = rng.normal(loc=1.0, size=60)
        est = bootstrap(np.mean, x, n_resamples=500, seed=i).estimate
        covered += est.ci_low <= 1.0 <= est.ci_high
    assert 0.88 <= covered / 200 <= 0.99


def test_percentile_interval_ignores_nan_and_validates_level() -> None:
    low, high = percentile_interval([np.nan, 1.0, 2.0, 3.0], 0.5)
    assert low == pytest.approx(1.5)
    assert high == pytest.approx(2.5)
    with pytest.raises(ValueError):
        percentile_interval([1.0], 1.0)


def test_input_validation() -> None:
    with pytest.raises(ValueError):
        bootstrap(np.mean, np.ones(3), np.ones(4))
    with pytest.raises(ValueError):
        stratified_resample_indices(np.ones((2, 2)), 10, 0)
