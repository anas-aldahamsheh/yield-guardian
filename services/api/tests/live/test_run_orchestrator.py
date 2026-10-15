"""The run orchestrator: stage order and timing, skipped tracks, failing engines, alarms, z, and
the materialiser. The sensor track is the real SECOM engine on real units; the wafer engine is
a double (tests/live/doubles.py) until V3 is on main."""

import math
import re
from random import Random

import numpy as np
import pytest

from tests.live.doubles import (
    Calls,
    MemoryWriter,
    WaferDouble,
    Wrapped,
    held_out_ids,
    real_sensor_engine,
    small_wafer,
)
from yield_guardian.contracts.runs import (
    AlarmEvent,
    CaseRunCreate,
    ControlChartsResult,
    DrawnRunCreate,
    IntakeResult,
    PickRunCreate,
    RunDoneEvent,
    SampleRunCreate,
    SensorUnitInput,
    StageFailedEvent,
    StageResultEvent,
    StageSkippedEvent,
    UploadRunCreate,
    WaferInput,
)
from yield_guardian.contracts.services import NotFoundError, NotReadyError, UpstreamError
from yield_guardian.contracts.wafer import WaferMap
from yield_guardian.live.run_alarms import QUOTAS
from yield_guardian.live.runs import (
    NEEDS_SENSORS,
    NEEDS_WAFERS,
    Engines,
    Materialiser,
    RunOrchestrator,
)
from yield_guardian.live.stages import final_test, in_time_order, intake
from yield_guardian.services.runs import (
    STAGES,
    Z_IN_RESULT,
    InputError,
    RunInput,
    decode_z,
    encode_z,
)

RUN = "run_01jaf3k9x2m4q7r8s0t1v2w3x4"


def units(n: int = 40) -> list[SensorUnitInput]:
    """`n` consecutive real units of the SECOM test block, in time order."""
    return real_sensor_engine().from_secom(held_out_ids()[:n])


async def execute(engines: Engines, data: RunInput) -> MemoryWriter:
    writer = MemoryWriter()
    orchestrator = RunOrchestrator(engines, writer, heartbeat_s=0.01)
    await orchestrator.execute(RUN, data, orchestrator.plan(data))
    return writer


def ends(writer: MemoryWriter) -> dict[str, str]:
    """Each stage's closing event type."""
    return {
        e.stage: e.type
        for e in writer.events
        if isinstance(e, StageResultEvent | StageSkippedEvent | StageFailedEvent)
    }


async def test_stages_run_in_order_one_at_a_time_and_time_their_compute() -> None:
    calls = Calls()
    delay = 0.05
    sensors = Wrapped(real_sensor_engine(), calls, delay=delay)
    wafers = WaferDouble(timing=calls, delay=delay)
    data = RunInput(
        units=units(),
        wafers=[small_wafer("L1", 1, label="none"), small_wafer("L1", 2, label="none")],
    )
    writer = await execute(Engines(sensors=sensors, wafers=wafers), data)

    closing = [e for e in writer.events if e.type in {"stage_result", "stage_skipped"}]
    assert [e.stage for e in closing if hasattr(e, "stage")] == list(STAGES)
    # Every attempted stage is announced first, and nothing interleaves.
    kinds = [k for k in writer.kinds() if k[0] != "alarm"]
    for stage in STAGES:
        assert kinds.index(("stage_started", stage)) + 1 == kinds.index(("stage_result", stage))
    assert kinds[-1] == ("run_done", None)
    # The engine calls ran one after the other, in stage order.
    assert [name for name, _, _ in calls.spans] == [
        "sensor_risk",
        "control_charts",
        "drift_health",
        "wafer_pattern",
        "wafer_similar",
        "lot",
    ]
    for (_, _, end), (_, start, _) in zip(calls.spans, calls.spans[1:], strict=False):
        assert end <= start
    # elapsed_ms is the stage's own compute time, measured in the worker thread.
    for event in writer.events:
        if isinstance(event, StageResultEvent) and event.stage in {"sensor_risk", "lot"}:
            assert event.elapsed_ms >= delay * 1000
            assert event.elapsed_ms < 5_000
    assert writer.statuses == ["running", "done"]
    done = writer.events[-1]
    assert isinstance(done, RunDoneEvent)
    assert done.status == "done"
    assert writer.heartbeats > 0  # the ticker beats while a stage computes


