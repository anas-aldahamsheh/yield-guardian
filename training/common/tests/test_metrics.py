"""Metrics against scikit-learn, SciPy and hand-computed values.

All labels and scores here are SYNTHETIC test inputs, not results.
"""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt
import pytest
from scipy import stats
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from yg_common.metrics import (
    average_precision,
    binary_curve,
    brier_score,
    clopper_pearson_interval,
    confusion_at_threshold,
    equal_count_bins,
    expected_calibration_error,
    reliability_table,
    roc_auc,
    threshold_at_fpr,
    wilson_interval,
)


def _synthetic(
    seed: int, n: int = 300, prevalence: float = 0.07, decimals: int | None = None
) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.float64]]:
    rng = np.random.default_rng(seed)
    y = (rng.random(n) < prevalence).astype(np.int64)
    y[0], y[1] = 1, 0  # both classes present
    scores = rng.normal(size=n) + 1.2 * y
    if decimals is not None:
        scores = np.round(scores, decimals)  # creates ties
    return y, scores


@pytest.mark.parametrize("seed", range(25))
@pytest.mark.parametrize("decimals", [None, 1])
def test_average_precision_matches_sklearn(seed: int, decimals: int | None) -> None:
    y, s = _synthetic(seed, decimals=decimals)
    assert average_precision(y, s) == pytest.approx(average_precision_score(y, s), abs=1e-12)


@pytest.mark.parametrize("seed", range(25))
@pytest.mark.parametrize("decimals", [None, 1])
def test_roc_auc_matches_sklearn(seed: int, decimals: int | None) -> None:
    y, s = _synthetic(seed, decimals=decimals)
    assert roc_auc(y, s) == pytest.approx(roc_auc_score(y, s), abs=1e-12)


def test_constant_score_gives_prevalence_and_half() -> None:
    y = np.array([1, 0, 0, 0, 1, 0, 0, 0, 0, 0])
    s = np.full(10, 0.3)
    assert average_precision(y, s) == pytest.approx(0.2)
    assert roc_auc(y, s) == pytest.approx(0.5)


def test_hand_computed_average_precision() -> None:
    # Ranking: 0.9 (pos), 0.8 (neg), 0.7 (pos), 0.1 (neg).
    # Recall steps 0.5 at precision 1, then 0.5 at precision 2/3 -> AP = 0.5 + 1/3.
    y = np.array([1, 0, 1, 0])
    s = np.array([0.9, 0.8, 0.7, 0.1])
    assert average_precision(y, s) == pytest.approx(0.5 + 1.0 / 3.0)
    assert roc_auc(y, s) == pytest.approx(0.75)


def test_undefined_metrics_are_nan() -> None:
    assert math.isnan(average_precision([0, 0, 0], [0.1, 0.2, 0.3]))
    assert math.isnan(roc_auc([1, 1], [0.1, 0.2]))


def test_brier_matches_sklearn() -> None:
    rng = np.random.default_rng(3)
    y = (rng.random(500) < 0.1).astype(int)
    p = rng.random(500)
    assert brier_score(y, p) == pytest.approx(brier_score_loss(y, p), abs=1e-15)
    with pytest.raises(ValueError):
        brier_score([0, 1], [0.5, 1.5])


def test_binary_curve_counts() -> None:
    y = np.array([1, 0, 1, 0, 0])
    s = np.array([0.9, 0.9, 0.5, 0.2, 0.2])
    curve = binary_curve(y, s)
    np.testing.assert_array_equal(curve.thresholds, [0.9, 0.5, 0.2])
    np.testing.assert_array_equal(curve.tp, [1, 2, 2])
    np.testing.assert_array_equal(curve.fp, [1, 1, 3])
    assert (curve.n_pos, curve.n_neg) == (2, 3)


@pytest.mark.parametrize("seed", range(30))
@pytest.mark.parametrize("target", [0.05, 0.10])
@pytest.mark.parametrize("decimals", [None, 1])
def test_threshold_at_fpr_is_feasible_and_tight(
    seed: int, target: float, decimals: int | None
) -> None:
    y, s = _synthetic(seed, n=400, decimals=decimals)
    t = threshold_at_fpr(y, s, target)
    conf = confusion_at_threshold(y, s, t)
    n_neg = int((y == 0).sum())
    assert conf.fp <= math.floor(target * n_neg + 1e-9)
    # Tightness: lowering the threshold to the highest score below it adds false positives
    # beyond the target, or no lower score exists.
    lower = s[s < t]
    if lower.size:
        conf_lower = confusion_at_threshold(y, s, float(lower.max()))
        assert conf_lower.fp > math.floor(target * n_neg + 1e-9)


