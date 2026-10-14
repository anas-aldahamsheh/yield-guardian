"""Platt scaling of raw model scores.

``p = 1 / (1 + exp(a * z + b))`` with ``z`` the model's raw log-odds, fitted by maximum
likelihood with Platt's smoothed targets ``t+ = (N+ + 1) / (N+ + 2)`` and
``t- = 1 / (N- + 2)``, which keep the fit finite and less overconfident when a sample holds
few events (Platt, 1999, sec. 2.2). Two parameters only: with a negative slope ``a`` the map
is strictly increasing, so ranking metrics (PR-AUC, ROC-AUC) are unchanged by calibration.

Isotonic regression is not used: it is a step function with up to one free level per
distinct score, so with only a few failures in the calibration block it overfits (it
needs far more calibration data to beat a sigmoid; Niculescu-Mizil and Caruana, 2005),
and its flat steps tie units that the model ranks differently, which changes the ranking
the risk is meant to convey.

The fit is Newton's method with a backtracking line search on the convex negative
log-likelihood (Lin, Lin and Weng, 2007), started at ``a = 0`` and the smoothed log prior
odds, stopping when the gradient falls below ``1e-10`` times the sample size.

Platt, J. (1999). Probabilistic outputs for support vector machines and comparisons to
regularized likelihood methods. In Advances in Large Margin Classifiers, MIT Press.
Niculescu-Mizil, A. and Caruana, R. (2005). Predicting good probabilities with supervised
learning. ICML 2005.
Lin, H.-T., Lin, C.-J. and Weng, R. C. (2007). A note on Platt's probabilistic outputs for
support vector machines. Machine Learning, 68, 267-276.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy import special

FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True)
class PlattCalibrator:
    """Fitted Platt scaling ``p = 1 / (1 + exp(a * z + b))``."""

    a: float
    b: float
    n: int
    n_events: int
    converged: bool

    @property
    def increasing(self) -> bool:
        """True when higher raw scores map to higher probabilities (``a < 0``)."""
        return bool(self.a < 0)

    def predict(self, z: npt.ArrayLike) -> FloatArray:
        f = self.a * np.asarray(z, dtype=np.float64) + self.b
        return np.asarray(special.expit(-f), dtype=np.float64)

    def to_contract(self) -> dict[str, float | str]:
        """The ``calibrator.json`` content defined in ARTIFACTS.md."""
        return {"method": "platt", "a": self.a, "b": self.b}

    @classmethod
    def fit(cls, z: npt.ArrayLike, y: npt.ArrayLike) -> PlattCalibrator:
        scores = np.asarray(z, dtype=np.float64)
        labels = np.asarray(y).astype(np.int64)
        if scores.shape != labels.shape or scores.ndim != 1:
            raise ValueError("z and y must be one-dimensional and aligned")
        if not np.all(np.isfinite(scores)):
            raise ValueError("raw scores must be finite")
        n_pos = int(labels.sum())
        n_neg = int(labels.size - n_pos)
        if n_pos == 0 or n_neg == 0:
            raise ValueError("Platt scaling needs both classes")
        target = np.where(labels == 1, (n_pos + 1.0) / (n_pos + 2.0), 1.0 / (n_neg + 2.0))
        a, b, converged = _newton(scores, target, n_pos, n_neg)
        return cls(
            a=float(a),
            b=float(b),
            n=int(labels.size),
            n_events=n_pos,
            converged=bool(converged),
        )


def _loss(scores: FloatArray, target: FloatArray, a: float, b: float) -> float:
    f = a * scores + b
    # -log p = log(1 + e^f); -log(1 - p) = log(1 + e^-f)
    return float(np.sum(target * np.logaddexp(0.0, f) + (1 - target) * np.logaddexp(0.0, -f)))


def _newton(
    scores: FloatArray, target: FloatArray, n_pos: int, n_neg: int, max_iter: int = 100
) -> tuple[float, float, bool]:
    a, b = 0.0, math.log((n_neg + 1.0) / (n_pos + 1.0))
    value = _loss(scores, target, a, b)
    tolerance = 1e-10 * scores.size
    for _ in range(max_iter):
        f = a * scores + b
        q = special.expit(f)  # = 1 - p
        g = q - (1.0 - target)
        grad = np.array([float(np.sum(g * scores)), float(np.sum(g))])
        if np.max(np.abs(grad)) < tolerance:
            return a, b, True
        w = q * (1.0 - q)
        h11 = float(np.sum(w * scores * scores)) + 1e-12
        h22 = float(np.sum(w)) + 1e-12
        h12 = float(np.sum(w * scores))
        det = h11 * h22 - h12 * h12
        da = -(h22 * grad[0] - h12 * grad[1]) / det
        db = -(-h12 * grad[0] + h11 * grad[1]) / det
        slope = grad[0] * da + grad[1] * db
        step = 1.0
        while step >= 1e-10:
            new_a, new_b = a + step * da, b + step * db
            new_value = _loss(scores, target, new_a, new_b)
            if new_value <= value + 1e-4 * step * slope:
                break
            step /= 2.0
        else:
            return a, b, False
        a, b, value = new_a, new_b, new_value
    return a, b, False
