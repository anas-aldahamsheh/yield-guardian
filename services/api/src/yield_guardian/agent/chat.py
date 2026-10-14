"""Engineer chat (PLAN 7.5): grounded answers about the plant data, streamed as events.

Every reply is written by the chat model; no answer, refusal or capability text is written in
advance by code (the owner's rule: the product's intelligence is the model's).

1. **Gather evidence**: the chat model, told what the product is and given every read-only
   tool, chooses which tools to call (at most eight calls in four rounds), or none.
2. **Answer**: the chat model writes the reply from the evidence, streamed sentence by sentence.
   Code still checks each sentence before it is sent (PLAN rule 4): every number or identifier
   the evidence does not hold is replaced by a marker and listed in ``done.numbers_unverified``.
   That check never writes text of its own.

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
from yield_guardian.agent.grounding import (
    REDACTED,
    REDACTED_IDENTIFIER,
    EvidenceFacts,
    check_text,
)
from yield_guardian.agent.numbers import NumberMention, scan
from yield_guardian.agent.prompts import CHAT_SYSTEM, data_message
from yield_guardian.agent.tools import (
    TOOLS,
    EvidenceLedger,
    ToolExecutor,
    ToolOutcome,
    model_view,
    tool_specs,
)
from yield_guardian.contracts.base import Problem
from yield_guardian.contracts.chat import (
    ChatCitationEvent,
    ChatContext,
    ChatDoneEvent,
    ChatErrorEvent,
    ChatEventPayload,
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

CHAT_MAX_TOKENS = 2000
"""Room for a full answer: Arabic takes several tokens per word, and 700 cut answers short."""
TOOL_ROUND_MAX_TOKENS = 1024
MAX_MODEL_TOOL_CALLS = 8
MAX_TOOL_ROUNDS = 4
HISTORY_MESSAGES = 10
PRODUCT_NAMES = frozenset({"WM-811K"})
"""Names in the system prompt that contain digits; the model may write them, they are not data."""
SYSTEM = CHAT_SYSTEM.format(
    tools="\n".join(f"- {name}: {tool.description}" for name, tool in TOOLS.items())
)
"""The chat system prompt with every tool listed, so the model knows all it can look up. Static,
so the provider can reuse its prompt cache."""
_BOUNDARY = re.compile(r"(?<=[.!?:;])\s+|\n+")
_LIST_MARKER = re.compile(r"^\s*(?:[-*•]\s*)?\d{1,2}[.)](?=\s|$)")
"""A numbered-list marker at the start of a line ("1." or "2)"): layout, not a quantity."""
MAX_SUM_TERMS = 400
"""Distinct whole numbers in the evidence up to which a sum of two of them is checked."""


def _is_sum_of_two(mention: NumberMention, facts: EvidenceFacts) -> bool:
    """A whole number that is the sum of two whole numbers in the evidence (116 dead and 57 in
    maintenance make 173). Only exact integer sums count, so a rounded or invented total does
    not pass."""
    if mention.percent or mention.decimals or mention.comparator is not None:
        return False
    if mention.value != int(mention.value):
        return False
    whole = {int(v) for v in facts.numbers if v == int(v) and v >= 0}
    if len(whole) > MAX_SUM_TERMS:
        return False
    target = int(mention.value)
    return any(target - a in whole and target - a != a for a in whole) or (
        target % 2 == 0 and target // 2 in whole and facts.numbers.count(target // 2) > 1
    )


class SentenceGate:
    """Holds streamed text until a sentence is complete, then checks it against the evidence."""

    def __init__(self, facts: EvidenceFacts) -> None:
        self.facts = facts
        self.buffer = ""
        self.numbers_checked = 0
        self.unverified: list[str] = []

    def _check(self, sentence: str) -> str:
        marker = _LIST_MARKER.match(sentence)
        head, body = (
            (sentence[: marker.end()], sentence[marker.end() :]) if marker else ("", sentence)
        )
        check = check_text(body, self.facts)
        unverified = [n for n in check.unverified if not _is_sum_of_two(n, self.facts)]
        self.numbers_checked += len(check.numbers)
        self.unverified.extend(n.text for n in unverified)
        spans: dict[tuple[int, int], str] = {(n.start, n.end): REDACTED for n in unverified}
        for identifier, _ in check.unsupported_identifiers:
            spans[(identifier.start, identifier.end)] = REDACTED_IDENTIFIER
        for (start, end), text in sorted(spans.items(), reverse=True):
            body = body[:start] + text + body[end:]
        return head + body

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
    strings.extend(PRODUCT_NAMES)
    facts = EvidenceFacts.build(evidence, strings=strings, units=units)
    for mention in found.numbers:
        facts.numbers.append(mention.value / 100 if mention.percent else mention.value)
    facts.known_identifiers.update(s for s in strings if "-" in s or s.startswith("lot"))
    facts.known_identifiers.update(PRODUCT_NAMES)
    return facts


def _sum[N: (int, float)](values: Sequence[N | None]) -> N | None:
    """A total, or null when any part is unknown (a partial sum would understate it)."""
    known = [v for v in values if v is not None]
    return None if len(known) < len(values) else sum(known[1:], known[0])


def total_usage(records: Sequence[LlmCallRecord]) -> CallUsage | None:
    """All model calls of one answer, summed, named after the call that wrote the answer; a
    count stays null when any call did not report it."""
    used = [r for r in records if r.sent or r.cache_hit]
    if not used:
        return None
    parts = [to_call_usage(r) for r in used]
    last = parts[-1]
    return CallUsage(
        role=last.role,
        model_id=last.model_id,
        tokens_in=_sum([p.tokens_in for p in parts]),
        tokens_out=_sum([p.tokens_out for p in parts]),
        tokens_reasoning=_sum([p.tokens_reasoning for p in parts]),
        points=_sum([p.points for p in parts]),
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

        await self.route_log.record("model", "general", self.wall_clock())
        yield ChatRouteEvent(type="route", route="model", intent="general", model_id=None)

        ledger = EvidenceLedger(None)
        executor = ToolExecutor(self.services, ledger, wall_clock=self.wall_clock)
        outcomes: list[ToolOutcome] = []
        async for event in self._model_tools(
            question, history, request.context, executor, outcomes, options
        ):
            yield event

        evidence = ledger.items
        failed = [f"{o.title}: {o.error}" for o in outcomes if o.evidence is None and o.error]
        gate = SentenceGate(question_facts(evidence, question, request.context))
        final = LlmChatRequest(
            messages=(
                ChatMessage.system(SYSTEM),
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
        """Let the chat model choose read-only tools: at most eight calls in four rounds."""
        messages: list[ChatMessage] = [
            ChatMessage.system(SYSTEM),
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
