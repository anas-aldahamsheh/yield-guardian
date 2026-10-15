"""The chat over runs (PLAN_V2 8): page context, run tools, the numeric gate and the offer to
start an investigation. Runs and replies are SYNTHETIC test values."""

from __future__ import annotations

import json

import pytest
import respx
from pydantic import ValidationError

from tests.agent.helpers import (
    FakeScience,
    ScriptedModel,
    stream_reply,
    text_reply,
    tool_reply,
)
from tests.agent.run_helpers import LOT, REAL_UNIT, RUN_ID, FakeRuns, LineSecom
from tests.agent.test_agent_chat import answerer, ask, collect, last, text, types
from yield_guardian.agent.chat import question_facts
from yield_guardian.agent.grounding import REDACTED
from yield_guardian.agent.tools import ALL_TOOL_NAMES
from yield_guardian.contracts.chat import ChatContext, ChatEvent, ChatSuggestionEvent

CONTEXT = ChatContext(run_id=RUN_ID, station="monitoring", run_unit=3, run_alarm="RA-1")


def suggest(kind: str, ref: str) -> tuple[str, dict[str, str]]:
    return ("suggest_investigation", {"kind": kind, "ref": ref})


def test_run_fields_of_the_context_need_a_run() -> None:
    with pytest.raises(ValidationError, match="need run_id"):
        ChatContext(run_unit=3)
    assert ChatContext(run_id=RUN_ID, run_lot="L7A", run_wafer=0).run_lot == "L7A"
    with pytest.raises(ValidationError):
        ChatContext(run_id="not a run")


async def test_with_a_run_on_the_page_the_model_reads_it(respx_mock: respx.Router) -> None:
    model = ScriptedModel().mount(respx_mock)
    model.add(
        "chat",
        tool_reply(("get_run_unit", {"run_id": RUN_ID, "unit_index": 3})),
        text_reply("enough"),
        stream_reply("Group G1 holds 50% of the unit's SPE [E1]. ", "Its risk is 0.99 [E1]."),
    )
    chat, _ = answerer(FakeScience(runs=FakeRuns()))
    events = await collect(chat, ask("Why did this unit alarm?", context=CONTEXT))
    first = model.bodies("chat")[0]
    offered = [t["function"]["name"] for t in first["tools"]]
    assert offered == [*ALL_TOOL_NAMES, "suggest_investigation"]
    looking_at = json.loads(
        first["messages"][1]["content"].split("<data>\n")[1].split("\n</data>")[0]
    )
    assert looking_at["looking_at"] == CONTEXT.model_dump(mode="json", exclude_none=True)
    assert types(events)[:3] == ["route", "tool", "citation"]
    answer = text(events)
    assert "50%" in answer  # in the evidence: spe_share 0.5
    assert f"Its risk is {REDACTED}" in answer  # 0.99 is not: the gate still applies
    assert last(events).numbers_unverified == ["0.99"]


async def test_the_model_offers_an_investigation_of_a_run_alarm(respx_mock: respx.Router) -> None:
    model = ScriptedModel().mount(respx_mock)
    model.add(
        "chat",
        tool_reply(suggest("run_alarm", f"{RUN_ID}:RA-1")),
        text_reply("done"),
        stream_reply("You can start an investigation of this alarm."),
    )
    chat, _ = answerer(FakeScience(runs=FakeRuns()))
    events = await collect(chat, ask("Should I look into this alarm?", context=CONTEXT))
    (offer,) = [e for e in events if e.type == "suggestion"]
    assert isinstance(offer, ChatSuggestionEvent)
    assert offer.trigger.model_dump() == {
        "kind": "run_alarm", "ref": f"{RUN_ID}:RA-1", "question": None,
    }  # fmt: skip
    assert offer.title == "Sensor relationships broke (SPE) on unit U-3 (RA-1)"
    assert ChatEvent.model_validate(offer.model_dump(mode="json")).root == offer
    reply = model.bodies("chat")[1]["messages"][-1]
    assert reply["role"] == "tool"
    assert "nothing has started" in reply["content"]
    final = model.bodies("chat")[2]["messages"][1]["content"]
    assert '"investigation_offered"' in final


