"""Typed response side: parsing completions and accumulating streamed chunks.

Documented response facts (``docs/vendor/token-factory.md``): thinking text arrives in
``choices[0].message.reasoning``, its token count in
``usage.completion_tokens_details.reasoning_tokens`` (absent for Qwen3.8-27B), and a low
``max_tokens`` can leave ``content`` empty with ``finish_reason: "length"``. vLLM servers name
the thinking field ``reasoning_content``; it is accepted as an alias so the same client works
against a fab's own vLLM endpoint.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from yield_guardian.llm.errors import ResponseShapeError
from yield_guardian.llm.messages import FunctionCall, ToolCall
from yield_guardian.llm.profiles import Usage


class ChatResult(BaseModel):
    """One completed chat call (or a cache hit standing in for one)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str
    """The model the request was built for (the server's echo is kept in ``served_model``)."""
    served_model: str | None = None
    response_id: str | None = None
    content: str | None = None
    reasoning: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    finish_reason: str | None = None
    usage: Usage | None = None
    points: float | None = None
    latency_ms: float = 0.0
    attempts: int = 1
    cache_hit: bool = False
    cache_key: str | None = None
    adjustments: tuple[str, ...] = ()
    rate_limit_headers: dict[str, str] = Field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not (self.content and self.content.strip()) and not self.tool_calls

    @property
    def truncated(self) -> bool:
        return self.finish_reason == "length"


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def parse_usage(payload: object) -> Usage | None:
    """Parse ``usage``; any missing count stays None (the gateway may omit usage)."""
    if not isinstance(payload, Mapping):
        return None
    completion_details = payload.get("completion_tokens_details")
    prompt_details = payload.get("prompt_tokens_details")
    reasoning = (
        _int_or_none(completion_details.get("reasoning_tokens"))
        if isinstance(completion_details, Mapping)
        else None
    )
    cached = (
        _int_or_none(prompt_details.get("cached_tokens"))
        if isinstance(prompt_details, Mapping)
        else None
    )
    usage = Usage(
        prompt_tokens=_int_or_none(payload.get("prompt_tokens")),
        completion_tokens=_int_or_none(payload.get("completion_tokens")),
        total_tokens=_int_or_none(payload.get("total_tokens")),
        reasoning_tokens=reasoning,
        cached_tokens=cached,
    )
    if usage == Usage():
        return None
    return usage


def _text_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _reasoning_of(obj: Mapping[str, Any]) -> str | None:
    return _text_or_none(obj.get("reasoning")) or _text_or_none(obj.get("reasoning_content"))


def _arguments_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _parse_tool_calls(value: object) -> tuple[ToolCall, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ResponseShapeError("tool_calls is not a list")
    calls: list[ToolCall] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ResponseShapeError(f"tool_calls[{index}] is not an object")
        function = item.get("function")
        if not isinstance(function, Mapping) or not isinstance(function.get("name"), str):
            raise ResponseShapeError(f"tool_calls[{index}] has no function name")
        call_id = item.get("id")
        calls.append(
            ToolCall(
                id=call_id if isinstance(call_id, str) and call_id else f"call_{index}",
                function=FunctionCall(
                    name=function["name"], arguments=_arguments_text(function.get("arguments"))
                ),
            )
        )
    return tuple(calls)


class ParsedCompletion(BaseModel):
    model_config = ConfigDict(frozen=True)

    served_model: str | None
    response_id: str | None
    content: str | None
    reasoning: str | None
    tool_calls: tuple[ToolCall, ...]
    finish_reason: str | None
    usage: Usage | None


def parse_chat_completion(payload: object) -> ParsedCompletion:
    """Parse a non-streaming ``chat.completion`` body."""
    if not isinstance(payload, Mapping):
        raise ResponseShapeError("completion body is not a JSON object")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
        raise ResponseShapeError("completion has no choices")
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, Mapping):
        raise ResponseShapeError("choices[0] has no message")
    return ParsedCompletion(
        served_model=_text_or_none(payload.get("model")),
        response_id=_text_or_none(payload.get("id")),
        content=_text_or_none(message.get("content")),
        reasoning=_reasoning_of(message),
        tool_calls=_parse_tool_calls(message.get("tool_calls")),
        finish_reason=_text_or_none(choice.get("finish_reason")),
        usage=parse_usage(payload.get("usage")),
    )


