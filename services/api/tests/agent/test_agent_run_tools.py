"""The run tools read one run through the RunReader: outputs, evidence, the model's view."""

from __future__ import annotations

import math
from typing import Any

import pytest

from tests.agent.helpers import FakeScience, TickingClock
from tests.agent.run_helpers import (
    LOT,
    REAL_UNIT,
    REAL_UNIT_INDEX,
    RUN_ID,
    UNITS,
    FakeRuns,
    build_run,
    ring_map,
)
from yield_guardian.agent.pointer import resolve
from yield_guardian.agent.run_tools import alarm_item_call, radial_profile
from yield_guardian.agent.tools import EvidenceLedger, ToolExecutor, ToolOutcome, model_view
from yield_guardian.contracts.investigation import Evidence


@pytest.fixture
def runs() -> FakeRuns:
    return FakeRuns()


def executor(runs: FakeRuns | None) -> ToolExecutor:
    science = FakeScience(runs=runs)
    return ToolExecutor(
        science.services, EvidenceLedger("inv_testcase01"), wall_clock=TickingClock()
    )


async def read(runs: FakeRuns | None, tool: str, **arguments: Any) -> ToolOutcome:
    return await executor(runs).execute(tool, {"run_id": RUN_ID, **arguments})


def data(outcome: ToolOutcome) -> dict[str, Any]:
    assert outcome.evidence is not None, outcome.error
    return outcome.evidence.data


async def test_get_run_gives_stages_counts_highlights_and_alarms(runs: FakeRuns) -> None:
    outcome = await read(runs, "get_run")
    assert outcome.status == "new"
    assert outcome.evidence is not None
    assert outcome.evidence.evidence_id == "E1"
    assert outcome.title == f"Read run {RUN_ID}"
    assert outcome.evidence.summary.startswith(
        f"Run {RUN_ID} (Picked items): 25 units and 3 wafers"
    )
    run = data(outcome)
    assert [s["status"] for s in run["stages"]] == ["done"] * 8
    risk = run["risk"]
    assert (risk["highest_risk"], risk["highest_risk_index"]) == (0.62, REAL_UNIT_INDEX)
    assert risk["highest_risk_unit_id"] == f"U-{REAL_UNIT_INDEX}"
    assert risk["units_above_threshold"] == 1
    assert risk["validity_counts"] == {"held_out": 1, "new_data": UNITS - 1}
    assert risk["elevated_threshold"] == 0.2
    charts = run["charts"]
    assert (charts["units_at_alarm"], charts["highest_spe"], charts["highest_spe_index"]) == (
        1,
        90.0,
        3,
    )
    assert run["drift"]["groups"][0]["first_ewma_alarm"] == 11
    assert run["wafer_patterns"]["label_counts"] == {"Edge-Ring": 3}
    assert run["wafer_patterns"]["agreeing_with_recorded"] == 1
    assert run["lots"] == [
        {
            "lot": LOT,
            "wafers": 3,
            "flagged": True,
            "flagged_labels": ["Edge-Ring"],
            "min_q_value": 0.0008,
        }
    ]
    assert run["alarm_counts"] == {"spe": 1, "wafer_pattern": 1, "lot_excursion": 1}
    assert [a["alarm_id"] for a in run["alarms"]] == ["RA-1", "RA-2", "RA-3"]
    assert (run["alarms_total"], run["alarms_not_listed"]) == (3, 0)
    view = model_view(outcome.evidence)
    assert "units" not in view["data"]["final_test"]  # per-unit lists stay in the evidence only
    assert len(run["final_test"]["units"]) == UNITS


