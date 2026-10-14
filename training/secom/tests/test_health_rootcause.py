"""Sensor-health rules and root-cause mechanics (SYNTHETIC inputs)."""

from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest

from yg_secom.health import HealthRules, analyse_health
from yg_secom.rootcause import (
    assemble_shap,
    correlated_groups,
    group_importance,
    permutation_p_values,
    sensor_shap,
    top_k_mask,
)

RULES = HealthRules(
    min_readings=5,
    flatline_probability=1e-3,
    stuck_alpha=0.01,
    jump_reference_share=0.01,
    jump_fdr_q=0.05,
    watch_out_of_reference=0.05,
    maintenance_out_of_reference=0.2,
    watch_window_missing=0.2,
    maintenance_window_missing=0.5,
    normal_missing=0.1,
)


def _health_inputs(n: int = 600, seed: int = 0) -> tuple[pd.DataFrame, pd.Series, np.ndarray]:
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(rng.normal(size=(n, 6)), columns=[f"S{i:03d}" for i in range(1, 7)])
    X["S002"] = np.nan  # never measured: dead
    X["S003"] = 4.0  # constant: dead
    X.loc[400:450, "S004"] = 1.234  # stuck at a value never seen in the reference
    spikes = rng.random(n) < 0.15
    spikes[:200] = False  # spiky only after the reference
    X.loc[spikes, "S005"] += rng.choice([-25.0, 25.0], size=int(spikes.sum()))
    ts = pd.Series(pd.date_range("2008-07-19", periods=n, freq="45min", tz="UTC"))
    y = (rng.random(n) < 0.1).astype(np.int8)
    return X, ts, y


def test_statuses_reasons_and_jump_calibration() -> None:
    X, ts, y = _health_inputs()
    order = np.arange(len(X), dtype=np.int64)
    doc, summary = analyse_health(
        X,
        ts,
        y,
        order,
        label_ids=order[:450],
        reference_ids=order[:100],
        held_out_ids=order[100:200],
        rules=RULES,
        fdr_q=0.05,
    )
    status = {s["sensor"]: s for s in doc["sensors"]}
    assert status["S002"]["status"] == "dead"
    assert status["S003"]["status"] == "dead"
    assert status["S004"]["status"] == "maintenance"
    assert status["S004"]["stuck_value"] == pytest.approx(1.234)
    assert status["S005"]["status"] == "watch"
    assert any("jumps" in r for r in status["S005"]["reasons"])
    for s in doc["sensors"]:
        assert (s["status"] == "ok") == (not s["reasons"])
    jump = summary["rules"]["jump"]
    assert jump["reference_share_flagged"] <= RULES.jump_reference_share
    assert jump["threshold_z"] > 0
    assert doc["rules"] == summary["rules"]["status"]
    assert len(doc["rules"]) == 4
    assert summary["status_counts"]["dead"] == 2
    assert sum(summary["status_counts"].values()) == 6
    assert [w["window_id"] for w in doc["windows"]] == list(range(len(doc["windows"])))