@pytest.mark.parametrize(
    ("call", "reason"),
    [
        (suggest("run_alarm", f"{RUN_ID}:RA-9"), "has no alarm RA-9"),
        (suggest("run_alarm", "run_doesnotexist:RA-1"), "does not exist"),
        (suggest("unit", "77"), "77 is not in the evidence"),
        (suggest("alarm", "AL-77-spe"), "AL-77-spe is not in the evidence"),
        (suggest("lot", "not a lot"), "not a valid lot reference"),
        (("suggest_investigation", {"kind": "unit"}), "invalid arguments"),
    ],
)
async def test_an_offer_code_cannot_check_is_not_sent(
    respx_mock: respx.Router, call: tuple[str, dict[str, str]], reason: str
) -> None:
    model = ScriptedModel().mount(respx_mock)
    model.add("chat", tool_reply(call), text_reply("ok"), stream_reply("Nothing to offer."))
    chat, _ = answerer(FakeScience(runs=FakeRuns()))
    events = await collect(chat, ask("Investigate it?", context=CONTEXT))
    assert "suggestion" not in types(events)
    reply = model.bodies("chat")[1]["messages"][-1]["content"]
    assert "not offered" in reply
    assert reason in reply


async def test_an_item_from_the_evidence_can_be_offered_once(respx_mock: respx.Router) -> None:
    model = ScriptedModel().mount(respx_mock)
    model.add(
        "chat",
        tool_reply(("get_run_wafer", {"run_id": RUN_ID, "wafer_index": 0})),
        tool_reply(suggest("wafer", "lot47542-12"), suggest("lot", LOT)),
        text_reply("ok"),
        stream_reply("This wafer is a real WM-811K wafer."),
    )
    chat, _ = answerer(FakeScience(runs=FakeRuns()))
    events = await collect(chat, ask("What about this wafer?", context=CONTEXT))
    offers = [e for e in events if e.type == "suggestion"]
    assert [(o.trigger.kind, o.trigger.ref, o.title) for o in offers] == [
        ("wafer", "lot47542-12", "Wafer lot47542-12")
    ]
    second = model.bodies("chat")[2]["messages"][-1]["content"]
    assert "already offered" in second


async def test_without_a_run_the_run_tools_are_not_offered(respx_mock: respx.Router) -> None:
    model = ScriptedModel().mount(respx_mock)
    model.add(
        "chat",
        tool_reply(("get_run", {"run_id": RUN_ID})),
        text_reply("ok"),
        stream_reply("I cannot read runs here."),
    )
    chat, _ = answerer(FakeScience(runs=FakeRuns()))
    events = await collect(chat, ask("Summarise my run"))
    assert "citation" not in types(events)
    refusal = model.bodies("chat")[1]["messages"][-1]["content"]
    assert "unknown tool" in refusal


async def test_a_run_sees_every_secom_unit(respx_mock: respx.Router) -> None:
    model = ScriptedModel().mount(respx_mock)
    model.add(
        "chat",
        tool_reply(("get_unit", {"unit_id": REAL_UNIT})),
        text_reply("ok"),
        stream_reply("Read."),
    )
    secom = LineSecom()
    chat, _ = answerer(FakeScience(secom=secom, runs=FakeRuns()))
    await collect(chat, ask("And the real unit?", context=CONTEXT))
    assert secom.positions == [1566]  # the whole line, not the replay clock


def test_what_the_page_shows_may_be_repeated() -> None:
    context = ChatContext(run_id=RUN_ID, run_lot=LOT, run_unit=3, run_wafer=2, run_alarm="RA-1")
    facts = question_facts([], "Tell me more", context)
    assert {RUN_ID, LOT, "RA-1"} <= facts.strings
    assert LOT in facts.known_identifiers
    assert 3 in facts.ints["unit"]
    assert 2 in facts.ints["wafer_index"]
