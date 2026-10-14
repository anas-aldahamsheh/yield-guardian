"""Unit tests of the statistical and preprocessing functions.

Synthetic inputs here are test fixtures for the functions only (WORKERS.md rule 6); no
result reported anywhere is computed from them.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import torch
from scipy.special import softmax
from sklearn.metrics import f1_score

from wm import stats
from wm.lots import join_count
from wm.model import class_balanced_weights, dihedral, focal_loss, random_dihedral
from wm.preprocess import nearest_indices, one_hot, resize_nearest
from wm.splits import build


def test_nearest_resize_never_invents_values() -> None:
    rng = np.random.default_rng(0)
    for h, w in [(6, 3), (25, 27), (64, 64), (300, 205)]:
        grid = rng.integers(0, 3, (h, w), dtype=np.uint8)
        out = resize_nearest(grid)
        assert out.shape == (64, 64)
        assert set(np.unique(out)) <= set(np.unique(grid))


def test_nearest_resize_identity_and_upsampling() -> None:
    grid = np.arange(64 * 64).reshape(64, 64)
    assert np.array_equal(resize_nearest(grid), grid)
    assert nearest_indices(32).tolist() == [i // 2 for i in range(64)]


def test_one_hot_channels() -> None:
    maps = torch.tensor([[[0, 1], [2, 1]]], dtype=torch.uint8)
    x = one_hot(maps)
    assert x.shape == (1, 3, 2, 2)
    assert x[0, 0, 0, 0] == 1 and x[0, 1, 0, 1] == 1 and x[0, 2, 1, 0] == 1
    assert torch.all(x.sum(1) == 1)


def test_dihedral_group_has_eight_distinct_elements() -> None:
    x = torch.arange(16).view(4, 4)
    images = {tuple(dihedral(x, e).flatten().tolist()) for e in range(8)}
    assert len(images) == 8


def test_random_dihedral_matches_reference() -> None:
    g = torch.Generator().manual_seed(1)
    x = torch.randint(0, 3, (32, 8, 8), dtype=torch.uint8)
    y = random_dihedral(x, g)
    e = torch.randint(0, 8, (32,), generator=torch.Generator().manual_seed(1))
    assert all(torch.equal(y[i], dihedral(x[i], int(e[i]))) for i in range(32))


def test_focal_loss_with_gamma_zero_is_weighted_cross_entropy() -> None:
    logits = torch.randn(20, 4)
    target = torch.randint(0, 4, (20,))
    w = torch.tensor([1.0, 2.0, 0.5, 1.5])
    ce = torch.nn.functional.cross_entropy(logits, target, weight=w, reduction="none").mean()
    assert torch.allclose(focal_loss(logits, target, w, gamma=0.0), ce, atol=1e-6)


def test_class_balanced_weights_favour_rare_classes() -> None:
    w = class_balanced_weights(torch.tensor([10000, 100, 10]))
    assert w[0] < w[1] < w[2]
    assert torch.isclose(w.mean(), torch.tensor(1.0))


def test_macro_f1_matches_sklearn() -> None:
    rng = np.random.default_rng(0)
    y = rng.integers(0, 5, 500)
    pred = np.where(rng.random(500) < 0.7, y, rng.integers(0, 5, 500))
    cm = stats.confusion(y, pred, 5)
    assert stats.macro_f1_from_cm(cm) == pytest.approx(f1_score(y, pred, average="macro"))


def test_bootstrap_interval_contains_point_estimate() -> None:
    rng = np.random.default_rng(0)
    lots = np.repeat(np.arange(100), 10)
    x = rng.normal(size=1000) + np.repeat(rng.normal(size=100), 10)
    est = stats.bootstrap(lambda w: float(np.average(x, weights=w)), lots, b=300)
    assert est["ci_low"] < est["value"] < est["ci_high"]
    assert est["lots"] == 100


def test_cluster_bootstrap_is_wider_than_iid_for_correlated_lots() -> None:
    rng = np.random.default_rng(1)
    lot_effect = np.repeat(rng.normal(size=50), 20)
    x = lot_effect + 0.1 * rng.normal(size=1000)
    cluster = stats.bootstrap(
        lambda w: float(np.average(x, weights=w)), np.repeat(np.arange(50), 20), b=300
    )
    iid = stats.bootstrap(lambda w: float(np.average(x, weights=w)), np.arange(1000), b=300)
    assert cluster["ci_high"] - cluster["ci_low"] > 2 * (iid["ci_high"] - iid["ci_low"])


def test_temperature_recovers_known_scale() -> None:
    rng = np.random.default_rng(0)
    true_logits = rng.normal(size=(20000, 4)) * 2
    probs = softmax(true_logits, axis=1)
    y = np.array([rng.choice(4, p=p) for p in probs])
    t = stats.fit_temperature(true_logits * 3.0, y)
    assert t == pytest.approx(3.0, rel=0.08)


def test_ece_is_small_for_calibrated_probabilities() -> None:
    rng = np.random.default_rng(0)
    probs = softmax(rng.normal(size=(50000, 3)) * 2, axis=1)
    y = np.array([rng.choice(3, p=p) for p in probs])
    assert stats.reliability(probs, y)["ece"] < 0.02


def test_join_count_detects_clusters_and_not_checkerboards() -> None:
    rng = np.random.default_rng(0)
    checker = np.ones((20, 20), dtype=np.uint8) + (np.indices((20, 20)).sum(0) % 2).astype(np.uint8)
    res = join_count(checker, rng)
    assert res["bb"] == 0 and res["p"] == 1.0
    block = np.ones((20, 20), dtype=np.uint8)
    block[:6, :6] = 2
    res = join_count(block, rng)
    assert res["bb"] == 2 * 6 * 5 and res["p"] <= 0.002


def test_lot_grouped_splits_never_share_a_lot() -> None:
    rng = np.random.default_rng(0)
    lots = np.repeat([f"lot{i}" for i in range(400)], 5)
    index = pd.DataFrame(
        {
            "row": np.arange(len(lots)),
            "lot": lots,
            "label": rng.choice(["none", "Center", "Loc"], size=len(lots)),
            "official_split": np.where(np.arange(len(lots)) < 1000, "Training", "Test"),
        }
    )
    out = build(index).merge(index, on="row")
    for column in ("split_official", "split_lot"):
        owners = out.groupby("lot")[column].nunique()
        assert (owners == 1).all(), column
