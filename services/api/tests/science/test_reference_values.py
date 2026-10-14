"""Statistics computed in the API against reference implementations (Q1).

The inputs are synthetic test fixtures; nothing reported is computed from them.
"""

import math

import numpy as np
import pytest

from yield_guardian.agent.evaluation import wilson
from yield_guardian.bundles.wafermap import _energy, _softmax, mahalanobis_score

scipy_stats = pytest.importorskip("scipy.stats")
scipy_special = pytest.importorskip("scipy.special")
scipy_distance = pytest.importorskip("scipy.spatial.distance")


@pytest.mark.parametrize(("k", "n"), [(0, 10), (3, 10), (8, 10), (10, 10), (7, 28), (27, 28)])
def test_wilson_matches_scipy(k: int, n: int) -> None:
    reference = scipy_stats.binomtest(k, n).proportion_ci(0.95, method="wilson")
    estimate = wilson(k, n)
    assert estimate.value == pytest.approx(k / n)
    assert estimate.ci_low == pytest.approx(reference.low, abs=1e-12)
    assert estimate.ci_high == pytest.approx(reference.high, abs=1e-12)


def test_energy_and_softmax_match_scipy() -> None:
    logits = np.random.default_rng(41).normal(scale=5.0, size=(50, 9))
    logits[0] = [800.0] + [0.0] * 8  # would overflow a naive exp
    np.testing.assert_allclose(_energy(logits), -scipy_special.logsumexp(logits, axis=1))
    np.testing.assert_allclose(_softmax(logits), scipy_special.softmax(logits, axis=1))


def test_mahalanobis_score_is_the_smallest_squared_distance_to_a_class_mean() -> None:
    rng = np.random.default_rng(42)
    d = 6
    a = rng.normal(size=(d, d))
    covariance = a @ a.T + d * np.eye(d)
    precision = np.linalg.inv(covariance)
    means = rng.normal(scale=3.0, size=(4, d))
    embedding = rng.normal(scale=3.0, size=(30, d)).astype(np.float32)
    scores = mahalanobis_score(embedding, means, precision)
    for row, score in zip(embedding.astype(np.float64), scores, strict=True):
        reference = min(scipy_distance.mahalanobis(row, mu, precision) ** 2 for mu in means)
        assert score == pytest.approx(reference, rel=1e-10)
    assert math.isclose(float(mahalanobis_score(means[:1], means, precision)[0]), 0.0)