async def test_a_missing_track_is_skipped_at_its_place_and_says_what_it_needs() -> None:
    sensors_only = await execute(
        Engines(sensors=real_sensor_engine(), wafers=WaferDouble()), RunInput(units=units())
    )
    skipped = {e.stage: e.needs for e in sensors_only.events if isinstance(e, StageSkippedEvent)}
    assert skipped == {
        "wafer_pattern": NEEDS_WAFERS,
        "wafer_similar": NEEDS_WAFERS,
        "lot": NEEDS_WAFERS,
    }
    order = [getattr(e, "stage", None) for e in sensors_only.events if e.type != "alarm"]
    assert order.index("wafer_pattern") > order.index("drift_health")
    assert order.index("wafer_pattern") < order.index("final_test")

    wafers_only = await execute(
        Engines(sensors=real_sensor_engine(), wafers=WaferDouble()),
        RunInput(wafers=[small_wafer("L1", 1, label="none")]),
    )
    skipped = {e.stage: e.needs for e in wafers_only.events if isinstance(e, StageSkippedEvent)}
    assert skipped["sensor_risk"] == NEEDS_SENSORS
    assert skipped["control_charts"] == NEEDS_SENSORS
    assert skipped["drift_health"] == NEEDS_SENSORS
    # One wafer: the lot test says what it needs (the double runs it; the real engine would
    # raise NeedsInput), and final test compares the recorded label.
    assert ends(wafers_only)["final_test"] == "stage_result"


async def test_a_failing_engine_fails_its_stage_and_the_run_goes_on() -> None:
    sensors = Wrapped(real_sensor_engine(), fail={"control_charts": RuntimeError("boom")})
    wafers = WaferDouble(fail={"wafer_pattern": UpstreamError("model service down")})
    writer = await execute(
        Engines(sensors=sensors, wafers=wafers),
        RunInput(units=units(), wafers=[small_wafer("L1", 1, label="none")]),
    )
    closing = ends(writer)
    assert closing["control_charts"] == "stage_failed"
    assert closing["drift_health"] == "stage_result"  # the run went on
    assert closing["wafer_pattern"] == "stage_failed"
    assert closing["wafer_similar"] == "stage_skipped"  # needs the pattern result
    assert closing["final_test"] == "stage_result"  # the risk stage finished
    failed = {e.stage: e.problem for e in writer.events if isinstance(e, StageFailedEvent)}
    assert failed["control_charts"].code == "internal_error"
    assert "boom" not in (failed["control_charts"].detail or "")  # no internals leak out
    assert failed["wafer_pattern"].code == "upstream_error"
    assert writer.stages["control_charts"].status == "failed"
    done = writer.events[-1]
    assert isinstance(done, RunDoneEvent)
    assert done.status == "failed"


async def test_units_whose_time_goes_back_keep_their_order_and_skip_drift() -> None:
    given = units(30)
    given[10], given[11] = given[11], given[10]
    writer = await execute(Engines(sensors=real_sensor_engine()), RunInput(units=given))
    intake_result = next(
        e.result for e in writer.events if isinstance(e, StageResultEvent) and e.stage == "intake"
    )
    assert isinstance(intake_result, IntakeResult)
    assert intake_result.in_time_order is False
    drift = next(
        e for e in writer.events if isinstance(e, StageSkippedEvent) and e.stage == "drift_health"
    )
    assert "Sort the file by timestamp" in drift.needs
    assert writer.stages["drift_health"].needs == drift.needs
    charts = next(
        e.result
        for e in writer.events
        if isinstance(e, StageResultEvent) and e.stage == "control_charts"
    )
    assert isinstance(charts, ControlChartsResult)
    assert [u.unit_id for u in charts.units] == [u.unit_id for u in given]  # never re-sorted


async def test_alarms_follow_their_stage_result_capped_per_stage() -> None:
    every = units(len(held_out_ids()))
    writer = await execute(Engines(sensors=real_sensor_engine()), RunInput(units=every))
    events = writer.events
    for i, event in enumerate(events):
        if isinstance(event, AlarmEvent):
            before = events[i - 1]
            assert isinstance(before, StageResultEvent | AlarmEvent)
            raised_by = before.stage if isinstance(before, StageResultEvent) else before.alarm.stage
            assert event.alarm.stage == raised_by
    alarms = [e.alarm for e in events if isinstance(e, AlarmEvent)]
    assert [a.alarm_id for a in alarms] == [f"RA-{n}" for n in range(1, len(alarms) + 1)]
    for stage, quota in QUOTAS.items():
        assert sum(a.stage == stage for a in alarms) <= quota
    charts = [a for a in alarms if a.stage == "control_charts"]
    assert charts, "the 313 held-out units raise control-chart alarms"
    ranked = [(a.severity != "alarm", -(a.value or 0) / (a.limit or 1)) for a in charts]
    assert ranked == sorted(ranked)  # most severe first
    done = events[-1]
    assert isinstance(done, RunDoneEvent)
    assert done.alarms == len(alarms) == len(writer.alarms)
    assert done.alarms_not_listed == writer.not_listed > 0


