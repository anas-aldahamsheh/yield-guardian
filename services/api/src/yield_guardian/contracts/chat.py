"""Engineer chat: grounded questions about the plant data, answered as an SSE stream."""

from typing import Annotated, Literal

from pydantic import Field, JsonValue, RootModel

from yield_guardian.contracts.base import (
    Contract,
    Count,
    InvestigationId,
    LotId,
    Problem,
    SensorId,
    UnitId,
    WaferId,
)
from yield_guardian.contracts.investigation import Evidence, ToolName
from yield_guardian.contracts.models import CallUsage

RouteKind = Literal["deterministic", "model"]


class ChatMessage(Contract):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatContext(Contract):
    """What the engineer is looking at; helps the router resolve "this unit" or "this wafer"."""

    unit_id: UnitId | None = None
    sensor: SensorId | None = None
    wafer_id: WaferId | None = None
    lot: LotId | None = None
    investigation_id: InvestigationId | None = None


class ChatRequest(Contract):
    messages: list[ChatMessage] = Field(min_length=1, max_length=20)
    context: ChatContext | None = None


class ChatRouteEvent(Contract):
    type: Literal["route"]
    route: RouteKind
    intent: str
    model_id: str | None


class ChatToolEvent(Contract):
    type: Literal["tool"]
    tool: ToolName
    arguments: dict[str, JsonValue]


class ChatCitationEvent(Contract):
    type: Literal["citation"]
    evidence: Evidence


class ChatTokenEvent(Contract):
    type: Literal["token"]
    text: str


class ChatRefusalEvent(Contract):
    """The question is outside the plant data, or asks the assistant to act."""

    type: Literal["refusal"]
    reason: str


class ChatDoneEvent(Contract):
    type: Literal["done"]
    usage: CallUsage | None
    numbers_checked: Count
    numbers_unverified: list[str] = Field(
        description="Numbers in the answer not found in any cited evidence."
    )


class ChatErrorEvent(Contract):
    type: Literal["error"]
    problem: Problem


class ChatEvent(
    RootModel[
        Annotated[
            ChatRouteEvent
            | ChatToolEvent
            | ChatCitationEvent
            | ChatTokenEvent
            | ChatRefusalEvent
            | ChatDoneEvent
            | ChatErrorEvent,
            Field(discriminator="type"),
        ]
    ]
):
    """An event on POST /chat (SSE: `event` is the type)."""


ChatEventPayload = (
    ChatRouteEvent
    | ChatToolEvent
    | ChatCitationEvent
    | ChatTokenEvent
    | ChatRefusalEvent
    | ChatDoneEvent
    | ChatErrorEvent
)
