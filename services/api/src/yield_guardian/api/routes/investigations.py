from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Header, Path, Query, status
from sse_starlette import EventSourceResponse

from yield_guardian.api.deps import EngineerSession, Investigations, LiveInvestigator, Registry
from yield_guardian.api.problems import problem_responses
from yield_guardian.contracts.investigation import (
    DecisionCreate,
    Evidence,
    Investigation,
    InvestigationCreate,
    InvestigationPage,
    InvestigationStatus,
)
from yield_guardian.services.investigations import check_run_alarm

router = APIRouter(tags=["investigations"])

InvestigationPath = Annotated[str, Path(pattern=r"^inv_[0-9a-z]{8,40}$")]

SSE_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Server-sent events. `event` is the event type, `id` its `seq`, `data` the JSON event.",
        "content": {
            "text/event-stream": {"schema": {"$ref": "#/components/schemas/InvestigationEvent"}}
        },
    }
}


@router.post(
    "/investigations",
    operation_id="create_investigation",
    status_code=status.HTTP_202_ACCEPTED,
    responses=problem_responses(400, 401, 403, 404, 503),
)
async def create_investigation(
    session: EngineerSession,
    body: InvestigationCreate,
    store: Investigations,
    registry: Registry,
    _investigator: LiveInvestigator,
) -> Investigation:
    """Start a live investigation. Follow it on GET /investigations/{id}/events.

    A `run_alarm` trigger (`<run_id>:<alarm_id>`) needs the run and its alarm (404 otherwise)."""
    # Without an investigator, LiveInvestigator answers 503 not_ready before any run exists.
    title = None
    if body.trigger.kind == "run_alarm":
        title = await check_run_alarm(registry.run_reader, body.trigger)
    return await store.create(body.trigger, session=session, title=title)


@router.get("/investigations", operation_id="list_investigations", responses=problem_responses(503))
async def list_investigations(
    store: Investigations,
    status: InvestigationStatus | None = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> InvestigationPage:
    """Investigations, newest first, recorded runs included."""
    return await store.list(status=status, cursor=cursor, limit=limit)


@router.get(
    "/investigations/{investigation_id}",
    operation_id="get_investigation",
    responses=problem_responses(404, 503),
)
async def get_investigation(
    store: Investigations, investigation_id: InvestigationPath
) -> Investigation:
    return await store.get(investigation_id)


@router.get(
    "/investigations/{investigation_id}/events",
    operation_id="stream_investigation_events",
    response_model=None,
    responses={**SSE_RESPONSE, **problem_responses(404, 503)},
)
async def stream_investigation_events(
    store: Investigations,
    investigation_id: InvestigationPath,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> EventSourceResponse:
    """Stored events after Last-Event-ID, then live ones; the stream closes after the `end` event."""
    await store.get(investigation_id)
    after = int(last_event_id) if last_event_id and last_event_id.isdigit() else None

    async def events() -> AsyncIterator[dict[str, str]]:
        async for event in store.events(investigation_id, after_seq=after):
            yield {"event": event.type, "id": str(event.seq), "data": event.model_dump_json()}

    return EventSourceResponse(events(), ping=15)


@router.post(
    "/investigations/{investigation_id}/decision",
    operation_id="decide_investigation",
    responses=problem_responses(401, 403, 404, 409, 503),
)
async def decide_investigation(
    session: EngineerSession,
    body: DecisionCreate,
    store: Investigations,
    investigation_id: InvestigationPath,
) -> Investigation:
    """Approve (opens a work order) or reject the report. Only when status is awaiting_decision."""
    return await store.decide(investigation_id, body, session=session)


@router.get(
    "/investigations/{investigation_id}/evidence/{evidence_id}",
    operation_id="get_evidence",
    responses=problem_responses(404, 503),
)
async def get_evidence(
    store: Investigations,
    investigation_id: InvestigationPath,
    evidence_id: Annotated[str, Path(pattern=r"^E\d+$")],
) -> Evidence:
    return await store.get_evidence(investigation_id, evidence_id)