async def test_z_rides_for_the_first_200_units_and_every_unit_chart_is_kept() -> None:
    every = units(len(held_out_ids()))
    writer = await execute(Engines(sensors=real_sensor_engine()), RunInput(units=every))
    event = next(
        e for e in writer.events if isinstance(e, StageResultEvent) and e.stage == "control_charts"
    )
    assert isinstance(event.result, ControlChartsResult)
    shown = event.result.units
    assert all(u.z is not None for u in shown[:Z_IN_RESULT])
    assert all(u.z is None for u in shown[Z_IN_RESULT:])
    stored = writer.stages["control_charts"].result
    assert stored == event.result  # GET carries the same numbers as the stream
    assert [u.index for u in writer.unit_charts] == list(range(len(every)))
    assert all(u.z is not None for u in writer.unit_charts)
    assert writer.unit_charts[5].z == shown[5].z
    live = real_sensor_engine().control_charts(every).units[250].z
    assert live is not None
    kept = writer.unit_charts[250].z
    assert kept is not None
    assert len(kept) == len(live)
    for a, b in zip(kept, live, strict=True):
        assert (a is None) == (b is None)
        if a is not None and b is not None:
            assert a == float(np.float32(b))


def test_z_is_kept_as_float32_with_nan_for_missing() -> None:
    blob = encode_z([0.5, None, -1.25, 3.0e-8])
    assert blob is not None
    assert len(blob) == 16
    decoded = decode_z(blob)
    assert decoded is not None
    assert decoded[1] is None
    assert decoded[0] == 0.5
    assert decoded[2] == -1.25
    assert decoded[3] is not None
    assert math.isclose(decoded[3], 3.0e-8, rel_tol=1e-6)
    assert encode_z(None) is None
    assert decode_z(None) is None


# Stages written here --------------------------------------------------------------------------


def test_intake_counts_what_came_in() -> None:
    given = units(25)
    result = intake(given, [small_wafer("A", 1), small_wafer("B", 1)], ["S006"])
    assert result.units == 25
    assert result.wafers == 2
    assert result.lots == 2
    assert result.missing_readings == sum(r is None for u in given for r in u.readings)
    assert result.in_time_order is True
    assert result.two_sources is True
    assert result.first_timestamp == given[0].timestamp
    assert intake([], [small_wafer("A", 1)], ["S006"]).unmonitored_sensors == []
    undated = [given[0], given[1].model_copy(update={"timestamp": None})]
    assert in_time_order(undated) is False
    same = [given[0], given[0].model_copy(update={"unit_id": "again"})]
    assert in_time_order(same) is True  # equal times are in order


def test_final_test_compares_warnings_with_recorded_results() -> None:
    given = units(40)
    risk = real_sensor_engine().risk(given)
    result = final_test(given, [], risk, None)
    flagged = {u.index for u in risk.units if u.above_threshold}
    assert result.units_with_result == 40
    assert result.failed_units == sum(u.result == "fail" for u in given)
    assert result.failed_flagged == sum(
        1 for i, u in enumerate(given) if u.result == "fail" and i in flagged
    )
    assert result.wafers == []
    assert result.wafers_with_label == 0
    no_risk = final_test(given, [], None, None)
    assert no_risk.units == []
    assert no_risk.summary == "Nothing in the input could be compared."


# Materialiser ---------------------------------------------------------------------------------


def lots() -> dict[str, list[WaferInput]]:
    return {
        "lotA": [small_wafer("lotA", 1), small_wafer("lotA", 2)],
        "lotB": [small_wafer("lotB", 1)],
    }


