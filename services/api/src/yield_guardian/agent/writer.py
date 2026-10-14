"""Report writer (PLAN 7.4): one structured report from the evidence, revised on request.

The writer role answers with the :class:`~yield_guardian.contracts.investigation.Report`
contract: strict ``json_schema`` on MiMo-V2.6-Flash (the only model documented to accept it),
``json_object`` plus Pydantic validation on any fallback. The writer sees the evidence only
through :func:`~yield_guardian.agent.tools.model_view`, as data.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

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

WRITER_MAX_TOKENS = 16384
"""Room for a thinking model's reasoning and the report: Qwen3.8-27B (it cannot turn thinking
off; "low" is its lowest effort) used all of 4096 on reasoning in the first live run."""
REPORT_SCHEMA_NAME = "investigation_report"


@dataclass(frozen=True, slots=True)
class WriterInput:
    trigger: InvestigationTrigger
    evidence: Sequence[Evidence]
    previous: Report | None = None
    issues: Sequence[VerificationIssue] = ()


def writer_request(data: WriterInput, *, max_tokens: int = WRITER_MAX_TOKENS) -> ChatRequest:
    payload: dict[str, object] = {
        "trigger": data.trigger.model_dump(mode="json"),
        "evidence": [model_view(item) for item in data.evidence],
    }
    if data.previous is not None:
        payload["task"] = REVISION_NOTE
        payload["previous_report"] = data.previous.model_dump(mode="json")
        payload["problems"] = [
            {"location": i.location, "code": i.code, "message": i.message} for i in data.issues
        ]
    return ChatRequest(
        messages=(ChatMessage.system(WRITER_SYSTEM), ChatMessage.user(data_message(payload))),
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