async def test_get_run_unit_measures_each_group_and_sensor(runs: FakeRuns) -> None:
    outcome = await read(runs, "get_run_unit", unit_index=REAL_UNIT_INDEX)
    unit = data(outcome)
    assert (unit["unit_id"], unit["source_unit"], unit["recorded_result"]) == (
        "U-3",
        REAL_UNIT,
        "fail",
    )
    assert unit["risk"]["risk"] == 0.62
    assert unit["risk_threshold"] == 0.3
    assert unit["chart"]["spe"] == 90.0
    assert unit["limits"]["spe_999"] == 80.0
    first, second = unit["groups"]
    assert first["group_id"] == "G1"
    assert first["sensors"] == ["S001", "S002", "S003"]
    assert first["t2_share"] == pytest.approx(0.5)  # S001 0.3 + S002 0.2
    assert first["spe_share"] == pytest.approx(0.5)  # S002
    assert first["shap"] == pytest.approx(0.65)  # S001 0.4 + S002 0.25
    assert (first["max_abs_z"], first["max_abs_z_sensor"]) == (3.5, "S002")
    assert ("get_unit_chart", RUN_ID, REAL_UNIT_INDEX) in runs.calls  # z is not in the run
    assert unit["chart"]["z"][1] == -3.5
    assert first["ewma"] == pytest.approx(0.3)  # the group's EWMA at this unit
    assert (first["ewma_limit"], first["first_ewma_alarm"], first["cusum_upper"]) == (1.0, 11, 1.5)
    assert second == {
        "group_id": "G2", "sensors": ["S005"], "shap": 0.1, "t2_share": None, "spe_share": 0.1,
        "max_abs_z": None, "max_abs_z_sensor": None, "ewma": None, "ewma_limit": None,
        "cusum_upper": None, "cusum_lower": None, "cusum_h": None, "first_ewma_alarm": None,
        "first_cusum_alarm": None,
    }  # fmt: skip
    sensors = {s["sensor"]: s for s in unit["sensors"]}
    assert list(sensors) == ["S001", "S002", "S007", "S005", "S009"]
    assert sensors["S001"]["value"] == 3.0  # the reading in the run input
    assert sensors["S007"]["value"] == 9.0
    assert sensors["S005"]["value"] is None  # missing in the input
    assert sensors["S005"]["missing_indicator_shap"] == 0.1
    assert (sensors["S002"]["health"], sensors["S002"]["health_reasons"]) == ("watch", ["jumps"])
    assert sensors["S001"]["health"] == "ok"
    assert (sensors["S001"]["group_id"], sensors["S007"]["group_id"]) == ("G1", None)
    assert [a["alarm_id"] for a in unit["alarms"]] == ["RA-1"]
    assert any(f"SECOM unit {REAL_UNIT}" in note for note in unit["notes"])
    assert outcome.evidence is not None
    assert resolve(outcome.evidence.data, "/groups/0/t2_share") == first["t2_share"]
    assert "z" not in model_view(outcome.evidence)["data"]["chart"]
    assert outcome.evidence.summary.startswith("Run unit at position 3 (U-3, SECOM unit 1062)")


async def test_get_run_unit_without_drift_lists_feature_groups_only(runs: FakeRuns) -> None:
    runs.run = runs.run.model_copy(
        update={"stages": [s for s in runs.run.stages if s.stage != "drift_health"]}
    )
    unit = data(await read(runs, "get_run_unit", unit_index=0))
    assert [g["group_id"] for g in unit["groups"]] == ["G1", "G2"]
    assert unit["groups"][0]["sensors"] == ["S001", "S002"]  # only its listed risk features
    assert unit["groups"][0]["ewma"] is None
    assert all(s["health"] is None for s in unit["sensors"])
    assert unit["source_unit"] is None