StreamEventType = Literal["content", "reasoning", "tool_call", "finish", "usage"]


class StreamDelta(BaseModel):
    """One meaningful piece of a streamed completion."""

    model_config = ConfigDict(frozen=True)

    type: StreamEventType
    text: str | None = None
    tool_index: int | None = None
    finish_reason: str | None = None
    usage: Usage | None = None


class _PartialCall:
    __slots__ = ("arguments", "id", "name")

    def __init__(self) -> None:
        self.id: str | None = None
        self.name: str | None = None
        self.arguments: list[str] = []


class StreamAccumulator:
    """Folds ``chat.completion.chunk`` objects into deltas and a final :class:`ParsedCompletion`.

    Usage is taken from whichever chunk carries it (the gateway drops ``stream_options``,
    so it may never come; then usage stays None and points are unknown).
    """

    def __init__(self) -> None:
        self._content: list[str] = []
        self._reasoning: list[str] = []
        self._calls: dict[int, _PartialCall] = {}
        self.finish_reason: str | None = None
        self.usage: Usage | None = None
        self.served_model: str | None = None
        self.response_id: str | None = None

    def feed(self, chunk: object) -> list[StreamDelta]:
        if not isinstance(chunk, Mapping):
            raise ResponseShapeError("stream chunk is not a JSON object")
        self.served_model = self.served_model or _text_or_none(chunk.get("model"))
        self.response_id = self.response_id or _text_or_none(chunk.get("id"))
        out: list[StreamDelta] = []
        usage = parse_usage(chunk.get("usage"))
        choices = chunk.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], Mapping):
            choice = choices[0]
            delta = choice.get("delta")
            if isinstance(delta, Mapping):
                reasoning = _reasoning_of(delta)
                if reasoning:
                    self._reasoning.append(reasoning)
                    out.append(StreamDelta(type="reasoning", text=reasoning))
                content = _text_or_none(delta.get("content"))
                if content:
                    self._content.append(content)
                    out.append(StreamDelta(type="content", text=content))
                out.extend(self._feed_tool_calls(delta.get("tool_calls")))
            finish = _text_or_none(choice.get("finish_reason"))
            if finish:
                self.finish_reason = finish
                out.append(StreamDelta(type="finish", finish_reason=finish))
        if usage is not None:
            self.usage = usage
            out.append(StreamDelta(type="usage", usage=usage))
        return out

    def _feed_tool_calls(self, value: object) -> list[StreamDelta]:
        if not isinstance(value, list):
            return []
        out: list[StreamDelta] = []
        for position, item in enumerate(value):
            if not isinstance(item, Mapping):
                raise ResponseShapeError("streamed tool call is not an object")
            raw_index = item.get("index", position)
            index = raw_index if isinstance(raw_index, int) else position
            partial = self._calls.setdefault(index, _PartialCall())
            call_id = item.get("id")
            if isinstance(call_id, str) and call_id:
                partial.id = call_id
            function = item.get("function")
            if isinstance(function, Mapping):
                name = function.get("name")
                if isinstance(name, str) and name:
                    partial.name = name
                fragment = function.get("arguments")
                if fragment is not None:
                    partial.arguments.append(_arguments_text(fragment))
            out.append(StreamDelta(type="tool_call", tool_index=index))
        return out

    def result(self) -> ParsedCompletion:
        calls: list[ToolCall] = []
        for index in sorted(self._calls):
            partial = self._calls[index]
            if partial.name is None:
                raise ResponseShapeError(f"streamed tool call {index} never received a name")
            calls.append(
                ToolCall(
                    id=partial.id or f"call_{index}",
                    function=FunctionCall(name=partial.name, arguments="".join(partial.arguments)),
                )
            )
        return ParsedCompletion(
            served_model=self.served_model,
            response_id=self.response_id,
            content="".join(self._content) if self._content else None,
            reasoning="".join(self._reasoning) if self._reasoning else None,
            tool_calls=tuple(calls),
            finish_reason=self.finish_reason,
            usage=self.usage,
        )
