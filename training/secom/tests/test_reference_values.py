"""SECOM statistics against reference implementations and textbook formulas (Q1).

All inputs are SYNTHETIC test fixtures; no reported result is computed from them.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats
from yg_common.metrics import roc_auc
from yg_common.multiple_testing import benjamini_hochberg

from yg_secom.fdc import spe_limit, t2_limit
from yg_secom.rootcause import univariate_tests


def test_mann_whitney_screen_matches_scipy_and_the_auc() -> None:
    rng = np.random.default_rng(21)
    n = 300
    y = (rng.random(n) < 0.15).astype(np.int64)
    X = pd.DataFrame(
        {
            "S001": rng.normal(size=n) + 0.8 * y,  # shifted in failures
            "S002": rng.normal(size=n),  # no difference
            "S003": rng.integers(0, 4, size=n).astype(float),  # many ties
            "S004": np.where(rng.random(n) < 0.3, np.nan, rng.normal(size=n) - 0.5 * y),
        }
    )
    rows = univariate_tests(X, y, list(X.columns))
    p_values = []
    for sensor in X.columns:
        values = X[sensor].to_numpy()
        present = ~np.isnan(values)
        failed, passed = values[present & (y == 1)], values[present & (y == 0)]
        reference = stats.mannwhitneyu(failed, passed, alternative="two-sided", method="auto")
        row = rows[sensor]
        assert row["mann_whitney_p"] == pytest.approx(reference.pvalue, rel=1e-12)
        assert (row["n_failed"], row["n_passed"]) == (failed.size, passed.size)
        # U / (n1 n0) is the probability that a failed unit reads higher: the ROC AUC.
        auc = roc_auc(y[present], values[present])
        assert row["auc"] == pytest.approx(auc, rel=1e-12)
        p_values.append(reference.pvalue)
    q = benjamini_hochberg(np.asarray(p_values))
    for sensor, q_value in zip(X.columns, q, strict=True):
        assert rows[sensor]["q_value"] == pytest.approx(q_value, rel=1e-12)
    assert rows["S001"]["direction"] == "higher_in_failures"
    assert rows["S004"]["direction"] == "lower_in_failures"


def test_mann_whitney_screen_leaves_untestable_sensors_untested() -> None:
    y = np.array([1, 1, 0, 0, 0, 0, 0], dtype=np.int64)
    X = pd.DataFrame({"S001": [1.0, 2, 3, 4, 5, 6, 7], "S002": [1.0] * 7})
    rows = univariate_tests(X, y, ["S001", "S002"])
    for sensor in ("S001", "S002"):  # too few failures, and a constant sensor
        assert rows[sensor]["direction"] == "not_tested"
        assert rows[sensor]["mann_whitney_p"] is None


@pytest.mark.parametrize("a", [1, 3, 10])
def test_t2_limit_tends_to_the_chi_square_limit_for_a_large_reference(a: int) -> None:
    """A (n^2 - 1) / (n (n - A)) F(A, n - A) -> chi-square(A) as n grows (Montgomery,
    Introduction to Statistical Quality Control, Phase II T^2 limit)."""
    for alpha in (0.01, 0.001):
        assert t2_limit(a, 1_000_000, alpha) == pytest.approx(
            stats.chi2.ppf(1 - alpha, a), rel=2e-4
        )
    # A small reference widens the limit.
    assert t2_limit(a, 30, 0.01) > stats.chi2.ppf(0.99, a)


@pytest.mark.parametrize("k", [5, 40])
def test_spe_limit_is_close_to_the_exact_chi_square_for_equal_eigenvalues(k: int) -> None:
    """With k equal residual eigenvalues lambda, SPE = lambda chi-square(k) exactly."""
    for alpha in (0.01, 0.001):
        limit, method = spe_limit(np.full(k, 0.7), alpha)
        assert method == "Jackson-Mudholkar"
        assert limit == pytest.approx(0.7 * stats.chi2.ppf(1 - alpha, k), rel=0.02)
