"""Engineer chat (PLAN 7.5): grounded answers about the plant data, streamed as events.

1. **Route** (:mod:`yield_guardian.agent.router`): rules first, the router model only when the
   rules cannot decide. Requests for actions and attempts to change the rules are refused.
2. **Gather evidence**: the tool calls the route names, made by code; when the route names none
   (an open question), the chat model chooses read-only tools, at most four calls.
3. **Answer**: count questions are answered by code alone. Otherwise the chat model writes the
   answer from the evidence, streamed sentence by sentence: each sentence is checked by code
   before it is sent, and every number or identifier the evidence does not hold is replaced by
   a marker and listed in ``done.numbers_unverified``. Causal wording gets a code-written note.

The engineer's conversation reaches the model only as data inside one user message; a browser
cannot forge an assistant or system turn.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable, Sequence
from datetime import UTC, datetime
from typing import Any

import structlog

from yield_guardian.agent.graph import llm_problem
from yield_guardian.agent.grounding import EvidenceFacts, redact_unverified
from yield_guardian.agent.numbers import scan
from yield_guardian.agent.prompts import CHAT_SYSTEM, data_message
from yield_guardian.agent.router import ChatRouter, Route
from yield_guardian.agent.tools import (
    EvidenceLedger,
    ToolExecutor,
    ToolOutcome,
    model_view,
    tool_specs,
)
from yield_guardian.agent.wording import causal_phrases
from yield_guardian.contracts.base import Problem
from yield_guardian.contracts.chat import (
    ChatCitationEvent,
    ChatContext,
    ChatDoneEvent,
    ChatErrorEvent,
    ChatEventPayload,
    ChatRefusalEvent,
    ChatRequest,
    ChatRouteEvent,
    ChatTokenEvent,
    ChatToolEvent,
)
from yield_guardian.contracts.investigation import Evidence
from yield_guardian.contracts.models import CallUsage
from yield_guardian.contracts.services import ScienceServices
from yield_guardian.contracts.session import SessionInfo
from yield_guardian.llm.admin import RouteLog
from yield_guardian.llm.calllog import LlmCallRecord, to_call_usage
from yield_guardian.llm.errors import LlmError
from yield_guardian.llm.gateway import CallOptions, LlmGateway
from yield_guardian.llm.messages import ChatMessage
from yield_guardian.llm.messages import ChatRequest as LlmChatRequest
from yield_guardian.llm.registry import Role
from yield_guardian.llm.results import ChatResult, StreamDelta

log = structlog.get_logger(__name__)

CHAT_MAX_TOKENS = 700
TOOL_ROUND_MAX_TOKENS = 1024
MAX_MODEL_TOOL_CALLS = 4
MAX_TOOL_ROUNDS = 3
HISTORY_MESSAGES = 10
CAUSAL_NOTE = " (Note: the data shows statistical association, not cause.)"
_BOUNDARY = re.compile(r"(?<=[.!?:;])\s+|\n+")


class SentenceGate:
    """Holds streamed text until a sentence is complete, then checks it against the evidence."""

    def __init__(self, facts: EvidenceFacts) -> None:
        self.facts = facts
        self.buffer = ""
        self.numbers_checked = 0
        self.unverified: list[str] = []
        self.causal = False

    def _check(self, sentence: str) -> str:
        shown, check = redact_unverified(sentence, self.facts)
        self.numbers_checked += len(check.numbers)
        self.unverified.extend(n.text for n in check.unverified)
        if causal_phrases(sentence):
            self.causal = True
        return shown

    def feed(self, text: str) -> list[str]:
        self.buffer += text
        out: list[str] = []
        while match := _BOUNDARY.search(self.buffer):
            sentence, self.buffer = self.buffer[: match.end()], self.buffer[match.end() :]
            out.append(self._check(sentence))
        return out

    def flush(self) -> list[str]:
        if not self.buffer:
            return []
        rest, self.buffer = self.buffer, ""
        return [self._check(rest)]


def question_facts(
    evidence: Sequence[Evidence], question: str, context: ChatContext | None
) -> EvidenceFacts:
    """What an answer may mention: the evidence, plus what the engineer wrote or is looking at
    (an answer may repeat the question's own numbers and identifiers)."""
    strings: list[str] = []
    units: list[int] = []
    found = scan(question)
    for identifier in found.identifiers:
        if identifier.kind == "unit":
            units.extend(int(v) for v in identifier.values)
        else:
            strings.extend(identifier.values)
    if context is not None:
        strings.extend(v for v in (context.sensor, context.wafer_id, context.lot) if v)
        if context.unit_id is not None:
            units.append(context.unit_id)
    facts = EvidenceFacts.build(evidence, strings=strings, units=units)
    for mention in found.numbers:
        facts.numbers.append(mention.value / 100 if mention.percent else mention.value)
    facts.known_identifiers.update(s for s in strings if "-" in s or s.startswith("lot"))
    return facts


def count_answer(route: Route, outcomes: Sequence[ToolOutcome]) -> str | None:
    """The whole answer to a count question, written by code from the evidence."""
    found = [o for o in outcomes if o.evidence is not None]
    if not found:
        errors = "; ".join(o.error or "no result" for o in outcomes) or "no lookup was made"
        return f"I could not read the data for this question ({errors})."
    item = found[0].evidence
    assert item is not None
    data: dict[str, Any] = item.data
    ref = f"[{item.evidence_id}]"
    if route.count == "sensors_by_status":
        counts = data.get("counts", {})
        parts = [f"{counts.get(s)} sensors have the status {s}" for s in route.entities.statuses]
        return "; ".join(parts) + f" {ref}."
    if route.count == "significant_groups":
        return (
            f"{data.get('significant_groups')} sensor groups are significantly associated with "
            f"failure, covering {data.get('sensors_in_significant_groups')} of "
            f"{data.get('sensors_total')} sensors {ref}."
        )
    if route.count == "wafers_in_lot":
        wafers = data.get("wafers") or []
        return f"Lot {data.get('lot')} has {len(wafers)} wafers in the data {ref}."
    return None


def total_usage(records: Sequence[LlmCallRecord]) -> CallUsage | None:
    """All model calls of one answer, summed, named after the call that wrote the answer."""
    used = [r for r in records if r.sent or r.cache_hit]
    if not used:
        return None
    parts = [to_call_usage(r) for r in used]
    last = parts[-1]
    return CallUsage(
        role=last.role,
        model_id=last.model_id,
        tokens_in=sum(p.tokens_in for p in parts),
        tokens_out=sum(p.tokens_out for p in parts),
        tokens_reasoning=sum(p.tokens_reasoning for p in parts),
        points=sum(p.points for p in parts),
        latency_ms=sum(p.latency_ms for p in parts),
        cached=all(p.cached for p in parts),
    )


def _bad_request(detail: str) -> ChatErrorEvent:
    problem = Problem(title="Invalid question", status=400, detail=detail, code="bad_request")
    return ChatErrorEvent(type="error", problem=problem)


def _payload(
    question: str,
    history: Sequence[dict[str, str]],
    context: ChatContext | None,
    evidence: Sequence[Evidence],
    failed: Sequence[str],
) -> dict[str, Any]:
    payload: dict[str, Any] = {"question": question}
    if history:
        payload["conversation"] = list(history)
    if context is not None:
        payload["looking_at"] = context.model_dump(mode="json", exclude_none=True)
    payload["evidence"] = [model_view(e) for e in evidence]
    if failed:
        payload["failed_lookups"] = list(failed)
    return payload


class ChatAnswerer:
    """Implements :class:`~yield_guardian.contracts.services.ChatResponder`."""

    def __init__(
        self,
        *,
        gateway: LlmGateway,
        services: ScienceServices,
        route_log: RouteLog,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.gateway = gateway
        self.services = services
        self.route_log = route_log
        self.router = ChatRouter(gateway)
        self.wall_clock = wall_clock

    async def answer(
        self, request: ChatRequest, *, session: SessionInfo
    ) -> AsyncIterator[ChatEventPayload]:
        try:
            async for event in self._answer(request):
                yield event
        except LlmError as exc:
            yield ChatErrorEvent(type="error", problem=llm_problem(exc))
        except Exception as exc:
            log.exception("chat_failed")
            problem = Problem(
                title="Chat failed",
                status=500,
                detail=f"an internal error stopped the answer ({type(exc).__name__})",
                code="internal_error",
            )
            yield ChatErrorEvent(type="error", problem=problem)

    async def _answer(self, request: ChatRequest) -> AsyncIterator[ChatEventPayload]:
        if request.messages[-1].role != "user":
            yield _bad_request("the last message must be the engineer's question")
            return
        question = request.messages[-1].content
        history = [
            {"role": m.role, "content": m.content}
            for m in request.messages[:-1][-HISTORY_MESSAGES:]
        ]
        records: list[LlmCallRecord] = []
        options = CallOptions(on_record=records.append)

        route = await self.router.route(question, request.context, options=options)
        await self.route_log.record(route.kind, route.intent, self.wall_clock())
        yield ChatRouteEvent(
            type="route", route=route.kind, intent=route.intent, model_id=route.model_id
        )
        if route.refused:
            yield ChatRefusalEvent(type="refusal", reason=route.reason)
            return

        ledger = EvidenceLedger(None)
        executor = ToolExecutor(self.services, ledger, wall_clock=self.wall_clock)
        outcomes: list[ToolOutcome] = []
        for tool, arguments in route.calls:
            prepared = executor.prepare(tool, arguments)
            yield ChatToolEvent(type="tool", tool=tool, arguments=prepared.arguments or arguments)
            outcome = await executor.run(prepared)
            outcomes.append(outcome)
            if outcome.status == "new" and outcome.evidence is not None:
                yield ChatCitationEvent(type="citation", evidence=outcome.evidence)

        if route.count is not None:
            text = count_answer(route, outcomes)
            if text is not None:
                yield ChatTokenEvent(type="token", text=text)
                yield ChatDoneEvent(
                    type="done",
                    usage=total_usage(records),
                    numbers_checked=len(scan(text).numbers),
                    numbers_unverified=[],
                )
                return

        if not route.calls:
            async for event in self._model_tools(
                question, history, request.context, executor, outcomes, options
            ):
                yield event

        evidence = ledger.items
        failed = [f"{o.title}: {o.error}" for o in outcomes if o.evidence is None and o.error]
        gate = SentenceGate(question_facts(evidence, question, request.context))
        final = LlmChatRequest(
            messages=(
                ChatMessage.system(CHAT_SYSTEM),
                ChatMessage.user(
                    data_message(_payload(question, history, request.context, evidence, failed))
                ),
            ),
            max_tokens=CHAT_MAX_TOKENS,
        )
        async for item in self.gateway.stream(Role.CHAT, final, options=options):
            if isinstance(item, StreamDelta) and item.type == "content" and item.text:
                for piece in gate.feed(item.text):
                    yield ChatTokenEvent(type="token", text=piece)
        for piece in gate.flush():
            yield ChatTokenEvent(type="token", text=piece)
        if gate.causal:
            yield ChatTokenEvent(type="token", text=CAUSAL_NOTE)
        yield ChatDoneEvent(
            type="done",
            usage=total_usage(records),
            numbers_checked=gate.numbers_checked,
            numbers_unverified=gate.unverified,
        )

    async def _model_tools(
        self,
        question: str,
        history: Sequence[dict[str, str]],
        context: ChatContext | None,
        executor: ToolExecutor,
        outcomes: list[ToolOutcome],
        options: CallOptions,
    ) -> AsyncIterator[ChatEventPayload]:
        """Let the chat model choose read-only tools; at most four calls in three rounds."""
        messages: list[ChatMessage] = [
            ChatMessage.system(CHAT_SYSTEM),
            ChatMessage.user(data_message(_payload(question, history, context, [], []))),
        ]
        used = 0
        for _ in range(MAX_TOOL_ROUNDS):
            if used >= MAX_MODEL_TOOL_CALLS:
                return
            request = LlmChatRequest(
                messages=tuple(messages),
                max_tokens=TOOL_ROUND_MAX_TOKENS,
                tools=tool_specs(),
                tool_choice="auto",
            )
            result: ChatResult = await self.gateway.complete(Role.CHAT, request, options=options)
            if not result.tool_calls:
                return
            messages.append(ChatMessage.assistant(result.content or None, result.tool_calls))
            for call in result.tool_calls:
                if used >= MAX_MODEL_TOOL_CALLS:
                    refusal = '{"error":"not run: the limit of tool calls for one answer is reached"}'  # fmt: skip
                    messages.append(ChatMessage.tool(call.id or "call", refusal))
                    continue
                used += 1
                prepared = executor.prepare(call.function.name, call.function.arguments)
                if prepared.tool is not None and prepared.arguments is not None:
                    yield ChatToolEvent(
                        type="tool", tool=prepared.tool.name, arguments=prepared.arguments
                    )
                outcome = await executor.run(prepared)
                outcomes.append(outcome)
                if outcome.status == "new" and outcome.evidence is not None:
                    yield ChatCitationEvent(type="citation", evidence=outcome.evidence)
                messages.append(ChatMessage.tool(call.id or "call", outcome.message_for_model()))
