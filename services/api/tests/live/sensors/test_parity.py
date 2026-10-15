"""Parity: the live SECOM engine reproduces the bundle's stored results (PLAN_V2 §3.2).

The engine computes from the readings alone; timeline.parquet, shap.npz, fdc.npz and
health.json are read here only as the reference. Stored values are float32, so live float64
values are compared within float32 precision (relative 1e-6).
"""

import json
from typing import Any

import numpy as np
import pytest

from yield_guardian.bundles.secom import SecomBundle
from yield_guardian.contracts.runs import (
    ControlChartsResult,
    DriftHealthResult,
    SensorRiskResult,
    SensorUnitInput,
)
from yield_guardian.live.sensors import SecomSensorEngine, readings_matrix

RTOL = 1e-6  # float32 keeps about 7 significant digits


@pytest.fixture(scope="module")
def values(all_units: list[SensorUnitInput]) -> np.ndarray:
    return readings_matrix(all_units)


@pytest.fixture(scope="module")
def charts(engine: SecomSensorEngine, all_units: list[SensorUnitInput]) -> ControlChartsResult:
    return engine.control_charts(all_units)


@pytest.fixture(scope="module")
def risk(engine: SecomSensorEngine, all_units: list[SensorUnitInput]) -> SensorRiskResult:
    return engine.risk(all_units)


@pytest.fixture(scope="module")
def drift(engine: SecomSensorEngine, all_units: list[SensorUnitInput]) -> DriftHealthResult:
    return engine.drift_health(all_units)


@pytest.fixture(scope="module")
def metrics(real_bundle: SecomBundle) -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(real_bundle.bundle.file("metrics.json").read_text())
    return raw


def test_inputs_are_every_secom_unit_in_the_timeline_order(
    all_units: list[SensorUnitInput], real_bundle: SecomBundle
) -> None:
    timeline = real_bundle.timeline
    assert [u.source_unit for u in all_units] == timeline.unit_id.tolist()
    assert [u.timestamp for u in all_units] == timeline.timestamp
    assert [u.result == "fail" for u in all_units] == timeline.failed.tolist()


# Control charts ------------------------------------------------------------------------------


def test_t2_and_spe_equal_the_timeline_for_every_unit(
    charts: ControlChartsResult, real_bundle: SecomBundle
) -> None:
    timeline = real_bundle.timeline
    t2 = np.array([u.t2 for u in charts.units])
    spe = np.array([u.spe for u in charts.units])
    assert len(charts.units) == len(timeline) == 1567
    np.testing.assert_allclose(t2, timeline.t2, rtol=RTOL, atol=0)
    np.testing.assert_allclose(spe, timeline.spe, rtol=RTOL, atol=0)
    # Rounded as the bundle stores them, they are the same numbers.
    assert np.array_equal(t2.astype(np.float32), timeline.t2.astype(np.float32))
    assert np.array_equal(spe.astype(np.float32), timeline.spe.astype(np.float32))
    assert [u.level for u in charts.units] == timeline.fdc_alarm


def test_limits_and_model_size_are_the_bundles(
    charts: ControlChartsResult, real_bundle: SecomBundle
) -> None:
    timeline = real_bundle.timeline
    limits = charts.limits
    for live, stored in (
        (limits.t2_99, timeline.t2_limit_99),
        (limits.t2_999, timeline.t2_limit_999),
        (limits.spe_99, timeline.spe_limit_99),
        (limits.spe_999, timeline.spe_limit_999),
    ):
        np.testing.assert_allclose(live, stored, rtol=RTOL)
    assert charts.n_components == real_bundle.fdc.n_components == 56
    assert charts.features == real_bundle.fdc.features
    assert charts.explained_variance == real_bundle.fdc_explained_variance


def test_contributions_equal_fdc_npz_for_every_unit(
    engine: SecomSensorEngine, values: np.ndarray, real_bundle: SecomBundle
) -> None:
    scores = engine.fdc_scores(values)
    by_unit = real_bundle.timeline.unit_id  # row i of `values` is this SECOM unit
    stored_t2 = real_bundle.fdc.contrib_t2[by_unit].astype(np.float64)
    stored_spe = real_bundle.fdc.contrib_spe[by_unit].astype(np.float64)
    np.testing.assert_allclose(scores.contrib_t2, stored_t2, rtol=RTOL, atol=1e-6)
    np.testing.assert_allclose(scores.contrib_spe, stored_spe, rtol=RTOL, atol=1e-6)
    # Each decomposition sums to its statistic.
    np.testing.assert_allclose(scores.contrib_t2.sum(axis=1), scores.t2, rtol=1e-9)
    np.testing.assert_allclose(scores.contrib_spe.sum(axis=1), scores.spe, rtol=1e-9)


