"""False discovery rate control (Benjamini and Hochberg, 1995).

Benjamini, Y. and Hochberg, Y. (1995). Controlling the false discovery rate: a practical
and powerful approach to multiple testing. Journal of the Royal Statistical Society B,
57(1), 289-300.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt


def benjamini_hochberg(p_values: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """Benjamini-Hochberg adjusted p-values (q-values).

    ``q_(i) = min_{j >= i} min(1, p_(j) * m / j)`` for the p-values sorted in ascending
    order, where ``m`` is the number of tested hypotheses. NaN entries mean "not tested":
    they stay NaN and are not counted in ``m``.

    Rejecting every hypothesis with ``q <= alpha`` is the BH step-up procedure at level
    ``alpha`` (the original rule ``p_(i) <= i * alpha / m``).

    Args:
        p_values: One-dimensional p-values in [0, 1]; NaN marks an untested hypothesis.

    Returns:
        Adjusted p-values in the input order.
    """
    p = np.asarray(p_values, dtype=np.float64)
    if p.ndim != 1:
        raise ValueError(f"p_values must be one-dimensional, got shape {p.shape}")
    tested = ~np.isnan(p)
    pv = p[tested]
    if np.any((pv < 0.0) | (pv > 1.0)):
        raise ValueError("p-values must lie in [0, 1]")
    q = np.full(p.shape, np.nan, dtype=np.float64)
    m = pv.size
    if m == 0:
        return q
    order = np.argsort(pv, kind="mergesort")
    scaled = pv[order] * m / np.arange(1, m + 1, dtype=np.float64)
    adjusted = np.minimum(np.minimum.accumulate(scaled[::-1])[::-1], 1.0)
    out = np.empty(m, dtype=np.float64)
    out[order] = adjusted
    q[tested] = out
    return q


def bh_reject(p_values: npt.ArrayLike, alpha: float = 0.05) -> npt.NDArray[np.bool_]:
    """Hypotheses rejected by the BH step-up procedure at FDR level ``alpha``.

    Untested hypotheses (NaN p-values) are never rejected.
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    q = benjamini_hochberg(p_values)
    return np.asarray(np.nan_to_num(q, nan=np.inf) <= alpha, dtype=np.bool_)
