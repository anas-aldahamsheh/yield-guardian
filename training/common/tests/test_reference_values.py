"""Statistics against values known independently of our code (Q1).

- Bootstrap intervals: coverage on simulated data whose true value is known.
- Benjamini-Hochberg: the 15 p-values of Benjamini and Hochberg (1995, section 4), with every
  q-value computed by hand below.
- ECE: the exact value for a known miscalibration, derived analytically.

All inputs are SYNTHETIC test fixtures; no reported result is computed from them.
"""

from __future__ import annotations

import numpy as np
import pytest

from yg_common.bootstrap import bootstrap, cluster_bootstrap, paired_bootstrap
from yg_common.metrics import average_precision, expected_calibration_error
from yg_common.multiple_testing import benjamini_hochberg, bh_reject

# -- bootstrap coverage -----------------------------------------------------------------------

REPS = 200  # coverage of a 95% interval over 200 datasets: binomial sd about 1.5 points


def _mean_of(a: np.ndarray) -> float:
    return float(np.mean(a))


def test_paired_bootstrap_covers_a_known_mean_difference() -> None:
    rng = np.random.default_rng(11)
    covered = 0
    for i in range(REPS):
        shared = rng.normal(size=80)
        a = shared + rng.normal(scale=0.5, size=80) + 0.3
        b = shared + rng.normal(scale=0.5, size=80)
        y = np.ones(80, dtype=np.int64)
        est = paired_bootstrap(
            lambda _y, s: float(np.mean(s.astype(np.float64))),
            y,
            a,
            b,
            stratified=False,
            n_resamples=400,
            seed=i,
        ).difference
        covered += est.ci_low <= 0.3 <= est.ci_high
    assert 0.89 <= covered / REPS <= 0.99


def test_cluster_bootstrap_covers_and_ordinary_bootstrap_does_not_on_clustered_data() -> None:
    """Random-intercept data, true mean 0: resampling clusters keeps the nominal coverage,
    resampling single observations understates the uncertainty."""
    rng = np.random.default_rng(12)
    clusters = np.repeat(np.arange(30), 10)
    cluster_cover = ordinary_cover = 0
    for i in range(REPS):
        x = rng.normal(size=30)[clusters] + rng.normal(size=clusters.size)
        c = cluster_bootstrap(_mean_of, x, clusters=clusters, n_resamples=400, seed=i).estimate
        o = bootstrap(_mean_of, x, n_resamples=400, seed=i).estimate
        cluster_cover += c.ci_low <= 0.0 <= c.ci_high
        ordinary_cover += o.ci_low <= 0.0 <= o.ci_high
    assert 0.87 <= cluster_cover / REPS <= 0.99
    assert ordinary_cover / REPS < 0.8


def test_stratified_bootstrap_of_average_precision_covers_the_population_value() -> None:
    """Binormal scores, prevalence 0.1; the population AP is taken from 2 million draws."""
    rng = np.random.default_rng(13)

    def draw(n: int) -> tuple[np.ndarray, np.ndarray]:
        y = (rng.random(n) < 0.1).astype(np.int64)
        return y, rng.normal(size=n) + 1.2 * y

    truth = average_precision(*draw(2_000_000))
    covered = 0
    for i in range(REPS):
        y, s = draw(600)
        est = bootstrap(average_precision, y, s, strata=y, n_resamples=400, seed=i).estimate
        covered += est.ci_low <= truth <= est.ci_high
    assert 0.85 <= covered / REPS <= 0.99


# -- Benjamini-Hochberg ------------------------------------------------------------------------

BH_1995 = [0.0001, 0.0004, 0.0019, 0.0095, 0.0201, 0.0278, 0.0298, 0.0344, 0.0459,
           0.3240, 0.4262, 0.5719, 0.6528, 0.7590, 1.0000]  # fmt: skip
# q_(i) = min over j >= i of p_(j) * 15 / j, worked by hand from the largest p down:
# 1.0, 0.759*15/14, 0.6528*15/13, 0.5719*15/12, 0.4262*15/11, 0.324*15/10 = 0.486,
# 0.0459*15/9 = 0.0765, 0.0344*15/8 = 0.0645, 0.0298*15/7 = 0.063857..., then
# 0.0278*15/6 = 0.0695 > 0.063857 so q_6 = q_7, 0.0201*3 = 0.0603, 0.0095*15/4 = 0.035625,
# 0.0019*5 = 0.0095, 0.0004*7.5 = 0.003, 0.0001*15 = 0.0015.
BH_1995_Q = [0.0015, 0.003, 0.0095, 0.035625, 0.0603, 0.0298 * 15 / 7, 0.0298 * 15 / 7,
             0.0645, 0.0765, 0.486, 0.4262 * 15 / 11, 0.5719 * 15 / 12, 0.6528 * 15 / 13,
             0.759 * 15 / 14, 1.0]  # fmt: skip


def test_benjamini_hochberg_1995_example_by_hand() -> None:
    np.testing.assert_allclose(benjamini_hochberg(BH_1995), BH_1995_Q, rtol=1e-12)
    rejected = bh_reject(BH_1995, alpha=0.05)
    assert rejected.tolist() == [True] * 4 + [False] * 11  # the paper rejects four
    shuffled = np.random.default_rng(0).permutation(15)
    np.testing.assert_allclose(
        benjamini_hochberg(np.asarray(BH_1995)[shuffled]), np.asarray(BH_1995_Q)[shuffled]
    )


# -- expected calibration error ----------------------------------------------------------------


def test_ece_matches_the_analytic_value_for_a_known_miscalibration() -> None:
    """p uniform on (0, 1), outcomes drawn with probability p**2. With ten equal-count bins
    (deciles [a, b)) the bin's mean prediction is (a + b) / 2 and its event rate
    (a^2 + ab + b^2) / 3, so ECE = sum_b 0.1 |(a + b) / 2 - (a^2 + ab + b^2) / 3|."""
    n = 400_000
    p = (np.arange(n) + 0.5) / n
    y = (np.random.default_rng(14).random(n) < p**2).astype(np.int64)
    edges = np.linspace(0, 1, 11)
    a, b = edges[:-1], edges[1:]
    analytic = float(np.sum(0.1 * np.abs((a + b) / 2 - (a * a + a * b + b * b) / 3)))
    # p > p**2 everywhere, so the sum is E[p - p**2] = 1/2 - 1/3 = 1/6.
    assert analytic == pytest.approx(1 / 6, rel=1e-12)
    assert expected_calibration_error(y, p, 10) == pytest.approx(analytic, abs=0.003)


def test_ece_of_calibrated_predictions_is_near_zero() -> None:
    n = 400_000
    p = (np.arange(n) + 0.5) / n
    y = (np.random.default_rng(15).random(n) < p).astype(np.int64)
    assert expected_calibration_error(y, p, 10) < 0.004
