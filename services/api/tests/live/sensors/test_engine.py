"""The live SECOM engine on real SECOM units: the stage contracts, NeedsInput, the materialiser
and sampler, and the formulas against reference implementations."""

import math
import time
from datetime import timedelta, timezone
from random import Random

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from yield_guardian.bundles.secom import SecomBundle
from yield_guardian.contracts.runs import MIN_UNITS_FOR_DRIFT, SensorUnitInput
from yield_guardian.contracts.services import InvalidArgumentError
from yield_guardian.live.protocols import NeedsInput, SensorEngine
from yield_guardian.live.sensors import (
    SAMPLE_UNITS,
    SecomSensorEngine,
    benjamini_hochberg,
    binomial_upper_tail,
    cusum_chart,
    ewma_chart,
    platt,
    readings_matrix,
    top_indices,
)

scipy_stats = pytest.importorskip("scipy.stats")
scipy_special = pytest.importorskip("scipy.special")


def as_new_data(units: list[SensorUnitInput]) -> list[SensorUnitInput]:
    """The same real readings, as an upload would carry them (no SECOM unit behind them)."""
    return [u.model_copy(update={"source_unit": None, "unit_id": f"up-{u.unit_id}"}) for u in units]


def test_it_is_a_sensor_engine(engine: SecomSensorEngine) -> None:
    checked: SensorEngine = engine
    assert checked is engine


# Materialiser and sampler ---------------------------------------------------------------------


def test_from_secom_gives_real_rows_in_time_order(
    engine: SecomSensorEngine, real_bundle: SecomBundle
) -> None:
    units = engine.from_secom([1500, 3, 1043, 3])
    source = real_bundle.source
    assert [u.source_unit for u in units] == sorted(
        {1500, 3, 1043}, key=lambda u: source.timestamps[u]
    )
    for unit in units:
        assert unit.source_unit is not None
        row = source.readings[unit.source_unit]
        assert unit.unit_id == str(unit.source_unit)
        assert unit.timestamp == source.timestamps[unit.source_unit]
        assert unit.result == ("fail" if source.failed[unit.source_unit] else "pass")
        assert [v is None for v in unit.readings] == np.isnan(row).tolist()
        assert [v for v in unit.readings if v is not None] == row[~np.isnan(row)].tolist()


def test_from_secom_refuses_units_that_do_not_exist(engine: SecomSensorEngine) -> None:
    with pytest.raises(InvalidArgumentError, match="SECOM has units 0 to 1566; 1567"):
        engine.from_secom([0, 1567])
    assert engine.from_secom([]) == []


def test_sample_is_a_seeded_window_of_the_block_the_model_never_saw(
    engine: SecomSensorEngine, real_bundle: SecomBundle
) -> None:
    timeline = real_bundle.timeline
    picked = engine.sample(Random(20261015))
    again = engine.sample(Random(20261015))
    assert [u.source_unit for u in picked.items] == [u.source_unit for u in again.items]
    assert picked.rule == again.rule
    assert len(picked.items) == SAMPLE_UNITS >= MIN_UNITS_FOR_DRIFT
    positions = [int(timeline.sequence_of[u.source_unit or 0]) for u in picked.items]
    assert positions == list(range(positions[0], positions[0] + SAMPLE_UNITS))
    assert {timeline.block[p] for p in positions} == {"test"}
    assert {engine.validity(u) for u in picked.items} == {"held_out"}
    first, last = picked.items[0].timestamp, picked.items[-1].timestamp
    assert first is not None
    assert last is not None
    assert f"{first:%Y-%m-%d %H:%M}" in picked.rule
    assert f"{last:%Y-%m-%d %H:%M}" in picked.rule
    assert "313 units from 2008-10-02 21:32 to 2008-10-17 06:07" in picked.rule
    assert "274 possible windows" in picked.rule
    assert len(picked.rule) <= 600
    starts = {engine.sample(Random(seed)).items[0].source_unit for seed in range(30)}
    assert len(starts) > 20
    # A sample always runs every stage.
    engine.drift_health(picked.items)