def test_threshold_at_fpr_hand_example() -> None:
    # Negatives 0.1..1.0 (10 of them); 10% FPR allows one false positive: the threshold
    # sits halfway between 0.9 (must not be flagged) and the next higher score 1.0.
    neg = np.round(np.arange(1, 11) / 10.0, 1)
    y = np.r_[np.zeros(10, dtype=int), [1]]
    s = np.r_[neg, [0.95]]
    t = threshold_at_fpr(y, s, 0.10)
    assert t == pytest.approx(0.925)
    conf = confusion_at_threshold(y, s, t)
    assert (conf.tp, conf.fp, conf.tn, conf.fn) == (1, 1, 9, 0)


def test_threshold_extremes() -> None:
    y = np.array([0, 0, 1])
    s = np.array([0.2, 0.4, 0.6])
    assert threshold_at_fpr(y, s, 1.0) == pytest.approx(0.2)
    t0 = threshold_at_fpr(y, s, 0.0)
    assert 0.4 < t0 <= 0.6
    with pytest.raises(ValueError):
        threshold_at_fpr([1, 1], [0.1, 0.2], 0.05)


def test_confusion_rates() -> None:
    conf = confusion_at_threshold([1, 1, 0, 0, 0], [0.9, 0.1, 0.8, 0.2, 0.3], 0.5)
    assert (conf.tp, conf.fp, conf.tn, conf.fn) == (1, 1, 2, 1)
    assert conf.recall == pytest.approx(0.5)
    assert conf.precision == pytest.approx(0.5)
    assert conf.fpr == pytest.approx(1.0 / 3.0)
    nothing = confusion_at_threshold([1, 0], [0.1, 0.2], 0.9)
    assert math.isnan(nothing.precision)


def test_equal_count_bins_balanced_and_ties_kept_together() -> None:
    p = np.arange(100) / 100.0
    bins = equal_count_bins(p, 5)
    assert np.bincount(bins).tolist() == [20] * 5
    tied = np.array([0.1] * 6 + [0.2] * 4)
    tb = equal_count_bins(tied, 4)
    for value in (0.1, 0.2):
        assert np.unique(tb[tied == value]).size == 1
    assert np.unique(equal_count_bins(np.full(9, 0.5), 3)).tolist() == [0]


def test_ece_hand_example() -> None:
    # Two equal-count bins: [0.1, 0.1] with outcomes [0, 1] -> |0.5 - 0.1| = 0.4;
    # [0.9, 0.9] with outcomes [1, 1] -> |1 - 0.9| = 0.1. ECE = 0.5 * 0.4 + 0.5 * 0.1.
    y = np.array([0, 1, 1, 1])
    p = np.array([0.1, 0.1, 0.9, 0.9])
    assert expected_calibration_error(y, p, 2) == pytest.approx(0.25)
    table = reliability_table(y, p, 2)
    assert [b.n for b in table] == [2, 2]
    assert table[0].observed_rate == pytest.approx(0.5)
    assert table[1].mean_predicted == pytest.approx(0.9)
    for b in table:
        assert b.observed_ci_low <= b.observed_rate <= b.observed_ci_high


@pytest.mark.parametrize(("k", "n"), [(0, 10), (3, 10), (10, 10), (7, 313), (1, 2)])
def test_binomial_intervals_match_scipy(k: int, n: int) -> None:
    result = stats.binomtest(k, n)
    w = result.proportion_ci(confidence_level=0.95, method="wilson")
    cp = result.proportion_ci(confidence_level=0.95, method="exact")
    assert wilson_interval(k, n) == pytest.approx((w.low, w.high), abs=1e-12)
    assert clopper_pearson_interval(k, n) == pytest.approx((cp.low, cp.high), abs=1e-12)


def test_binomial_interval_input_checks() -> None:
    assert all(math.isnan(v) for v in wilson_interval(0, 0))
    with pytest.raises(ValueError):
        wilson_interval(5, 3)
