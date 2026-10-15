"""A recorded run reads the data as of its alarm; a live run reads every unit.

The first recording on the server failed at triage with "Unit 1303 has not come off the line
yet": the recorder picked a test-block alarm while the (since retired) replay cursor was near
unit 350. Without a replay clock a live run reads any unit, and a recorded run still reads the
data as of its alarm. Model replies are scripted (values synthetic); the SECOM data and bundle
are the real test bundle.
"""

from __future__ import annotations

from typing import cast

import pytest
import respx
from langgraph.checkpoint.memory import InMemorySaver

from tests.agent.helpers import (
    FakeKnowledge,
    FakeWafer,
    RecordingSink,
    ScriptedModel,
    TickingClock,
    json_reply,
    text_reply,
)
from tests.llm.helpers import make_stack
from yield_guardian.agent.graph import InvestigatorRunner, paused_values, services_as_of
from yield_guardian.agent.recording import choose_alarms
from yield_guardian.bundles.secom import SecomBundle
from yield_guardian.contracts.services import (
    InvalidArgumentError,
    KnowledgeService,
    NotFoundError,
    ScienceServices,
    SecomService,
    WaferService,
)
from yield_guardian.science.secom.service import SecomInference

INV = "inv_0000000000recorded01"
MINIMAL_REPORT = {
    "summary": "The alarm was read.",
    "findings": [],
    "actions": [],
    "numbers": [],
    "limitations": ["Association only."],
}


def services(secom: SecomInference) -> ScienceServices:
    return ScienceServices(
        secom=cast(SecomService, secom),
        wafer=cast(WaferService, FakeWafer()),
        knowledge=cast(KnowledgeService, FakeKnowledge()),
    )


def runner(secom: SecomInference) -> InvestigatorRunner:
    return InvestigatorRunner(
        gateway=make_stack().gateway,
        services=services(secom),
        checkpointer=InMemorySaver(),
        wall_clock=TickingClock(),
    )


async def test_a_live_run_on_a_test_block_alarm_reads_its_unit(
    secom: SecomInference, secom_bundle: SecomBundle, respx_mock: respx.Router
) -> None:
    (alarm,) = choose_alarms(secom_bundle, 1)
    model = ScriptedModel().mount(respx_mock)
    model.add("investigator", text_reply("READY"))
    model.add("writer", json_reply(MINIMAL_REPORT))
    sink = RecordingSink()
    await runner(secom).run(INV, alarm.trigger(), sink)
    assert sink.of("error") == []
    assert sink.statuses == ["running", "awaiting_decision"]
    (evidence, *_) = sink.of("evidence")
    assert evidence.data["unit_id"] == alarm.unit_id


async def test_a_recorded_run_reads_the_line_as_of_its_alarm(
    secom: SecomInference, secom_bundle: SecomBundle, respx_mock: respx.Router
) -> None:
    (alarm,) = choose_alarms(secom_bundle, 1)
    model = ScriptedModel().mount(respx_mock)
    model.add("investigator", text_reply("READY"))
    model.add("writer", json_reply(MINIMAL_REPORT))
    run = runner(secom)
    sink = RecordingSink()
    await run.run(INV, alarm.trigger(), sink, as_of=alarm.sequence)
    assert sink.of("error") == []
    assert sink.statuses == ["running", "awaiting_decision"]
    (evidence, *_) = sink.of("evidence")
    assert evidence.tool == "get_unit"
    assert evidence.data["unit_id"] == alarm.unit_id
    alarm_ids = [a["alarm_id"] for a in evidence.data["alarms"]]
    assert alarm.alarm_id in alarm_ids
    # The position is part of the saved state, so an exported and imported run keeps it.
    state = await paused_values(run.graph.checkpointer, INV)  # type: ignore[arg-type]
    assert state is not None
    assert state["as_of"] == alarm.sequence
    # The live service itself is unchanged: it reads every unit.
    assert secom.fixed_position is None
    later = int(secom_bundle.timeline.unit_id[alarm.sequence + 1])
    assert (await secom.get_unit(later)).sequence == alarm.sequence + 1


async def test_as_of_hides_every_unit_after_the_alarm(
    secom: SecomInference, secom_bundle: SecomBundle
) -> None:
    (alarm,) = choose_alarms(secom_bundle, 1)
    view = secom.as_of(alarm.sequence)
    timeline = secom_bundle.timeline
    later = int(timeline.unit_id[alarm.sequence + 1])
    await view.get_unit(alarm.unit_id)
    with pytest.raises(NotFoundError, match="not come off the line"):
        await view.get_unit(later)
    page = await view.list_units(limit=1000000)
    assert max(u.sequence for u in page.items) <= alarm.sequence
    with pytest.raises(InvalidArgumentError):
        secom.as_of(len(timeline))


def test_live_services_are_unchanged_without_a_position(secom: SecomInference) -> None:
    live = services(secom)
    assert services_as_of(live, None) is live
    recorded = services_as_of(live, 5)
    assert recorded.secom is not live.secom
    assert cast(SecomInference, recorded.secom).fixed_position == 5
    assert secom.fixed_position is None