def test_unmonitored_sensors_reach_no_model(engine: SecomSensorEngine) -> None:
    unmonitored = engine.unmonitored_sensors()
    used = {f.removesuffix("_missing") for f in engine.model_features} | set(engine.fdc_features)
    assert len(unmonitored) == 590 - len(used) == 122
    assert not set(unmonitored) & used
    assert unmonitored == sorted(unmonitored)
    assert "S006" in unmonitored  # constant in the development period


# Risk ----------------------------------------------------------------------------------------


def test_risk_stage_on_a_real_window(engine: SecomSensorEngine, real_bundle: SecomBundle) -> None:
    units = engine.sample(Random(7)).items
    result = engine.risk(units)
    points = {p.id: p for p in real_bundle.operating_points.points}
    assert result.threshold == points["fpr_0.05"].threshold
    assert result.elevated_threshold == points["fpr_0.10"].threshold
    assert result.operating_point == "5% false-alarm rate on the validation block"
    assert [m.metric for m in result.skill] == ["roc_auc", "pr_auc"]
    main = next(m for m in real_bundle.metrics.models if m.main)
    by_metric = {m.metric: m for m in main.metrics}
    assert result.skill == [by_metric["roc_auc"], by_metric["pr_auc"]]
    assert result.model == real_bundle.bundle.info.bundle
    for i, unit in enumerate(result.units):
        assert (unit.index, unit.unit_id) == (i, units[i].unit_id)
        assert unit.band == (
            "high"
            if unit.risk >= result.threshold
            else "elevated"
            if unit.risk >= result.elevated_threshold
            else "low"
        )
        shaps = [abs(f.shap) for f in unit.top]
        assert shaps == sorted(shaps, reverse=True)
        assert 0 < len(shaps) <= 15
        assert all(f.shap != 0 for f in unit.top)
        readings = units[i].readings
        for feature in unit.top:
            reading = readings[int(feature.sensor[1:]) - 1]
            if feature.indicator:
                assert feature.feature == f"{feature.sensor}_missing"
                assert feature.value == (1.0 if reading is None else 0.0)
            else:
                assert feature.value == reading
        assert unit.raw_score == pytest.approx(
            unit.base_value + sum(f.shap for f in unit.top), abs=1.0
        )


def test_the_ranking_of_used_features_equals_a_full_sort(
    engine: SecomSensorEngine, all_units: list[SensorUnitInput]
) -> None:
    values = readings_matrix(all_units)
    scores = engine.risk_scores(values)
    result = engine.risk(all_units)
    full = np.argsort(-np.abs(scores.shap), axis=1, kind="stable")
    for i, unit in enumerate(result.units):
        expected = [engine.model_features[j] for j in full[i] if scores.shap[i, j] != 0][:15]
        assert [f.feature for f in unit.top] == expected


def test_caution_states_the_measured_skill(
    engine: SecomSensorEngine, real_bundle: SecomBundle
) -> None:
    caution = engine.risk(engine.from_secom([1300])).caution
    roc = next(
        m.estimate
        for model in real_bundle.metrics.models
        if model.main
        for m in model.metrics
        if m.metric == "roc_auc"
    )
    assert f"ROC-AUC {roc.value:.2f}, 95% CI {roc.ci_low:.2f} to {roc.ci_high:.2f}" in caution
    assert "no better than chance" in caution
    assert "caught 1 of 17 test failures" in caution
    assert "313 held-out test units" in caution


def test_new_data_gets_the_same_risk_and_says_so(engine: SecomSensorEngine) -> None:
    real = engine.from_secom(range(1250, 1260))  # validation and test units
    uploaded = as_new_data(real)
    a, b = engine.risk(real), engine.risk(uploaded)
    assert [u.risk for u in a.units] == [u.risk for u in b.units]
    assert [u.top for u in a.units] == [u.top for u in b.units]
    assert {u.validity for u in a.units} == {"in_training", "held_out"}
    assert {u.validity for u in b.units} == {"new_data"}


