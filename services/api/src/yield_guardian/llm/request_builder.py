"""Build the exact JSON body of a chat completion from a :class:`ChatRequest` and a profile.

The builder enforces the profile so that invalid combinations are never sent:

* ``developer`` messages become ``system`` where the model rejects the developer role (GLM);
* system messages are merged into one first message where the model requires it (Qwen);
* a ``reasoning_effort`` the model does not accept is refused before sending;
* image parts are stripped for text-only models (and the strip is recorded);
* strict ``json_schema`` is refused on models that do not support it;
* tool messages must answer a tool call of the preceding assistant message.

Only accepted parameters are emitted, and never ``stream_options`` (the gateway drops it).
Every change made to the caller's messages is listed in :attr:`BuiltRequest.adjustments`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from yield_guardian.llm.errors import ProfileViolationError
from yield_guardian.llm.messages import (
    ChatMessage,
    ChatRequest,
    ImagePart,
    NamedToolChoice,
    TextPart,
)
from yield_guardian.llm.profiles import (
    DeveloperRole,
    ModelProfile,
    ReasoningControl,
    SystemRule,
    efforts_text,
)

IMAGE_REMOVED_NOTE = "[image removed: this model does not accept image input]"


@dataclass(frozen=True, slots=True)
class BuiltRequest:
    model: str
    body: dict[str, Any]
    adjustments: tuple[str, ...]
    stripped_images: int


def _check_reasoning(profile: ModelProfile, request: ChatRequest) -> None:
    effort = request.reasoning_effort
    if effort is None:
        return
    if profile.reasoning_control is ReasoningControl.NOT_APPLICABLE:
        raise ProfileViolationError(
            profile.id,
            "reasoning_effort",
            f"reasoning_effort is not applicable to this model (got {effort!r})",
        )
    if effort not in profile.reasoning_efforts:
        raise ProfileViolationError(
            profile.id,
            "reasoning_effort",
            f"reasoning_effort {effort!r} is not accepted; accepted: "
            f"{efforts_text(profile.reasoning_efforts)}",
        )


def _check_capabilities(profile: ModelProfile, request: ChatRequest) -> None:
    if not profile.is_chat:
        raise ProfileViolationError(profile.id, "kind", f"{profile.kind} model, not a chat model")
    fmt = request.response_format
    if fmt is not None:
        if fmt.type == "json_schema" and not profile.supports_json_schema:
            raise ProfileViolationError(
                profile.id, "json_schema", "strict json_schema is not supported by this model"
            )
        if fmt.type == "json_object" and not profile.supports_json_object:
            raise ProfileViolationError(profile.id, "json_object", "json_object is not supported")
    if request.tools and not profile.supports_tools:
        raise ProfileViolationError(profile.id, "tools", "tool calling is not supported")
    if profile.context_length is not None and request.max_tokens > profile.context_length:
        raise ProfileViolationError(
            profile.id,
            "max_tokens",
            f"max_tokens {request.max_tokens} exceeds the context window {profile.context_length}",
        )


def _map_developer(
    profile: ModelProfile, messages: list[ChatMessage], notes: list[str]
) -> list[ChatMessage]:
    if profile.developer_role is DeveloperRole.ACCEPTED:
        return messages
    mapped = 0
    out: list[ChatMessage] = []
    for message in messages:
        if message.role == "developer":
            out.append(ChatMessage(role="system", content=message.text()))
            mapped += 1
        else:
            out.append(message)
    if mapped:
        notes.append(f"mapped {mapped} developer message(s) to system")
    return out


def _strip_images(
    profile: ModelProfile, messages: list[ChatMessage], notes: list[str]
) -> tuple[list[ChatMessage], int]:
    if profile.accepts_images:
        return messages, 0
    stripped = 0
    out: list[ChatMessage] = []
    for message in messages:
        if isinstance(message.content, list) and any(
            isinstance(part, ImagePart) for part in message.content
        ):
            texts = [part for part in message.content if isinstance(part, TextPart)]
            stripped += len(message.content) - len(texts)
            parts: list[TextPart] = [*texts, TextPart(text=IMAGE_REMOVED_NOTE)]
            out.append(message.model_copy(update={"content": parts}))
        else:
            out.append(message)
    if stripped:
        notes.append(f"stripped {stripped} image part(s): the model is text-only")
    return out, stripped


def _apply_system_rule(
    profile: ModelProfile, messages: list[ChatMessage], notes: list[str]
) -> list[ChatMessage]:
    if profile.system_rule is SystemRule.ANY:
        return messages
    system = [m for m in messages if m.role == "system"]
    rest = [m for m in messages if m.role != "system"]
    if not system:
        if profile.system_rule is SystemRule.EXACTLY_ONE_FIRST:
            raise ProfileViolationError(
                profile.id, "system_message", "exactly one system message, first, is required"
            )
        return messages
    already_fine = len(system) == 1 and messages[0].role == "system"
    if already_fine:
        return messages
    merged = ChatMessage(role="system", content="\n\n".join(m.text() for m in system))
    notes.append(f"merged {len(system)} system message(s) into one first message")
    return [merged, *rest]


def _check_tool_links(profile: ModelProfile, messages: list[ChatMessage]) -> None:
    pending: set[str] = set()
    for index, message in enumerate(messages):
        if message.role == "tool":
            if message.tool_call_id not in pending:
                raise ProfileViolationError(
                    profile.id,
                    "tool_message",
                    f"message {index} answers tool call {message.tool_call_id!r}, which the "
                    "preceding assistant message did not make (or was already answered)",
                )
            pending.discard(message.tool_call_id)
            continue
        if pending:
            raise ProfileViolationError(
                profile.id,
                "tool_message",
                f"tool call(s) {sorted(pending)} were not answered before message {index}",
            )
        if message.role == "assistant" and message.tool_calls:
            ids = [call.id for call in message.tool_calls]
            if len(ids) != len(set(ids)):
                raise ProfileViolationError(profile.id, "tool_message", "duplicate tool call ids")
            pending = set(ids)


def _content_json(message: ChatMessage) -> str | list[dict[str, Any]] | None:
    content = message.content
    if content is None or isinstance(content, str):
        return content
    if all(isinstance(part, TextPart) for part in content):
        return message.text()
    return [part.model_dump(mode="json") for part in content]


def _message_json(message: ChatMessage) -> dict[str, Any]:
    out: dict[str, Any] = {"role": message.role}
    if message.role == "tool":
        out["tool_call_id"] = message.tool_call_id
        out["content"] = message.content
        return out
    out["content"] = _content_json(message)
    if message.tool_calls:
        out["tool_calls"] = [call.model_dump(mode="json") for call in message.tool_calls]
    return out


def build_chat_request(
    profile: ModelProfile, request: ChatRequest, *, stream: bool = False
) -> BuiltRequest:
    """Return the body to POST to ``/chat/completions``, or raise :class:`ProfileViolationError`."""
    _check_capabilities(profile, request)
    _check_reasoning(profile, request)
    if stream and not profile.supports_streaming:
        raise ProfileViolationError(profile.id, "stream", "streaming is not supported")

    notes: list[str] = []
    messages = list(request.messages)
    messages = _map_developer(profile, messages, notes)
    messages, stripped = _strip_images(profile, messages, notes)
    messages = _apply_system_rule(profile, messages, notes)
    _check_tool_links(profile, messages)

    body: dict[str, Any] = {
        "model": profile.id,
        "messages": [_message_json(m) for m in messages],
        "max_tokens": request.max_tokens,
    }
    for name in ("temperature", "top_p", "presence_penalty", "frequency_penalty"):
        value = getattr(request, name)
        if value is not None:
            body[name] = value
    if request.tools:
        body["tools"] = [tool.model_dump(mode="json") for tool in request.tools]
        if request.tool_choice is not None:
            body["tool_choice"] = (
                request.tool_choice.model_dump(mode="json")
                if isinstance(request.tool_choice, NamedToolChoice)
                else request.tool_choice
            )
        if request.parallel_tool_calls is not None:
            body["parallel_tool_calls"] = request.parallel_tool_calls
    fmt = request.response_format
    if fmt is not None and fmt.type != "text":
        body["response_format"] = fmt.model_dump(mode="json", by_alias=True, exclude_none=True)
    if request.reasoning_effort is not None:
        body["reasoning_effort"] = request.reasoning_effort
    if stream:
        body["stream"] = True
    return BuiltRequest(
        model=profile.id, body=body, adjustments=tuple(notes), stripped_images=stripped
    )
