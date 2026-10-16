from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Header, Path, Query, Response, status
from sse_starlette import EventSourceResponse

from yield_guardian.api.deps import (
    CurrentSession,
    EngineerSession,
    Investigations,
    LiveInvestigator,
    Registry,
)
from yield_guardian.api.problems import ProblemError, problem_responses
from yield_guardian.contracts.investigation import (
    DecisionCreate,
    Evidence,
    Investigation,
    InvestigationCreate,
    InvestigationPage,
    InvestigationStatus,
    ModelCallTrace,
)
from yield_guardian.services.access import viewing
from yield_guardian.services.investigations import check_run_alarm
from yield_guardian.services.run_export import report_markdown

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
    """Start a live investigation of this workspace. Follow it on GET /investigations/{id}/events.

    A `run_alarm` trigger (`<run_id>:<alarm_id>`) needs a run this workspace may open and its
    alarm (404 otherwise)."""
    # Without an investigator, LiveInvestigator answers 503 not_ready before any run exists.
    title = None
    if body.trigger.kind == "run_alarm":
        with viewing(session.viewer):
            title = await check_run_alarm(registry.run_reader, body.trigger)
    return await store.create(body.trigger, session=session, title=title)


@router.get("/investigations", operation_id="list_investigations", responses=problem_responses(503))
async def list_investigations(
    store: Investigations,
    session: CurrentSession,
    status: InvestigationStatus | None = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> InvestigationPage:
    """This workspace's investigations, newest first (none without a session), and apart from
    them, on the first page, the product's examples: recorded runs every visitor sees."""
    return await store.list(status=status, cursor=cursor, limit=limit, viewer=session.viewer)


@router.get(
    "/investigations/{investigation_id}",
    operation_id="get_investigation",
    responses=problem_responses(404, 503),
)
async def get_investigation(
    store: Investigations, session: CurrentSession, investigation_id: InvestigationPath
) -> Investigation:
    """Another workspace's investigation answers 404, as a missing one does."""
    return await store.get(investigation_id, session.viewer)


@router.get(
    "/investigations/{investigation_id}/events",
    operation_id="stream_investigation_events",
    response_model=None,
    responses={**SSE_RESPONSE, **problem_responses(404, 503)},
)
async def stream_investigation_events(
    store: Investigations,
    session: CurrentSession,
    investigation_id: InvestigationPath,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> EventSourceResponse:
    """Stored events after Last-Event-ID, then live ones; the stream closes after the `end` event."""
    await store.get(investigation_id, session.viewer)
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
    """Approve (opens a work order) or reject the report. Only when status is awaiting_decision;
    the product's example (a recorded run) is read-only (403)."""
    return await store.decide(investigation_id, body, session=session)


@router.post(
    "/investigations/{investigation_id}/stop",
    operation_id="stop_investigation",
    responses=problem_responses(401, 403, 404, 409, 503),
)
async def stop_investigation(
    session: EngineerSession, store: Investigations, investigation_id: InvestigationPath
) -> Investigation:
    """Stop a queued or running investigation: no further model calls are made, its evidence so
    far is kept, no report is written, and it ends as `failed` with the reason "Stopped by the
    user". 409 once it has finished (or awaits a decision); the product's example is read-only
    (403); another workspace's investigation answers 404, as a missing one does."""
    return await store.stop(investigation_id, session=session)


@router.get(
    "/investigations/{investigation_id}/calls",
    operation_id="list_investigation_calls",
    responses=problem_responses(404, 503),
)
async def list_investigation_calls(
    store: Investigations, session: CurrentSession, investigation_id: InvestigationPath
) -> list[ModelCallTrace]:
    """Every model call of the investigation, oldest first, with a masked, truncated copy of
    what was sent and what came back. Another workspace's investigation answers 404."""
    return await store.calls(investigation_id, session.viewer)


@router.get(
    "/investigations/{investigation_id}/evidence/{evidence_id}",
    operation_id="get_evidence",
    responses=problem_responses(404, 503),
)
async def get_evidence(
    store: Investigations,
    session: CurrentSession,
    investigation_id: InvestigationPath,
    evidence_id: Annotated[str, Path(pattern=r"^E\d+$")],
) -> Evidence:
    return await store.get_evidence(investigation_id, evidence_id, session.viewer)


@router.get(
    "/investigations/{investigation_id}/report.md",
    operation_id="get_investigation_report",
    response_class=Response,
    responses={
        200: {
            "description": "The report as Markdown, as an attachment.",
            "content": {"text/markdown": {"schema": {"type": "string"}}},
        },
        **problem_responses(404, 409, 503),
    },
)
async def get_investigation_report(
    store: Investigations, session: CurrentSession, investigation_id: InvestigationPath
) -> Response:
    """The report with the evidence each finding cites, the hypotheses, the checks and the
    decision; 409 until the report is written."""
    investigation = await store.get(investigation_id, session.viewer)
    if investigation.report is None:
        raise ProblemError(
            409, "conflict", "No report yet", "The report is not written yet; try again later."
        )
    return Response(
        content=report_markdown(investigation).encode(),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{investigation_id}-report.md"'},
    )