def test_missing_readings_stay_missing(engine: SecomSensorEngine) -> None:
    unit = engine.from_secom([1400])[0]
    empty = unit.model_copy(update={"readings": [None] * 590, "source_unit": None})
    result = engine.risk([empty])
    item = result.units[0]
    assert 0 <= item.risk <= 1
    assert all(f.value in (None, 1.0) for f in item.top)


# Control charts -------------------------------------------------------------------------------


def test_control_charts_contract(
    engine: SecomSensorEngine, all_units: list[SensorUnitInput]
) -> None:
    units = all_units[:250]
    result = engine.control_charts(units)
    assert [u.index for u in result.units] == list(range(250))
    assert [u.timestamp for u in result.units] == [u.timestamp for u in units]
    shown = [u.z for u in result.units]
    assert all(z is not None and len(z) == len(result.features) for z in shown[:200])
    assert all(z is None for z in shown[200:])
    columns = [int(s[1:]) - 1 for s in result.features]
    for unit, chart in zip(units[:200], result.units[:200], strict=True):
        assert chart.z is not None
        assert [z is None for z in chart.z] == [unit.readings[c] is None for c in columns]
        for items in (chart.top_t2, chart.top_spe):
            assert len(items) == 10
            values = [c.contribution for c in items]
            assert values == sorted(values, reverse=True)
            assert sum(c.share for c in items) <= 1 + 1e-12
    assert {u.level for u in engine.control_charts(all_units).units} == {"none", "warning", "alarm"}


# Drift and health -----------------------------------------------------------------------------


def test_drift_needs_twenty_units(
    engine: SecomSensorEngine, all_units: list[SensorUnitInput]
) -> None:
    with pytest.raises(NeedsInput) as caught:
        engine.drift_health(all_units[: MIN_UNITS_FOR_DRIFT - 1])
    assert caught.value.needs == (
        "Drift and sensor health need at least 20 units in time order; this input has 19."
    )
    engine.drift_health(all_units[:MIN_UNITS_FOR_DRIFT])


def test_drift_needs_every_timestamp(
    engine: SecomSensorEngine, all_units: list[SensorUnitInput]
) -> None:
    units = list(all_units[:30])
    units[4] = units[4].model_copy(update={"timestamp": None})
    with pytest.raises(
        NeedsInput, match=rf"1 of 30 units have none \(the first is unit {units[4].unit_id}\)"
    ):
        engine.drift_health(units)


def test_drift_needs_time_order(
    engine: SecomSensorEngine, all_units: list[SensorUnitInput]
) -> None:
    units = list(all_units[:30])
    units[10], units[20] = units[20], units[10]
    with pytest.raises(NeedsInput) as caught:
        engine.drift_health(units)
    assert "need the units in time order" in caught.value.needs
    assert caught.value.needs.endswith("Sort the file by timestamp and run it again.")
    # Equal timestamps are in order (SECOM has 33 equal neighbours).
    tied = [u.model_copy(update={"timestamp": all_units[0].timestamp}) for u in all_units[:25]]
    engine.drift_health(tied)


def test_risk_and_charts_need_a_unit(engine: SecomSensorEngine) -> None:
    with pytest.raises(NeedsInput, match="at least one sensor unit"):
        engine.risk([])
    with pytest.raises(NeedsInput, match="at least one sensor unit"):
        engine.control_charts([])


def test_drift_on_a_window_starts_from_zero(
    engine: SecomSensorEngine, all_units: list[SensorUnitInput]
) -> None:
    window = all_units[600:660]
    result = engine.drift_health(window)
    assert len(result.groups) == 5
    for group in result.groups:
        assert len(group.ewma) == len(group.cusum_upper) == len(group.cusum_lower) == 60
        assert group.first_ewma_alarm is None or abs(group.ewma[group.first_ewma_alarm]) > (
            group.ewma_limit
        )
    assert sum(result.health_counts.values()) == 590
    assert all(h.status != "ok" and h.reasons for h in result.health)
    assert "calendar week" in result.method


