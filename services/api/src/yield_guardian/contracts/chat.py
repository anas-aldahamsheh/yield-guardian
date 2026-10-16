"""Engineer chat: grounded questions about the plant data, answered as an SSE stream."""

from typing import Annotated, Literal

from pydantic import Field, JsonValue, RootModel, model_validator

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
from yield_guardian.contracts.investigation import Evidence, InvestigationTrigger, ToolName
from yield_guardian.contracts.models import CallUsage
from yield_guardian.contracts.runs import RunAlarmId, RunId, Station, UserLabel

RouteKind = Literal["deterministic", "model"]


class ChatMessage(Contract):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatContext(Contract):
    """What the engineer is looking at, so the model can resolve "this unit" or "this alarm".
    With `run_id` the chat may read that run with the run tools."""

    unit_id: UnitId | None = None
    sensor: SensorId | None = None
    wafer_id: WaferId | None = None
    lot: LotId | None = None
    investigation_id: InvestigationId | None = None
    run_id: RunId | None = None
    station: Station | None = Field(None, description="The station of the run being looked at.")
    run_unit: Count | None = Field(None, description="Position of a unit in the run input.")
    run_wafer: Count | None = Field(None, description="Position of a wafer in the run input.")
    run_lot: UserLabel | None = Field(None, description="A lot of the run, as named in its input.")
    run_alarm: RunAlarmId | None = Field(None, description="An alarm of the run.")
    page_content: str | None = Field(
        None,
        max_length=12000,
        description="Structured text of what is currently visible on the screen.",
    )

    @model_validator(mode="after")
    def _run_fields_need_a_run(self) -> "ChatContext":
        run_fields = (self.station, self.run_unit, self.run_wafer, self.run_lot, self.run_alarm)
        if self.run_id is None and any(v is not None for v in run_fields):
            raise ValueError("station, run_unit, run_wafer, run_lot and run_alarm need run_id")
        return self


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


class ChatSuggestionEvent(Contract):
    """An offer to start an investigation, proposed by the model and checked by code (the alarm
    or item exists in the run, the evidence or the page). The page shows a button; only the
    engineer's click starts it, with POST /investigations and this `trigger`."""

    type: Literal["suggestion"]
    action: Literal["start_investigation"]
    trigger: InvestigationTrigger
    title: str = Field(description="What would be investigated, written by code.")


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
            | ChatSuggestionEvent
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
    | ChatSuggestionEvent
    | ChatTokenEvent
    | ChatRefusalEvent
    | ChatDoneEvent
    | ChatErrorEvent
)