def test_stuck_rule_uses_the_reference_repeat_rate_and_counts_shared_runs() -> None:
    X, ts, y = _health_inputs()
    rng = np.random.default_rng(7)
    lots = np.repeat(rng.normal(size=len(X) // 5), 5)  # one reading per lot of 5 units
    X["S006"] = lots
    X["S001"] = lots + 1.0  # same lot structure: runs over exactly the same units
    order = np.arange(len(X), dtype=np.int64)
    doc, summary = analyse_health(
        X,
        ts,
        y,
        order,
        label_ids=order[:450],
        reference_ids=order[:100],
        held_out_ids=order[100:200],
        rules=RULES,
        fdr_q=0.05,
    )
    status = {s["sensor"]: s for s in doc["sensors"]}
    for sensor in ("S001", "S006"):
        assert not any("stuck" in r for r in status[sensor]["reasons"])
    assert any("stuck" in r for r in status["S004"]["reasons"])  # 51 repeats: still flagged
    runs = summary["identical_runs"]
    assert runs["largest_number_of_sensors_sharing_one_span"] == 2
    assert runs["runs_sharing_their_unit_span_with_another_sensor"] == 2 * (len(X) // 5)


def test_missingness_test_uses_only_the_given_label_rows() -> None:
    X, ts, y = _health_inputs(seed=1)
    order = np.arange(len(X), dtype=np.int64)
    y_masked = y.copy()
    y_masked[450:] = -1  # masked labels outside label_ids must never matter
    first, _ = analyse_health(
        X, ts, y, order, order[:450], order[:100], order[100:200], RULES, 0.05
    )
    second, _ = analyse_health(
        X, ts, y_masked, order, order[:450], order[:100], order[100:200], RULES, 0.05
    )
    assert first == second


def test_assembled_shap_rows_add_up_to_raw_scores() -> None:
    rng = np.random.default_rng(0)
    X = pd.DataFrame(rng.normal(size=(200, 4)), columns=["S001", "S002", "S003", "S003_missing"])
    y = (X["S001"] + rng.normal(size=200) > 1).astype(int)
    booster = lgb.train(
        {"objective": "binary", "verbosity": -1, "num_leaves": 4, "seed": 1},
        lgb.Dataset(X.to_numpy(), label=y, feature_name=list(X.columns)),
        20,
    )
    small = X[["S001", "S002"]]
    booster_small = lgb.train(
        {"objective": "binary", "verbosity": -1, "num_leaves": 4},
        lgb.Dataset(small.to_numpy(), label=y, feature_name=list(small.columns)),
        20,
    )
    full = np.asarray(booster.predict(X.to_numpy()[:5], pred_contrib=True), dtype=np.float64)
    part = np.asarray(
        booster_small.predict(small.to_numpy()[5:9], pred_contrib=True), dtype=np.float64
    )
    values, base = assemble_shap(
        12,
        list(X.columns),
        [
            (np.arange(5), full[:, :-1], list(X.columns), full[:, -1]),
            (np.arange(5, 9), part[:, :-1], list(small.columns), part[:, -1]),
        ],
    )
    raw_full = np.asarray(booster.predict(X.to_numpy()[:5], raw_score=True), dtype=np.float64)
    raw_part = np.asarray(
        booster_small.predict(small.to_numpy()[5:9], raw_score=True), dtype=np.float64
    )
    np.testing.assert_allclose(values[:5].sum(axis=1) + base[:5], raw_full, rtol=1e-5)
    np.testing.assert_allclose(values[5:9].sum(axis=1) + base[5:9], raw_part, rtol=1e-5)
    assert np.all(values[5:9, 2:] == 0)
    assert np.isnan(values[9:]).all()
    assert np.isnan(base[9:]).all()
    with pytest.raises(ValueError, match="two models"):
        assemble_shap(
            12, list(X.columns), [(np.arange(2), full[:2, :-1], list(X.columns), full[:2, -1])] * 2
        )


def test_sensor_shap_merges_indicators_and_groups_sum() -> None:
    values = np.array([[1.0, -2.0, 0.5], [0.0, 1.0, -1.0]])
    merged = sensor_shap(values, ["S001", "S002", "S001_missing"], ["S001", "S002"])
    np.testing.assert_allclose(merged, [[1.5, -2.0], [-1.0, 1.0]])
    importance = group_importance(np.array([0.2, 0.3, 0.5]), np.array([0, 0, 1]), 2)
    np.testing.assert_allclose(importance, [0.5, 0.5])
    assert top_k_mask(np.array([0.1, 0.0, 0.3]), 2).tolist() == [True, False, True]


def test_permutation_p_values_follow_phipson_smyth() -> None:
    observed = np.array([1.0, 0.0])
    null = np.array([[0.5, 0.0], [2.0, 0.0], [0.1, 0.1]])
    np.testing.assert_allclose(permutation_p_values(observed, null), [2 / 4, 4 / 4])


def test_correlated_groups_join_near_duplicates_only() -> None:
    rng = np.random.default_rng(0)
    base = rng.normal(size=300)
    X = pd.DataFrame(
        {
            "S001": base,
            "S002": base + 0.05 * rng.normal(size=300),
            "S003": rng.normal(size=300),
            "S004": -base,
        }
    )
    grouping = correlated_groups(X, ["S001", "S002", "S003", "S004"], 0.8, 30)
    m = grouping.membership
    assert m[0] == m[1] == m[3]
    assert m[2] != m[0]
    assert grouping.n_groups == 2
