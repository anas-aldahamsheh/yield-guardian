"""Benjamini-Hochberg against statsmodels and hand-computed values.

All p-values here are SYNTHETIC test inputs, not results.
"""

from __future__ import annotations

import numpy as np
import pytest
from statsmodels.stats.multitest import multipletests

from yg_common.multiple_testing import benjamini_hochberg, bh_reject


def test_hand_computed_example() -> None:
    # m = 5: q_(i) = min_{j>=i} p_(j) * 5 / j
    p = np.array([0.01, 0.04, 0.03, 0.005, 0.2])
    # sorted: 0.005, 0.01, 0.03, 0.04, 0.2 -> scaled 0.025, 0.025, 0.05, 0.05, 0.2
    expected = np.array([0.025, 0.05, 0.05, 0.025, 0.2])
    np.testing.assert_allclose(benjamini_hochberg(p), expected, rtol=0, atol=1e-15)


@pytest.mark.parametrize("seed", range(20))
def test_matches_statsmodels(seed: int) -> None:
    rng = np.random.default_rng(seed)
    m = int(rng.integers(1, 400))
    p = rng.beta(0.4, 2.0, size=m)
    p[: m // 3] = np.round(p[: m // 3], 2)  # ties
    p[rng.random(m) < 0.05] = 1.0
    reject, q_ref, _, _ = multipletests(p, alpha=0.05, method="fdr_bh")
    np.testing.assert_allclose(benjamini_hochberg(p), q_ref, rtol=1e-12, atol=1e-15)
    np.testing.assert_array_equal(bh_reject(p, 0.05), reject)


def test_nan_means_untested() -> None:
    p = np.array([0.01, np.nan, 0.02, np.nan])
    q = benjamini_hochberg(p)
    np.testing.assert_allclose(q[[0, 2]], [0.02, 0.02])
    assert np.isnan(q[1])
    assert np.isnan(q[3])
    assert bh_reject(p, 0.05).tolist() == [True, False, True, False]


def test_all_nan_and_empty() -> None:
    assert np.isnan(benjamini_hochberg([np.nan, np.nan])).all()
    assert benjamini_hochberg([]).size == 0


def test_monotone_in_p_and_bounded() -> None:
    rng = np.random.default_rng(7)
    p = rng.random(200)
    q = benjamini_hochberg(p)
    order = np.argsort(p)
    assert np.all(np.diff(q[order]) >= -1e-15)
    assert np.all((q >= p - 1e-15) & (q <= 1.0))


def test_rejects_invalid_input() -> None:
    with pytest.raises(ValueError):
        benjamini_hochberg([0.1, 1.2])
    with pytest.raises(ValueError):
        benjamini_hochberg([[0.1, 0.2]])
    with pytest.raises(ValueError):
        bh_reject([0.1], alpha=0.0)
