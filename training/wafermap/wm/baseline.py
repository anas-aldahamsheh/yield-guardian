"""Baseline: multinomial logistic regression on hand-made radial and density features.

Features are computed from the same 64x64 nearest-neighbour maps the CNN sees, so the
comparison isolates the model, not the input.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

RINGS = 8
SECTORS = 8
EIGHT = np.ones((3, 3), dtype=int)
FEATURE_NAMES = (
    ["fail_fraction", "die_fraction"]
    + [f"ring{i}_fail_density" for i in range(RINGS)]
    + [f"sector{i}_fail_density" for i in range(SECTORS)]
    + [
        "sector_density_std",
        "sector_density_range",
        "components",
        "largest_component_share",
        "largest_component_radius",
        "largest_component_elongation",
        "largest_component_dies",
        "edge_minus_centre_density",
    ]
)


def features(grid: np.ndarray) -> np.ndarray:
    die = grid > 0
    fail = grid == 2
    rr, cc = np.nonzero(die)
    n_die = max(len(rr), 1)
    n_fail = int(fail.sum())
    cy, cx = (rr.mean(), cc.mean()) if len(rr) else (31.5, 31.5)
    yy, xx = np.indices(grid.shape)
    radius = np.hypot(yy - cy, xx - cx)
    rmax = radius[die].max() if len(rr) else 1.0
    r = radius / max(rmax, 1e-6)
    theta = (np.arctan2(yy - cy, xx - cx) + np.pi) / (2 * np.pi)

    def density(mask: np.ndarray) -> float:
        d = (mask & die).sum()
        return float((mask & fail).sum() / d) if d else 0.0

    ring = np.minimum((r * RINGS).astype(int), RINGS - 1)
    sector = np.minimum((theta * SECTORS).astype(int), SECTORS - 1)
    rings = [density(ring == i) for i in range(RINGS)]
    sectors = [density(sector == i) for i in range(SECTORS)]

    labels, count = ndimage.label(fail, structure=EIGHT)
    if count:
        sizes = np.bincount(labels.ravel())[1:]
        big = int(sizes.argmax()) + 1
        py, px = np.nonzero(labels == big)
        comp_r = float(np.hypot(py.mean() - cy, px.mean() - cx) / max(rmax, 1e-6))
        if len(py) > 2:
            eig = np.sort(np.linalg.eigvalsh(np.cov(np.vstack([py, px]))))
            elong = float(np.sqrt((eig[1] + 1e-3) / (eig[0] + 1e-3)))
        else:
            elong = 1.0
        share = float(sizes.max() / n_fail)
        big_dies = float(sizes.max() / n_die)
    else:
        comp_r, elong, share, big_dies = 0.0, 1.0, 0.0, 0.0
    return np.array(
        [n_fail / n_die, n_die / grid.size, *rings, *sectors]  # noqa: RUF005
        + [
            float(np.std(sectors)),
            float(np.ptp(sectors)),
            float(count),
            share,
            comp_r,
            elong,
            big_dies,
            density(r >= 0.8) - density(r < 0.5),
        ],
        dtype=np.float32,
    )


def feature_matrix(maps: np.ndarray) -> np.ndarray:
    return np.stack([features(m) for m in maps])


def fit(
    x_train: np.ndarray, y_train: np.ndarray, x_val: np.ndarray, y_val: np.ndarray, k: int
) -> tuple[object, dict]:
    """Choose C on validation macro-F1 only."""
    scores = {}
    best = None
    for c in (0.01, 0.1, 1.0, 10.0):
        model = make_pipeline(
            StandardScaler(),
            LogisticRegression(C=c, class_weight="balanced", max_iter=3000),
        )
        model.fit(x_train, y_train)
        score = f1_score(y_val, model.predict(x_val), average="macro", labels=list(range(k)))
        scores[str(c)] = float(score)
        if best is None or score > best[0]:
            best = (score, c, model)
    assert best is not None
    return best[2], {"C_grid_val_macro_f1": scores, "chosen_C": best[1]}