def test_listed_contributions_are_the_largest_with_their_shares(
    charts: ControlChartsResult, engine: SecomSensorEngine, values: np.ndarray
) -> None:
    scores = engine.fdc_scores(values)
    index = {s: j for j, s in enumerate(charts.features)}
    for i, unit in enumerate(charts.units):
        for items, matrix in ((unit.top_t2, scores.contrib_t2), (unit.top_spe, scores.contrib_spe)):
            row = matrix[i]
            expected = np.argsort(-row, kind="stable")[:10]
            assert [index[c.sensor] for c in items] == expected.tolist()
            positive = np.clip(row, 0, None)
            for c in items:
                assert c.contribution == pytest.approx(row[index[c.sensor]], rel=1e-12)
                assert c.share == pytest.approx(positive[index[c.sensor]] / positive.sum())


# Risk and SHAP -------------------------------------------------------------------------------


def _by_source(real_bundle: SecomBundle) -> dict[str | None, np.ndarray]:
    sources = np.array(real_bundle.timeline.risk_source, dtype=object)
    return {s: np.flatnonzero(sources == s) for s in (None, "oof", "test")}


def test_risk_equals_the_timeline_where_the_deployed_model_scored_it(
    risk: SensorRiskResult, real_bundle: SecomBundle
) -> None:
    """The stored risk of the 313 test-block units came from the deployed model (step 11 of
    yg_secom.pipeline); live risk, band and threshold flag equal it for every one of them."""
    timeline = real_bundle.timeline
    test = _by_source(real_bundle)["test"]
    assert test.size == 313
    live = np.array([risk.units[s].risk for s in test])
    np.testing.assert_allclose(live, timeline.risk[test], rtol=RTOL, atol=1e-9)
    assert np.array_equal(live.astype(np.float32), timeline.risk[test].astype(np.float32))
    assert [risk.units[s].band for s in test] == [timeline.risk_band[s] for s in test]
    threshold = next(
        p.threshold
        for p in real_bundle.operating_points.points
        if p.id == real_bundle.operating_points.default
    )
    assert risk.threshold == threshold
    assert [risk.units[s].above_threshold for s in test] == [
        bool(timeline.risk[s] >= threshold) for s in test
    ]
    assert {risk.units[s].validity for s in test} == {"held_out"}


def test_shap_equals_shap_npz_where_the_deployed_model_explained_it(
    engine: SecomSensorEngine,
    values: np.ndarray,
    risk: SensorRiskResult,
    real_bundle: SecomBundle,
) -> None:
    shap = real_bundle.shap
    test = _by_source(real_bundle)["test"]
    units = real_bundle.timeline.unit_id[test]
    scores = engine.risk_scores(values[test])
    columns = [shap.features.index(f) for f in engine.model_features]
    stored = shap.values[units][:, columns].astype(np.float64)
    np.testing.assert_allclose(scores.shap, stored, rtol=RTOL, atol=1e-7)
    np.testing.assert_allclose(scores.base, shap.base_values[units], rtol=RTOL)
    # Features only the fold models had are exactly zero for test units.
    others = [j for j in range(len(shap.features)) if j not in set(columns)]
    assert np.all(shap.values[units][:, others] == 0)
    # TreeSHAP is exact: base value plus contributions is the raw score.
    np.testing.assert_allclose(scores.base + scores.shap.sum(axis=1), scores.raw, atol=1e-12)
    # What the stage lists is the largest |SHAP| of the stored explanation.
    for position, unit in zip(test.tolist(), units.tolist(), strict=True):
        item = risk.units[position]
        row = shap.values[unit][columns].astype(np.float64)
        for feature in item.top:
            assert feature.shap == pytest.approx(
                row[engine.model_features.index(feature.feature)], rel=RTOL, abs=1e-7
            )
        assert len(item.top) == min(15, int(np.count_nonzero(row)))


def test_out_of_fold_units_legitimately_differ(
    risk: SensorRiskResult, real_bundle: SecomBundle
) -> None:
    """The 878 validation units' stored risks and SHAP are out-of-fold: each came from the
    rolling-origin fold model whose slice held it, not from the deployed model (which was then
    refitted on them). Live risk uses the deployed model, so it differs there, and says the
    unit is in-sample; the 376 warm-up units have no stored risk at all."""
    timeline = real_bundle.timeline
    groups = _by_source(real_bundle)
    oof, warm = groups["oof"], groups[None]
    assert (oof.size, warm.size) == (878, 376)
    assert {timeline.block[s] for s in oof} == {"validation"}
    assert {timeline.block[s] for s in warm} == {"train"}
    live = np.array([risk.units[s].risk for s in oof])
    assert np.max(np.abs(live - timeline.risk[oof])) > 0.05
    # Fold models have their own expected values; the deployed model has one for every unit.
    units = timeline.unit_id
    stored_base = real_bundle.shap.base_values[units[oof]].astype(np.float64)
    live_base = np.array([risk.units[s].base_value for s in oof])
    assert np.all(np.abs(stored_base - live_base) > 1e-4)
    assert np.unique(stored_base).size == 5  # one per rolling-origin fold
    assert np.isnan(timeline.risk[warm]).all()
    assert np.isnan(real_bundle.shap.values[units[warm]]).all()
    assert {risk.units[s].validity for s in np.r_[oof, warm]} == {"in_training"}


