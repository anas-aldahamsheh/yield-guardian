"""The investigator over a run (PLAN_V2 3.4, 7): run_alarm triage, tools, hypotheses, verifier.

Runs and model replies are SYNTHETIC test values (tests/agent/run_helpers.py).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
import respx
from langgraph.checkpoint.memory import InMemorySaver

from tests.agent.helpers import (
    FakeScience,
    RecordingSink,
    ScriptedModel,
    TickingClock,
    json_reply,
    text_reply,
    tool_reply,
)
from tests.agent.run_helpers import REAL_UNIT, RUN_ID, FakeRuns, LineSecom
from tests.llm.helpers import make_stack
from yield_guardian.agent.graph import InvestigationLimits, InvestigatorRunner, triage_call
from yield_guardian.agent.tools import ALL_TOOL_NAMES
from yield_guardian.contracts.investigation import InvestigationTrigger, Verification

INV = "inv_0000000002"


def alarm(alarm_id: str) -> InvestigationTrigger:
    return InvestigationTrigger(kind="run_alarm", ref=f"{RUN_ID}:{alarm_id}")


def runner(science: FakeScience, limits: InvestigationLimits | None = None) -> InvestigatorRunner:
    return InvestigatorRunner(
        gateway=make_stack().gateway,
        services=science.services,
        checkpointer=InMemorySaver(),
        limits=limits,
        wall_clock=TickingClock(),
    )


SPE_SHARE = {
    "value": 50,
    "as_written": "50%",
    "unit": "%",
    "evidence_id": "E2",
    "path": "/groups/0/spe_share",
}
SENSOR_REPORT: dict[str, Any] = {
    "summary": f"The SPE alarm RA-1 on unit U-3 of run {RUN_ID} is associated with sensor "
    "group G1.",
    "findings": [
        {
            "claim": "Sensor group G1 holds 50% of the SPE statistic of unit U-3.",
            "evidence_ids": ["E2"],
            "strength": "moderate",
        }
    ],
    "actions": [
        {
            "action": "Check the sensors of group G1.",
            "rationale": "Group G1 is associated with the SPE alarm.",
            "evidence_ids": ["E2"],
        }
    ],
    "numbers": [SPE_SHARE],
    "limitations": ["SECOM sensors are anonymous; the evidence shows association only."],
    "hypotheses": [
        {
            "hypothesis": "The deviation of sensor group G1 is associated with the SPE alarm.",
            "source_ids": [],
            "evidence_for": [
                {"evidence_id": "E2", "observation": "Group G1 holds 50% of the unit's SPE."}
            ],
            "evidence_against": [],
            "assessment": "supported",
        }
    ],
}


async def test_a_run_alarm_reads_the_run_then_its_unit_and_tests_hypotheses(
    respx_mock: respx.Router,
) -> None:
    model = ScriptedModel().mount(respx_mock)
    model.add(
        "investigator",
        tool_reply(("get_unit", {"unit_id": REAL_UNIT}), ("get_feature_groups", {})),
        text_reply("READY"),
    )
    model.add("writer", json_reply(SENSOR_REPORT))
    model.add(
        "verifier",
        json_reply({"claims": [{"finding_index": 0, "verdict": "supported", "note": "ok"}]}),
    )
    runs = FakeRuns()
    sink = RecordingSink()
    await runner(FakeScience(runs=runs)).run(INV, alarm("RA-1"), sink)

    steps = sink.final_steps()
    assert [(s.node, s.tool) for s in steps[:4]] == [
        ("triage", "get_run"),
        ("triage", "get_run_unit"),
        ("plan", None),
        ("evidence", "get_unit"),
    ]
    assert steps[1].title == f"Read unit 3 of run {RUN_ID}"
    assert [e.tool for e in sink.of("evidence")] == [
        "get_run", "get_run_unit", "get_unit", "get_feature_groups",
    ]  # fmt: skip
    first = model.bodies("investigator")[0]
    assert [t["function"]["name"] for t in first["tools"]] == list(ALL_TOOL_NAMES)
    data = json.loads(first["messages"][1]["content"].split("<data>\n")[1].split("\n</data>")[0])
    assert data["tool_calls_used"] == 2
    assert [e["tool"] for e in data["evidence"]] == ["get_run", "get_run_unit"]
    (_, verification), *_ = [v for v in sink.of("verification")]
    assert isinstance(verification, Verification)
    assert verification.passed, verification.issues
    (_, shown), *_ = sink.of("report")
    assert shown.hypotheses[0].assessment == "supported"
    assert sink.statuses == ["running", "awaiting_decision"]


@pytest.mark.parametrize(("alarm_id", "tool"), [("RA-2", "get_run_wafer"), ("RA-3", "get_run_lot")])
async def test_wafer_and_lot_alarms_read_their_item(
    respx_mock: respx.Router, alarm_id: str, tool: str
) -> None:
    model = ScriptedModel().mount(respx_mock)
    minimal = {
        "summary": f"Alarm {alarm_id} was read.",
        "findings": [],
        "actions": [],
        "numbers": [],
        "limitations": ["Association only."],
        "hypotheses": [],
    }
    model.add("writer", json_reply(minimal))
    sink = RecordingSink()
    limits = InvestigationLimits(max_tool_steps=2)  # the two triage calls, then the report
    await runner(FakeScience(runs=FakeRuns()), limits).run(INV, alarm(alarm_id), sink)
    assert [e.tool for e in sink.of("evidence")] == ["get_run", tool]
    assert model.remaining() == {}
    assert sink.statuses == ["running", "awaiting_decision"]


async def test_an_alarm_that_is_not_in_the_run_fails_without_a_model_call(
    respx_mock: respx.Router,
) -> None:
    model = ScriptedModel().mount(respx_mock)
    sink = RecordingSink()
    await runner(FakeScience(runs=FakeRuns())).run(INV, alarm("RA-9"), sink)
    (problem,) = sink.of("error")
    assert (problem.code, problem.detail) == ("not_found", f"run {RUN_ID} has no alarm RA-9")
    assert sink.statuses == ["running", "failed"]
    assert model.requests == []


async def test_a_run_that_does_not_exist_fails_at_triage(respx_mock: respx.Router) -> None:
    ScriptedModel().mount(respx_mock)
    sink = RecordingSink()
    trigger = InvestigationTrigger(kind="run_alarm", ref="run_doesnotexist:RA-1")
    await runner(FakeScience(runs=FakeRuns())).run(INV, trigger, sink)
    (problem,) = sink.of("error")
    assert problem.code == "not_found"
    assert sink.statuses == ["running", "failed"]


def test_triage_of_a_run_alarm_reads_the_run() -> None:
    assert triage_call(alarm("RA-1")) == ("get_run", {"run_id": RUN_ID})
    assert triage_call(InvestigationTrigger(kind="run_alarm", ref="RA-1")) is None


async def test_a_run_investigation_sees_every_secom_unit(respx_mock: respx.Router) -> None:
    model = ScriptedModel().mount(respx_mock)
    model.add("writer", json_reply(SENSOR_REPORT | {"hypotheses": []}))
    model.add("verifier", json_reply({"claims": []}))
    secom = LineSecom()
    sink = RecordingSink()
    limits = InvestigationLimits(max_tool_steps=2)
    await runner(FakeScience(secom=secom, runs=FakeRuns()), limits).run(INV, alarm("RA-1"), sink)
    assert set(secom.positions) == {1566}  # the whole line, whatever the replay clock says
    assert sink.statuses == ["running", "awaiting_decision"]
