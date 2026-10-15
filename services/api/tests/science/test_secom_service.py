"""SecomService on a bundle: visibility, risk, explanations, FDC, groups, health and series."""

import numpy as np
import pytest

from yield_guardian.bundles.secom import SecomBundle
from yield_guardian.contracts.services import InvalidArgumentError, NotFoundError
from yield_guardian.science.secom.service import SecomInference


def unit_at(bundle: SecomBundle, sequence: int) -> int:
    return int(bundle.timeline.unit_id[sequence])


async def test_every_unit_is_visible_without_a_clock(
    secom: SecomInference, secom_bundle: SecomBundle
) -> None:
    with pytest.raises(NotFoundError, match="does not exist"):
        await secom.get_unit(1567)
    detail = await secom.get_unit(unit_at(secom_bundle, 1566))
    assert detail.sequence == 1566
    assert detail.sensors_measured + detail.sensors_missing == 590
    assert detail.final_test == ("fail" if secom_bundle.timeline.failed[1566] else "pass")


async def test_measured_counts_come_from_the_source_file(
    secom: SecomInference, secom_bundle: SecomBundle
) -> None:
    unit = unit_at(secom_bundle, 500)
    detail = await secom.get_unit(unit)
    assert detail.sensors_measured == int(np.isfinite(secom_bundle.source.readings[unit]).sum())


async def test_unit_pages_are_in_time_order_and_complete(secom: SecomInference) -> None:
    seen: list[int] = []
    cursor = None
    while True:
        page = await secom.list_units(limit=300, cursor=cursor)
        seen += [u.sequence for u in page.items]
        cursor = page.next_cursor
        if cursor is None:
            break
    assert seen == list(range(1567))
    assert page.total == 1567
    high = await secom.list_units(band="high", limit=2000)
    assert all(u.risk_band == "high" for u in high.items)
    window = await secom.list_units(from_seq=10, to_seq=5000, limit=2000)
    assert [u.sequence for u in window.items] == list(range(10, 1567))
    with pytest.raises(InvalidArgumentError):
        await secom.list_units(from_seq=10, to_seq=5)


async def test_risk_notes_explain_the_source(
    secom: SecomInference, secom_bundle: SecomBundle
) -> None:
    warm = await secom.get_risk(unit_at(secom_bundle, 3))
    assert warm.risk is None
    assert warm.above_threshold is None
    assert warm.note is not None
    assert "warm-up" in warm.note
    later = await secom.get_risk(unit_at(secom_bundle, 1000))
    assert later.risk is not None
    assert later.above_threshold == (later.risk >= later.operating_point.threshold)


async def test_an_explanation_adds_up_to_the_raw_score(
    secom: SecomInference, secom_bundle: SecomBundle
) -> None:
    unit = unit_at(secom_bundle, 700)
    explanation = await secom.get_explanation(unit, top_k=5)
    values = secom_bundle.shap.values[unit].astype(np.float64)
    shown = sum(c.shap for c in explanation.contributions)
    assert len(explanation.contributions) == 5
    assert explanation.other_features == len(values) - 5
    assert shown + explanation.other_shap == pytest.approx(values.sum(), abs=1e-6)
    assert explanation.raw_score == pytest.approx(explanation.base_value + values.sum(), abs=1e-6)
    magnitudes = [abs(c.shap) for c in explanation.contributions]
    assert magnitudes == sorted(magnitudes, reverse=True)
    indicator = [c for c in explanation.contributions if c.kind == "missing_indicator"]
    assert all(c.value in (0.0, 1.0) for c in indicator)


async def test_warm_up_units_have_no_explanation(
    secom: SecomInference, secom_bundle: SecomBundle
) -> None:
    with pytest.raises(NotFoundError, match="warm-up"):
        await secom.get_explanation(unit_at(secom_bundle, 3))


async def test_contribution_shares_add_up(secom: SecomInference, secom_bundle: SecomBundle) -> None:
    unit = unit_at(secom_bundle, 800)
    for statistic in ("t2", "spe"):
        result = await secom.get_contributions(unit, statistic=statistic, top_k=50)
        assert sum(c.share for c in result.contributions) + result.other_share == pytest.approx(1)
        values = [c.contribution for c in result.contributions]
        assert values == sorted(values, reverse=True)


async def test_groups_report_stability_and_counts(secom: SecomInference) -> None:
    groups = await secom.get_feature_groups()
    assert [g.group_id for g in groups.groups] == ["G01", "G02", "G03"]
    assert [g.stable for g in groups.groups] == [True, False, True]
    assert groups.significant_groups == 2
    assert groups.sensors_in_significant_groups == 3
    only = await secom.get_feature_groups(significant_only=True, limit=1)
    assert [g.group_id for g in only.groups] == ["G01"]
    untested = groups.groups[2].univariate[0]
    assert untested.direction == "not_tested"
    assert untested.mann_whitney_p is None


async def test_health_as_of_a_recorded_alarm_hides_what_came_later(
    secom: SecomInference, secom_bundle: SecomBundle
) -> None:
    report = await secom.as_of(400).get_sensor_health(sensors=["S001"])
    (s001,) = report.sensors
    plant_time = secom_bundle.timeline.timestamp[400]
    for window, rate in zip(report.windows, s001.missing_by_window, strict=True):
        assert (rate is None) == (window.start > plant_time)
    everything = await secom.get_sensor_health(sensors=["S001"])
    assert None not in everything.sensors[0].missing_by_window
    assert s001.jump_unit_ids == [unit_at(secom_bundle, 10)]
    assert report.counts.watch == 1
    assert report.counts.ok == 589
    with pytest.raises(InvalidArgumentError):
        await secom.get_sensor_health(sensors=["S999"])
    watch = await secom.get_sensor_health(statuses=["watch"])
    assert [s.sensor for s in watch.sensors] == ["S001"]


async def test_sensor_series_uses_the_real_readings(
    secom: SecomInference, secom_bundle: SecomBundle
) -> None:
    series = await secom.get_sensor_series("S060", from_seq=0, to_seq=50)
    assert len(series.points) == 51
    for point in series.points:
        raw = secom_bundle.source.readings[point.unit_id, 59]
        assert point.value == (None if np.isnan(raw) else pytest.approx(raw))
    assert series.reference is not None
    assert series.reference.q01 <= series.reference.median <= series.reference.q99
    with pytest.raises(NotFoundError):
        await secom.get_sensor_series("S600")


async def test_fdc_series_covers_every_unit(secom: SecomInference) -> None:
    series = await secom.get_fdc_series()
    assert [p.sequence for p in series.points] == list(range(1567))
    assert series.n_components == 3
    assert series.features == 20


async def test_metrics_name_their_bundle(secom: SecomInference, secom_bundle: SecomBundle) -> None:
    metrics = await secom.get_metrics()
    assert metrics.bundle == secom_bundle.bundle.info.bundle
