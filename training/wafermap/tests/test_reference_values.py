"""Wafer-map statistics against known values (Q1). CPU only; no raw data.

Synthetic inputs here are test fixtures for the functions only (WORKERS.md rule 6); no
result reported anywhere is computed from them.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats as sps

from wm import stats
from wm.lots import binomial_tests, join_count


def _disc(size: int = 26) -> np.ndarray:
    """A round wafer: 0 outside, 1 (pass) on the die cells."""
    yy, xx = np.indices((size, size)) - (size - 1) / 2
    return (xx**2 + yy**2 <= (size / 2) ** 2).astype(np.uint8)


def _rook_joins(die: np.ndarray) -> int:
    return int((die[:, :-1] & die[:, 1:]).sum() + (die[:-1, :] & die[1:, :]).sum())


def test_join_count_null_mean_matches_the_hypergeometric_expectation() -> None:
    """Under random placement of f fails on n dies with J rook joins,
    E[BB] = J f (f - 1) / (n (n - 1)) (Cliff and Ord, 1981, free sampling without replacement)."""
    rng = np.random.default_rng(31)
    grid = _disc()
    die = grid > 0
    cells = np.flatnonzero(die)
    grid.flat[rng.choice(cells, size=60, replace=False)] = 2
    result = join_count(grid, rng)
    n, f, joins = int(die.sum()), 60, _rook_joins(die.astype(np.int64))
    expected = joins * f * (f - 1) / (n * (n - 1))
    assert (result["dies"], result["fails"]) == (n, f)
    assert result["expected"] == pytest.approx(expected, rel=0.03)


def test_join_count_p_values_are_calibrated_on_random_maps() -> None:
    """Maps with fails placed at random: about 5% of p-values fall at or below 0.05."""
    rng = np.random.default_rng(32)
    grid0 = _disc()
    cells = np.flatnonzero(grid0 > 0)
    p_values = []
    for _ in range(300):
        grid = grid0.copy()
        grid.flat[rng.choice(cells, size=50, replace=False)] = 2
        p_values.append(join_count(grid, rng)["p"])
    share = float(np.mean(np.asarray(p_values) <= 0.05))
    assert 0.02 <= share <= 0.09  # binomial 99% range for 300 maps at 5%


def test_join_count_finds_known_spatial_patterns() -> None:
    rng = np.random.default_rng(33)
    base = _disc()
    ring = base.copy()
    inner = np.zeros_like(base)
    inner[3:-3, 3:-3] = _disc(base.shape[0] - 6)
    ring[(base > 0) & (inner == 0)] = 2  # Edge-Ring: every die near the edge fails
    scratch = base.copy()
    for i in range(5, 21):
        scratch[i, i] = scratch[i, i + 1] = 2  # a diagonal line
    for grid in (ring, scratch):
        result = join_count(grid, rng)
        assert result["p"] == pytest.approx(1 / 1000)
        assert result["z"] > 3


def test_lot_cluster_bootstrap_covers_a_known_mean() -> None:
    """Wafers share a lot effect; true mean 0. Coverage of the 95% interval over 150 data
    sets (binomial sd about 1.8 points)."""
    rng = np.random.default_rng(34)
    lots = np.repeat(np.arange(40), 15)
    covered = 0
    for i in range(150):
        x = rng.normal(size=40)[lots] + rng.normal(size=lots.size)
        est = stats.bootstrap(lambda w, x=x: float(np.average(x, weights=w)), lots, b=300, seed=i)
        covered += est["ci_low"] <= 0.0 <= est["ci_high"]
    assert 0.87 <= covered / 150 <= 0.99


def test_lot_binomial_tests_match_scipy() -> None:
    rng = np.random.default_rng(35)
    patterns = ["Center", "Scratch"]
    reference = pd.DataFrame({"pred": rng.choice(["Center", "Scratch", "none"], 2000,
                                                 p=[0.05, 0.02, 0.93])})  # fmt: skip
    tested = pd.DataFrame({"lot": np.repeat([f"L{i}" for i in range(30)], 25)})
    tested["pred"] = rng.choice(["Center", "Scratch", "none"], len(tested), p=[0.05, 0.02, 0.93])
    tested.loc[tested["lot"] == "L3", "pred"] = "Center"  # one excursion lot
    tests, p_ref = binomial_tests(reference, tested, "pred", patterns)
    for p in patterns:
        assert p_ref[p] == pytest.approx(float((reference["pred"] == p).mean()))
    for row in tests.itertuples():
        expected = sps.binomtest(int(row.count), int(row.wafers), row.expected_rate,
                                 alternative="greater").pvalue  # fmt: skip
        assert row.p_value == pytest.approx(expected, rel=1e-9)
    np.testing.assert_allclose(tests["q_value"], sps.false_discovery_control(tests["p_value"]))
    flagged = tests[tests["flagged"]]
    assert ("L3", "Center") in set(zip(flagged["lot"], flagged["pattern"], strict=True))


def test_reliability_ece_hand_example() -> None:
    """Two equal-width bins hit: confidences 0.6 (2 wafers, 1 correct) and 0.9 (2 wafers,
    both correct). ECE = 0.5 |0.5 - 0.6| + 0.5 |1.0 - 0.9| = 0.1."""
    probs = np.array([[0.6, 0.4], [0.6, 0.4], [0.9, 0.1], [0.1, 0.9]])
    y = np.array([0, 1, 0, 1])
    result = stats.reliability(probs, y, bins=10)
    assert result["ece"] == pytest.approx(0.1, abs=1e-12)