async def test_a_sample_is_the_same_for_the_same_seed() -> None:
    materialise = Materialiser(
        Engines(sensors=real_sensor_engine(), wafers=WaferDouble(demo=lots())), None, None
    )
    first_origin, first = await materialise(SampleRunCreate(source="sample", seed=7))
    again_origin, again = await materialise(SampleRunCreate(source="sample", seed=7))
    other_origin, other = await materialise(SampleRunCreate(source="sample", seed=8))
    assert first == again
    assert first_origin == again_origin
    assert first_origin.seed == 7
    assert "Seed 7" in first_origin.rule
    assert first_origin.datasets == ["secom", "wm811k"]
    assert [u.unit_id for u in first.units] != [u.unit_id for u in other.units]
    assert other_origin.seed == 8
    # One Random for both: the units are the engine's own pick for that seed, wafers after.
    rng = Random(7)
    expected = real_sensor_engine().sample(rng)
    assert first.units == expected.items
    assert first.wafers == WaferDouble(demo=lots()).sample(rng).items
    unseeded, _ = await materialise(SampleRunCreate(source="sample"))
    assert unseeded.seed is not None
    assert f"Seed {unseeded.seed}" in unseeded.rule


async def test_a_sample_without_the_wafer_engine_takes_the_units_and_says_so() -> None:
    materialise = Materialiser(Engines(sensors=real_sensor_engine()), None, None)
    origin, data = await materialise(SampleRunCreate(source="sample", seed=7))
    both, _ = await Materialiser(
        Engines(sensors=real_sensor_engine(), wafers=WaferDouble(demo=lots())), None, None
    )(SampleRunCreate(source="sample", seed=7))
    assert data.wafers == []
    assert origin.datasets == ["secom"]
    assert "wafer-map bundle is not loaded" in origin.rule
    assert [u.unit_id for u in data.units] == [
        u.unit_id for u in real_sensor_engine().sample(Random(7)).items
    ]
    assert both.rule != origin.rule
    with pytest.raises(NotReadyError):
        await Materialiser(Engines(), None, None)(SampleRunCreate(source="sample"))


async def test_a_pick_is_real_rows_and_refuses_repeats_and_unknown_ids() -> None:
    materialise = Materialiser(
        Engines(sensors=real_sensor_engine(), wafers=WaferDouble(demo=lots())), None, None
    )
    origin, data = await materialise(PickRunCreate(source="pick", unit_ids=[1043, 3], lot="lotA"))
    assert [u.source_unit for u in data.units] == [3, 1043]  # time order
    assert len(data.wafers) == 2
    assert origin.datasets == ["secom", "wm811k"]
    with pytest.raises(InputError, match="picked twice"):
        await materialise(PickRunCreate(source="pick", unit_ids=[3, 3]))
    with pytest.raises(NotFoundError, match="1567"):  # 404, as for a wafer or lot
        await materialise(PickRunCreate(source="pick", unit_ids=[1567]))
    with pytest.raises(NotFoundError, match="nolot"):
        await materialise(PickRunCreate(source="pick", lot="nolot"))
    with pytest.raises(NotFoundError, match="nolot-1"):
        await materialise(PickRunCreate(source="pick", wafer_ids=["nolot-1"]))
    with pytest.raises(InputError):
        await materialise(PickRunCreate(source="pick"))


async def test_a_drawing_is_your_drawing_and_is_checked() -> None:
    materialise = Materialiser(Engines(wafers=WaferDouble()), None, None)
    drawn = small_wafer("mine", 1, fails=[4], label="Center").model_copy(
        update={"source_wafer": "lot1-1"}
    )
    origin, data = await materialise(DrawnRunCreate(source="drawn", wafers=[drawn]))
    assert origin.title == "Your drawing"
    assert origin.datasets == ["user"]
    assert data.wafers[0].label is None
    assert data.wafers[0].source_wafer is None
    for cells, said in (
        ("AQEB", "3 x 3 needs 9"),
        ("not base64!", "not valid base64"),
        ("AQEBAQEBAQED", "0 (no die), 1 (pass) or 2 (fail)"),
        ("AAAAAAAAAAAA", "no die"),
    ):
        bad = drawn.model_copy(update={"map": WaferMap(height=3, width=3, cells=cells)})
        with pytest.raises(InputError, match=re.escape(said)) as raised:
            await materialise(DrawnRunCreate(source="drawn", wafers=[drawn, bad]))
        assert raised.value.status == 422
        assert raised.value.detail.startswith("Drawing 2: ")
    with pytest.raises(NotReadyError):
        await Materialiser(Engines(), None, None)(DrawnRunCreate(source="drawn", wafers=[drawn]))


async def test_cases_and_uploads_need_their_sources() -> None:
    materialise = Materialiser(Engines(), None, None)
    with pytest.raises(NotReadyError):
        await materialise(CaseRunCreate(source="case", case_id="spe_alarm"))
    with pytest.raises(NotReadyError):
        await materialise(
            UploadRunCreate(source="upload", upload_id="upl_01jaf3k9x2m4q7r8s0t1v2w3x4")
        )