# Drift ----------------------------------------------------------------------------------------


def test_ewma_and_cusum_alarms_equal_the_timeline(
    drift: DriftHealthResult, real_bundle: SecomBundle, metrics: dict[str, Any]
) -> None:
    timeline = real_bundle.timeline
    ewma = np.zeros(len(timeline), dtype=bool)
    cusum = np.zeros(len(timeline), dtype=bool)
    recorded = metrics["fdc"]["small_shift_charts"]["leading_groups"]
    assert [g.group_id for g in drift.groups] == [r["group_id"] for r in recorded]
    for group, record in zip(drift.groups, recorded, strict=True):
        assert group.sensors == record["members_used"]
        flags = np.abs(np.array(group.ewma)) > group.ewma_limit
        signals = (np.array(group.cusum_upper) > group.cusum_h) | (
            np.array(group.cusum_lower) > group.cusum_h
        )
        assert group.ewma_limit == pytest.approx(record["ewma_limit"], rel=1e-12)
        assert (int(flags.sum()), int(signals.sum())) == (
            record["ewma_alarms"],
            record["cusum_alarms"],
        )
        assert group.first_ewma_alarm == int(np.flatnonzero(flags)[0])
        ewma |= flags
        cusum |= signals
    assert np.array_equal(ewma, timeline.ewma_alarm)
    assert np.array_equal(cusum, timeline.cusum_alarm)
    assert (int(ewma.sum()), int(cusum.sum())) == (1010, 207)


def test_chart_parameters_are_the_training_configuration(
    drift: DriftHealthResult, metrics: dict[str, Any]
) -> None:
    config = metrics["run"]["config"]
    assert (drift.ewma_lambda, drift.ewma_width, drift.cusum_k) == (0.2, 2.962, 0.5)
    assert (config["ewma_lambda"], config["ewma_l"], config["cusum_k"], config["cusum_h"]) == (
        0.2,
        2.962,
        0.5,
        5.0,
    )
    assert {g.cusum_h for g in drift.groups} == {5.0}


# Health ---------------------------------------------------------------------------------------


def test_health_statuses_and_reasons_equal_health_json(
    drift: DriftHealthResult, real_bundle: SecomBundle
) -> None:
    stored = real_bundle.health.sensors
    listed = {h.sensor: h for h in drift.health}
    assert len(stored) == 590
    for record in stored:
        if record.status == "ok":
            assert record.sensor not in listed
        else:
            assert (listed[record.sensor].status, listed[record.sensor].reasons) == (
                record.status,
                record.reasons,
            )
    assert len(listed) == sum(r.status != "ok" for r in stored)
    assert drift.health_counts == {"ok": 274, "watch": 143, "maintenance": 57, "dead": 116}
    assert drift.rules == real_bundle.health.rules


def test_every_health_field_equals_health_json(
    engine: SecomSensorEngine,
    values: np.ndarray,
    all_units: list[SensorUnitInput],
    real_bundle: SecomBundle,
) -> None:
    stamps = [u.timestamp for u in all_units if u.timestamp is not None]
    is_reference = np.array([u.source_unit in engine.reference_units for u in all_units])
    windows, details = engine.health(values, stamps, is_reference)
    unit_of = [u.source_unit for u in all_units]
    assert len(windows) == len(real_bundle.health.windows) == 14
    for window, stored in zip(windows, real_bundle.health.windows, strict=True):
        assert window.start == stored.start.date()
        assert [unit_of[i] for i in window.units] == stored.unit_ids
    for live, record in zip(details, real_bundle.health.sensors, strict=True):
        assert live.sensor == record.sensor
        assert live.missing_rate == record.missing_rate
        assert live.missing_by_window == record.missing_by_window
        assert live.flatline_windows == record.flatline_windows
        assert live.stuck_value == record.stuck_value
        assert [unit_of[i] for i in live.jump_units] == record.jump_unit_ids
        assert live.out_of_reference_rate == record.out_of_reference_rate