def _ring_counts() -> tuple[int, int, int, int]:
    _, cells = ring_map()
    dies = [(i // 9, i % 9, v) for i, v in enumerate(cells) if v in (1, 2)]
    outer = [v for r, c, v in dies if math.hypot(r - 4, c - 4) >= 3]
    return len(dies), sum(v == 2 for *_, v in dies), len(outer), sum(v == 2 for v in outer)


async def test_get_run_wafer_has_pattern_shape_similar_wafers_and_causes(runs: FakeRuns) -> None:
    outcome = await read(runs, "get_run_wafer", wafer_index=0)
    wafer = data(outcome)
    dies, failed, outer, outer_failed = _ring_counts()
    assert (wafer["lot"], wafer["wafer"], wafer["source_wafer"]) == (LOT, 1, "lot47542-12")
    assert wafer["pattern"]["top_label"] == "Edge-Ring"
    assert wafer["accept_threshold"] == 0.9
    assert (wafer["dies"], wafer["failed_dies"]) == (dies, failed)
    bands = wafer["radial_profile"]
    assert [b["fail_share"] for b in bands[:3]] == [0.0, 0.0, 0.0]
    assert (bands[3]["positions"], bands[3]["fail_share"]) == (outer, outer_failed / outer)
    assert sum(b["positions"] for b in bands) == dies
    assert wafer["similar_recorded_labels"] == {"Edge-Ring": 2, "Center": 1}
    assert (wafer["similar_unlabelled"], wafer["similar_matching_pattern"]) == (1, 2)
    assert [c["label"] for c in wafer["causes"]] == ["Edge-Ring"]
    assert [s["source_id"] for s in wafer["sources"]] == ["src_fixture_1"]
    assert wafer["lot_result"]["lot"] == LOT
    assert [a["alarm_id"] for a in wafer["alarms"]] == ["RA-2", "RA-3"]
    assert ("get_wafer_input", RUN_ID, 0) not in runs.calls  # the pattern stage has the map
    assert outcome.evidence is not None
    view = model_view(outcome.evidence)["data"]
    assert "map" not in view["pattern"]
    assert all("map" not in item for item in view["similar"])
    assert "stacked" not in view["lot_result"]


async def test_get_run_wafer_falls_back_to_the_input_and_the_knowledge_base(runs: FakeRuns) -> None:
    skipped = {"status": "skipped", "needs": "a failed test stage", "result": None}
    stages = [
        s.model_copy(update=skipped) if s.stage in ("wafer_pattern", "wafer_similar") else s
        for s in runs.run.stages
    ]
    runs.run = runs.run.model_copy(update={"stages": stages})
    wafer = data(await read(runs, "get_run_wafer", wafer_index=0))
    assert wafer["pattern"] is None
    assert wafer["causes"] == []  # no predicted pattern, so no candidate causes
    assert wafer["source_wafer"] == "lot47542-12"
    assert wafer["recorded_label"] == "Edge-Ring"
    assert wafer["dies"] == _ring_counts()[0]
    assert "wafer_pattern was skipped: a failed test stage" in wafer["notes"]


async def test_get_run_lot_has_tests_stacked_profile_wafers_and_alarms(runs: FakeRuns) -> None:
    outcome = await read(runs, "get_run_lot", lot=LOT)
    lot = data(outcome)
    _, _, outer, outer_failed = _ring_counts()
    assert lot["result"]["tests"][0]["flagged"] is True
    assert lot["stacked_radial_profile"][3]["fail_share"] == outer_failed / outer
    assert lot["wafers_total"] == 3
    assert [w["source_wafer"] for w in lot["wafers"]] == ["lot47542-12", None, None]
    assert [a["alarm_id"] for a in lot["alarms"]] == ["RA-2", "RA-3"]
    assert outcome.evidence is not None
    assert "stacked" not in model_view(outcome.evidence)["data"]["result"]


@pytest.mark.parametrize(
    ("tool", "arguments", "code", "detail"),
    [
        ("get_run_unit", {"unit_index": 99}, "not_found", "positions 0 to 24"),
        ("get_run_wafer", {"wafer_index": 3}, "not_found", "positions 0 to 2"),
        ("get_run_lot", {"lot": "ZZ"}, "not_found", "its lots: L7A"),
    ],
)
async def test_items_outside_the_run_are_refused(
    runs: FakeRuns, tool: str, arguments: dict[str, Any], code: str, detail: str
) -> None:
    outcome = await read(runs, tool, **arguments)
    assert outcome.status == "failed"
    assert outcome.problem is not None
    assert outcome.problem.code == code
    assert detail in (outcome.error or "")


async def test_an_unknown_run_and_a_missing_run_store_are_failed_calls(runs: FakeRuns) -> None:
    unknown = await executor(runs).execute("get_run", {"run_id": "run_doesnotexist"})
    assert (unknown.status, unknown.problem and unknown.problem.code) == ("failed", "not_found")
    missing = await read(None, "get_run")
    assert (missing.status, missing.problem and missing.problem.code) == ("failed", "not_ready")
    invalid = await executor(runs).execute("get_run", {"run_id": "RUN 1"})
    assert invalid.status == "invalid"


async def test_the_same_run_call_twice_reuses_its_evidence(runs: FakeRuns) -> None:
    run = executor(runs)
    first = await run.execute("get_run_unit", {"run_id": RUN_ID, "unit_index": 1})
    again = await run.execute("get_run_unit", {"run_id": RUN_ID, "unit_index": 1})
    assert again.status == "reused"
    assert isinstance(again.evidence, Evidence)
    assert first.evidence == again.evidence


def test_alarm_item_call_follows_the_alarm_to_its_item() -> None:
    run = build_run()
    assert alarm_item_call(run, "RA-1") == ("get_run_unit", {"run_id": RUN_ID, "unit_index": 3})
    assert alarm_item_call(run, "RA-2") == ("get_run_wafer", {"run_id": RUN_ID, "wafer_index": 0})
    assert alarm_item_call(run, "RA-3") == ("get_run_lot", {"run_id": RUN_ID, "lot": LOT})
    assert alarm_item_call(run, "RA-9") is None


def test_radial_profile_bands_run_from_the_centre_to_the_edge() -> None:
    # A 1 x 5 row of dies: centre at column 2, radius 2; only the ends failed.
    bands = radial_profile(5, [(0, 1.0), (1, 0.0), (2, 0.0), (3, 0.0), (4, 1.0)])
    assert [(b.inner, b.outer, b.positions, b.fail_share) for b in bands] == [
        (0.0, 0.25, 1, 0.0),
        (0.25, 0.5, 0, None),
        (0.5, 0.75, 2, 0.0),
        (0.75, 1.0, 2, 1.0),
    ]
    assert radial_profile(5, []) == []
