"""Report writer (PLAN 7.4): one structured report from the evidence, revised on request.

The writer role answers with the :class:`~yield_guardian.contracts.investigation.Report`
contract in ``json_object`` mode, validated by Pydantic in code. No model on the live endpoint
is known to accept strict ``json_schema`` (MiMo-V2.6-Flash refused it with HTTP 400 on
2026-10-14), so the system message carries the report's JSON Schema itself. The writer sees
the evidence only through :func:`~yield_guardian.agent.tools.model_view`, as data.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from yield_guardian.agent.prompts import REVISION_NOTE, WRITER_SYSTEM, data_message
from yield_guardian.agent.tools import model_view
from yield_guardian.contracts.investigation import (
    Evidence,
    InvestigationTrigger,
    Report,
    VerificationIssue,
)
from yield_guardian.llm.gateway import CallOptions, LlmGateway, Structured
from yield_guardian.llm.messages import ChatMessage, ChatRequest
from yield_guardian.llm.registry import Role
from yield_guardian.llm.structured import strict_json_schema

WRITER_MAX_TOKENS = 16384
"""Room for a thinking model's reasoning and the report: Qwen3.8-27B (it cannot turn thinking
off; "low" is its lowest effort) used all of 4096 on reasoning in the first live run."""
REPORT_SCHEMA_NAME = "investigation_report"
REPORT_SCHEMA_TEXT = json.dumps(strict_json_schema(Report), separators=(",", ":"))
TEXT_NUMBER_NOTE = (
    "Where a number's path may point: cite a numeric field when the evidence has one. When a "
    'number appears only inside a text value (such as a label "5% false-alarm rate"), give that '
    "text's path; the number must appear in it exactly as you write it. A number the tool was "
    'asked for (such as a window bound) is cited as "/arguments/<name>". A count of items (such '
    "as 15 sensors in a group) gives the path of the list; code checks its length. A level such "
    'as "the 99% control limit" is a name, not a quantity: do not list it in "numbers", and '
    "never give the limit's value as the level."
)
"""Kept here, not in prompts.py, while the chat prompts there are being rewritten. Each case
matches a rule of the verifier (text leaves, ``/arguments/`` paths, list lengths, levels)."""
WRITER_INSTRUCTIONS = f"{WRITER_SYSTEM}\n\n{TEXT_NUMBER_NOTE}"
"""The writer's system message: the rules and an example with every key. The JSON Schema is not
sent (about 800 tokens); code validates the report against it and sends a broken one back."""
QUIET_NOTE = "Nothing notable in this evidence; its data is left out. Do not cite numbers from it."


def _quiet(evidence: Evidence) -> bool:
    """Evidence with nothing notable: every sensor healthy, a control-chart window without a
    warning or alarm, a search or similarity lookup that found nothing. Anything else, or
    anything not sure, is sent in full."""
    data: Any = evidence.model_dump(mode="json")["data"]
    if not isinstance(data, dict):
        return False
    if evidence.tool == "get_sensor_health":
        sensors = data.get("sensors") or []
        return bool(sensors) and all(s.get("status") == "ok" for s in sensors)
    if evidence.tool == "get_fdc_window":
        points = data.get("points") or []
        return bool(points) and not any(
            p.get("fdc_alarm") in ("warning", "alarm")
            or p.get("ewma_alarm")
            or p.get("cusum_alarm")
            for p in points
        )
    if evidence.tool == "search_knowledge":
        return not data.get("hits")
    if evidence.tool == "get_similar_wafers":
        return not data.get("results")
    return False


def writer_view(evidence: Evidence) -> dict[str, Any]:
    """What the writer is shown of one piece of evidence: :func:`model_view`, or for evidence
    with nothing notable only its ID, tool, arguments and one-line summary."""
    if not _quiet(evidence):
        return model_view(evidence)
    return {
        "evidence_id": evidence.evidence_id,
        "tool": evidence.tool,
        "arguments": evidence.arguments,
        "summary": evidence.summary,
        "data": QUIET_NOTE,
    }


@dataclass(frozen=True, slots=True)
class WriterInput:
    trigger: InvestigationTrigger
    evidence: Sequence[Evidence]
    previous: Report | None = None
    issues: Sequence[VerificationIssue] = ()


def writer_request(data: WriterInput, *, max_tokens: int = WRITER_MAX_TOKENS) -> ChatRequest:
    payload: dict[str, object] = {
        "trigger": data.trigger.model_dump(mode="json"),
        "evidence": [writer_view(item) for item in data.evidence],
    }
    if data.previous is not None:
        payload["task"] = REVISION_NOTE
        payload["previous_report"] = data.previous.model_dump(mode="json")
        payload["problems"] = [
            {"location": i.location, "code": i.code, "message": i.message} for i in data.issues
        ]
    return ChatRequest(
        messages=(ChatMessage.system(WRITER_INSTRUCTIONS), ChatMessage.user(data_message(payload))),
        max_tokens=max_tokens,
    )


class ReportWriter:
    def __init__(self, gateway: LlmGateway, *, max_tokens: int = WRITER_MAX_TOKENS) -> None:
        self.gateway = gateway
        self.max_tokens = max_tokens

    async def write(self, data: WriterInput, *, options: CallOptions) -> Structured[Report]:
        return await self.gateway.complete_structured(
            Role.WRITER,
            writer_request(data, max_tokens=self.max_tokens),
            Report,
            schema_name=REPORT_SCHEMA_NAME,
            options=options,
        )