def test_new_data_is_judged_after_the_reference(
    engine: SecomSensorEngine, all_units: list[SensorUnitInput]
) -> None:
    """Real reference units marked as SECOM rows are part of the reference; the same readings
    as an upload are new data, so every reading counts as after the reference."""
    window = all_units[:120]
    real = {h.sensor: h for h in engine.drift_health(window).health}
    uploaded = {h.sensor: h for h in engine.drift_health(as_new_data(window)).health}
    assert real != uploaded
    assert any("after the reference" in r for h in uploaded.values() for r in h.reasons)


def test_health_uses_the_inputs_own_weeks(
    engine: SecomSensorEngine, all_units: list[SensorUnitInput]
) -> None:
    window = all_units[1000:1100]
    values = readings_matrix(window)
    stamps = [u.timestamp for u in window if u.timestamp is not None]
    windows, details = engine.health(values, stamps, np.zeros(100, dtype=bool))
    assert windows[0].start.weekday() == 0
    assert sorted(i for w in windows for i in w.units) == list(range(100))
    assert all(len(d.missing_by_window) == len(windows) for d in details)
    # The same week starts whatever zone the stamps are written in.
    shifted = [s.astimezone(timezone(timedelta(hours=3))) for s in stamps]
    again, _ = engine.health(values, shifted, np.zeros(100, dtype=bool))
    assert [w.start for w in again] == [w.start for w in windows]


# Formulas -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("k", "m", "p"),
    [(0, 10, 0.1), (1, 1448, 0.001), (8, 1448, 0.001), (3, 40, 0.001), (40, 40, 0.5), (2, 1, 0.3)],
)
def test_binomial_tail_matches_scipy(k: int, m: int, p: float) -> None:
    expected = float(scipy_stats.binom.sf(k - 1, m, p))
    assert binomial_upper_tail(k, m, p) == pytest.approx(expected, rel=1e-10, abs=1e-300)


@given(st.lists(st.floats(0, 1), min_size=1, max_size=60))
def test_benjamini_hochberg_matches_scipy(p: list[float]) -> None:
    ours = benjamini_hochberg(np.array(p))
    np.testing.assert_allclose(ours, scipy_stats.false_discovery_control(p), rtol=1e-12)


def test_platt_matches_scipy_expit() -> None:
    raw = np.linspace(-800, 800, 4001)
    np.testing.assert_allclose(platt(raw, -0.83, 2.55), scipy_special.expit(-(-0.83 * raw + 2.55)))


def test_charts_restart_cusum_after_a_signal() -> None:
    u = np.r_[np.zeros(5), np.full(10, 3.0), np.zeros(5)]
    upper, lower, alarm = cusum_chart(u, 0.5, 5.0)
    assert alarm.tolist().index(True) == 7  # 2.5 per unit after the shift: 7.5 > 5 at the 3rd
    assert upper[8] == pytest.approx(2.5)  # restarted at zero
    assert not lower.any()
    ewma, limit, flags = ewma_chart(u, 0.2, 2.962)
    assert limit == pytest.approx(2.962 * math.sqrt(0.2 / 1.8))
    assert ewma[5] == pytest.approx(0.6)
    assert flags[6]


@settings(max_examples=200)
@given(
    st.integers(1, 30).flatmap(
        lambda p: st.tuples(
            st.lists(st.lists(st.integers(-3, 3), min_size=p, max_size=p), min_size=1, max_size=8),
            st.integers(0, p + 1),
        )
    )
)
def test_top_indices_equal_a_stable_full_sort(case: tuple[list[list[int]], int]) -> None:
    rows, k = case
    values = np.array(rows, dtype=np.float64)  # small integers: many ties
    expected = np.argsort(-values, axis=1, kind="stable")[:, :k]
    assert np.array_equal(top_indices(values, k), expected)


def test_five_thousand_units_run(
    engine: SecomSensorEngine, all_units: list[SensorUnitInput]
) -> None:
    """The size guard's largest input runs (timing is measured and reported, not asserted)."""
    units = (all_units * 4)[:5000]
    started = time.perf_counter()
    risk = engine.risk(units)
    charts = engine.control_charts(units)
    elapsed = time.perf_counter() - started
    assert len(risk.units) == len(charts.units) == 5000
    assert elapsed > 0
