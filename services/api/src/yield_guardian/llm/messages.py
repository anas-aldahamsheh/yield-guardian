"""Typed request side of an OpenAI-compatible chat completion.

These types describe what a caller *wants*; :mod:`yield_guardian.llm.request_builder` turns
them into the exact JSON body a given model accepts. Only parameters that AMD Token Factory
accepts are representable here (see ``docs/vendor/token-factory.md``): fields the gateway
silently drops (``stop``, ``seed``, ``logit_bias`` ...) or rejects (``thinking``,
``reasoning.enabled``) have no field, so they can never be sent by accident.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# One definition of the documented reasoning_effort values, shared with the API contracts.
from yield_guardian.contracts.models import ReasoningEffort as ReasoningEffort

ALL_REASONING_EFFORTS: frozenset[ReasoningEffort] = frozenset(
    ("none", "minimal", "low", "medium", "high", "xhigh", "max")
)

MessageRole = Literal["system", "developer", "user", "assistant", "tool"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TextPart(_Frozen):
    type: Literal["text"] = "text"
    text: str


class ImageUrl(_Frozen):
    url: Annotated[str, Field(min_length=1)]
    """A ``data:image/...;base64,`` URL or an ``https://`` URL."""


class ImagePart(_Frozen):
    type: Literal["image_url"] = "image_url"
    image_url: ImageUrl


ContentPart = Annotated[TextPart | ImagePart, Field(discriminator="type")]


class FunctionCall(_Frozen):
    name: str
    arguments: str
    """JSON text exactly as produced by the model; parse and validate before use."""


class ToolCall(_Frozen):
    id: str
    type: Literal["function"] = "function"
    function: FunctionCall


class ChatMessage(_Frozen):
    """One message of a conversation."""

    role: MessageRole
    content: str | list[ContentPart] | None = None
    tool_call_id: str | None = None
    tool_calls: tuple[ToolCall, ...] | None = None

    @model_validator(mode="after")
    def _check_shape(self) -> ChatMessage:
        if self.role == "tool":
            if not self.tool_call_id:
                raise ValueError("a tool message needs tool_call_id")
            if not isinstance(self.content, str):
                raise ValueError("a tool message carries its result as a string")
        elif self.tool_call_id is not None:
            raise ValueError("only tool messages carry tool_call_id")
        if self.tool_calls and self.role != "assistant":
            raise ValueError("only assistant messages carry tool_calls")
        if self.role in ("system", "developer", "user") and self.content is None:
            raise ValueError(f"a {self.role} message needs content")
        if self.role == "assistant" and self.content is None and not self.tool_calls:
            raise ValueError("an assistant message needs content or tool_calls")
        if (
            self.role in ("system", "developer")
            and isinstance(self.content, list)
            and any(isinstance(part, ImagePart) for part in self.content)
        ):
            raise ValueError("system and developer messages are text only")
        return self

    @classmethod
    def system(cls, text: str) -> ChatMessage:
        return cls(role="system", content=text)

    @classmethod
    def developer(cls, text: str) -> ChatMessage:
        return cls(role="developer", content=text)

    @classmethod
    def user(cls, content: str | list[ContentPart]) -> ChatMessage:
        return cls(role="user", content=content)

    @classmethod
    def assistant(
        cls, content: str | None = None, tool_calls: tuple[ToolCall, ...] | None = None
    ) -> ChatMessage:
        return cls(role="assistant", content=content, tool_calls=tool_calls or None)

    @classmethod
    def tool(cls, tool_call_id: str, content: str) -> ChatMessage:
        return cls(role="tool", tool_call_id=tool_call_id, content=content)

    def text(self) -> str:
        """The text of this message, with image parts left out."""
        if self.content is None:
            return ""
        if isinstance(self.content, str):
            return self.content
        return "\n\n".join(part.text for part in self.content if isinstance(part, TextPart))


class FunctionSpec(_Frozen):
    name: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
    description: str
    parameters: dict[str, Any]
    """JSON Schema of the arguments object."""


class ToolSpec(_Frozen):
    type: Literal["function"] = "function"
    function: FunctionSpec


class NamedFunction(_Frozen):
    name: str


class NamedToolChoice(_Frozen):
    type: Literal["function"] = "function"
    function: NamedFunction


ToolChoice = Literal["none", "auto", "required"] | NamedToolChoice


class JsonSchemaFormat(_Frozen):
    name: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
    schema_: dict[str, Any] = Field(alias="schema")
    strict: bool = True

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class ResponseFormat(_Frozen):
    type: Literal["text", "json_object", "json_schema"]
    json_schema: JsonSchemaFormat | None = None

    @model_validator(mode="after")
    def _check(self) -> ResponseFormat:
        if (self.type == "json_schema") != (self.json_schema is not None):
            raise ValueError("json_schema is required exactly when type is json_schema")
        return self

    @classmethod
    def json_object(cls) -> ResponseFormat:
        return cls(type="json_object")

    @classmethod
    def strict_schema(cls, name: str, schema: dict[str, Any]) -> ResponseFormat:
        return cls(
            type="json_schema",
            json_schema=JsonSchemaFormat(name=name, schema_=schema, strict=True),
        )


class ChatRequest(_Frozen):
    """What a caller asks for. ``max_tokens`` is required: thinking tokens count toward it,
    so every call has to size it deliberately."""

    messages: Annotated[tuple[ChatMessage, ...], Field(min_length=1)]
    max_tokens: Annotated[int, Field(ge=1)]
    tools: tuple[ToolSpec, ...] | None = None
    tool_choice: ToolChoice | None = None
    parallel_tool_calls: bool | None = None
    response_format: ResponseFormat | None = None
    temperature: Annotated[float, Field(ge=0.0, le=2.0)] | None = None
    top_p: Annotated[float, Field(gt=0.0, le=1.0)] | None = None
    presence_penalty: Annotated[float, Field(ge=-2.0, le=2.0)] | None = None
    frequency_penalty: Annotated[float, Field(ge=-2.0, le=2.0)] | None = None
    reasoning_effort: ReasoningEffort | None = None

    @model_validator(mode="after")
    def _check_tools(self) -> ChatRequest:
        if not self.tools and (
            self.tool_choice is not None or self.parallel_tool_calls is not None
        ):
            raise ValueError("tool_choice and parallel_tool_calls need tools")
        if self.tools:
            names = [tool.function.name for tool in self.tools]
            if len(names) != len(set(names)):
                raise ValueError("tool names must be unique")
            if isinstance(self.tool_choice, NamedToolChoice) and (
                self.tool_choice.function.name not in names
            ):
                raise ValueError("tool_choice names a tool that is not offered")
        return self
