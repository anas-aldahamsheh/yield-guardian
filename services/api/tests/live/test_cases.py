"""The case catalog: fixed rules over live computations, deterministic, and a case run computes
what its rule saw. Sensor cases use the real SECOM engine; wafer cases the wafer double."""

import asyncio
import threading

import pytest

from tests.live.doubles import (
    WaferCall,
    WaferDouble,
    held_out_ids,
    real_secom,
    real_sensor_engine,
    small_wafer,
)
from yield_guardian.contracts.runs import WaferInput
from yield_guardian.contracts.services import NotFoundError, NotReadyError
from yield_guardian.live.cases import (
    DRIFT_WINDOW,
    SPE_WINDOW,
    CaseCatalog,
    sensor_cases,
    wafer_cases,
)
from yield_guardian.live.wiring import secom_units


def test_sensor_cases_are_found_by_their_rules_on_live_results() -> None:
    units, held_out = secom_units(real_secom())
    assert held_out == held_out_ids()
    engine = real_sensor_engine()
    found = {c.case.case_id: c for c in sensor_cases(engine, units, held_out)}
    assert set(found) == {"spe_alarm", "slow_drift"}

    spe = found["spe_alarm"]
    assert len(spe.unit_ids) == SPE_WINDOW
    last = spe.unit_ids[-1]
    assert last in held_out
    assert list(spe.unit_ids) == units[units.index(last) - SPE_WINDOW + 1 : units.index(last) + 1]
    charts = engine.control_charts(engine.from_secom(spe.unit_ids))
    assert charts.units[-1].spe > charts.limits.spe_999
    # It is the first held-out unit over the limit.
    every = engine.control_charts(engine.from_secom(held_out))
    first = next(u for u in every.units if u.spe > every.limits.spe_999)
    assert held_out[first.index] == last
    assert spe.case.units == SPE_WINDOW
    assert spe.case.datasets == ["secom"]

    drift = found["slow_drift"]
    assert len(drift.unit_ids) == DRIFT_WINDOW
    start = held_out.index(drift.unit_ids[0])
    assert start % DRIFT_WINDOW == 0
    assert list(drift.unit_ids) == held_out[start : start + DRIFT_WINDOW]
    result = engine.drift_health(engine.from_secom(drift.unit_ids))
    assert any(
        g.first_ewma_alarm is not None or g.first_cusum_alarm is not None for g in result.groups
    )

    again = {c.case.case_id: c for c in sensor_cases(engine, units, held_out)}
    assert again == found  # deterministic


def lot(name: str, n: int) -> list[WaferInput]:
    return [
        small_wafer(name, i).model_copy(update={"source_wafer": f"{name}-{i}"})
        for i in range(1, n + 1)
    ]


def test_wafer_cases_are_the_first_or_strongest_by_their_rules() -> None:
    demo = {"lotB": lot("lotB", 3), "lotA": lot("lotA", 2), "lotC": lot("lotC", 1)}
    calls = {
        ("lotB", 1): WaferCall(label="Scratch"),
        ("lotA", 2): WaferCall(label="Scratch"),  # first by lot name: lotA comes before lotB
        ("lotA", 1): WaferCall(label="Scratch", accepted=False),
        ("lotB", 2): WaferCall(unknown_score=30.0, unknown_threshold=10.0),
        ("lotC", 1): WaferCall(unknown_score=50.0, unknown_threshold=10.0),
    }
    engine = WaferDouble(calls=calls, q={"lotA": 0.2, "lotB": 0.01}, demo=demo)
    found = {c.case.case_id: c for c in wafer_cases(engine, list(demo))}
    assert found["scratch"].wafer_ids == ("lotA-2",)
    assert found["unknown_pattern"].wafer_ids == ("lotC-1",)
    repeat = found["lot_repeat"]
    assert repeat.lot == "lotB"
    assert repeat.case.wafers == 3
    assert repeat.case.title == "A lot with a repeating pattern"
    # lotC has one wafer: no lot test, so it is not a candidate.
    calm = WaferDouble(calls=calls, q={"lotA": 0.3, "lotB": 0.2}, demo=demo)
    weak = {c.case.case_id: c for c in wafer_cases(calm, list(demo))}["lot_repeat"]
    assert weak.case.title == "The lot closest to a repeating pattern"
    assert "not flagged" in weak.case.description
    assert wafer_cases(WaferDouble(demo={"lotA": lot("lotA", 1)}), ["lotA"]) == []
    stop = threading.Event()
    stop.set()
    assert wafer_cases(engine, list(demo), stop) == []


async def test_the_catalog_serves_cases_and_materialises_them() -> None:
    demo = {"lotA": lot("lotA", 2)}
    wafers = WaferDouble(
        calls={("lotA", 1): WaferCall(label="Scratch")}, q={"lotA": 0.01}, demo=demo
    )
    units, held_out = secom_units(real_secom())
    catalog = CaseCatalog(
        real_sensor_engine(), wafers, units=units, held_out=held_out, lots=["lotA"]
    )
    await catalog.start()
    listed = await catalog.list()
    assert [c.case_id for c in listed.items] == ["spe_alarm", "slow_drift", "scratch", "lot_repeat"]
    origin, data = await catalog.materialise("spe_alarm")
    assert origin.source == "case"
    assert origin.case_id == "spe_alarm"
    assert len(data.units) == SPE_WINDOW
    assert [u.source_unit for u in data.units] == list(
        next(c for c in await catalog.cases() if c.case.case_id == "spe_alarm").unit_ids
    )
    _, lot_run = await catalog.materialise("lot_repeat")
    assert [w.source_wafer for w in lot_run.wafers] == ["lotA-1", "lotA-2"]
    with pytest.raises(NotFoundError):
        await catalog.materialise("no_such_case")
    await catalog.stop()


async def test_a_catalog_still_computing_answers_not_ready_with_a_retry() -> None:
    gate = threading.Event()

    class Slow(WaferDouble):
        def from_demo(self, wafer_ids=(), lot=None):  # type: ignore[no-untyped-def]
            gate.wait(5)
            return super().from_demo(wafer_ids, lot)

    catalog = CaseCatalog(None, Slow(demo={"lotA": lot("lotA", 2)}), lots=["lotA"], wait_s=0.05)
    await catalog.start()
    with pytest.raises(NotReadyError) as raised:
        await catalog.list()
    assert raised.value.retry_after_s == 5
    gate.set()
    await asyncio.sleep(0)
    catalog.wait_s = 5
    assert [c.case_id for c in (await catalog.list()).items] == ["lot_repeat"]
    await catalog.stop()
