"""Live runs and uploads (PLAN_V2 §3.3). No sign-in is needed to run; with a session, a run or
upload belongs to that session's workspace, and any other session gets exactly what a missing ID
gets on every route below, the event stream included (services.access)."""

from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Header, Path, Response, UploadFile, status
from sse_starlette import EventSourceResponse

from yield_guardian.api.deps import CurrentSession, RunOwner, Runs, Uploads
from yield_guardian.api.problems import problem_responses
from yield_guardian.contracts.runs import (
    DrawLayoutList,
    Run,
    RunCaseList,
    RunCreate,
    RunCreated,
    UnitChartResult,
    UploadKind,
    UploadSummary,
)
from yield_guardian.contracts.workspace import RunComparison
from yield_guardian.live.tabular import MAX_BYTES
from yield_guardian.live.uploads import MEDIA_TYPES, DownloadFile, FileFormat, template
from yield_guardian.services.run_export import compare, results_csv

router = APIRouter()

RunPath = Annotated[str, Path(pattern=r"^run_[0-9a-z]{8,40}$")]

SSE_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Server-sent events. `event` is the event type, `id` its `seq`, `data` the "
        "JSON event.",
        "content": {"text/event-stream": {"schema": {"$ref": "#/components/schemas/RunEvent"}}},
    }
}
FILE_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "The file, as an attachment.",
        "content": {
            MEDIA_TYPES["csv"].split(";")[0]: {"schema": {"type": "string"}},
            MEDIA_TYPES["xlsx"]: {"schema": {"type": "string", "format": "binary"}},
        },
    }
}


@router.post(
    "/runs",
    operation_id="create_run",
    status_code=status.HTTP_201_CREATED,
    tags=["runs"],
    responses=problem_responses(400, 403, 404, 410, 503),
)
async def create_run(body: RunCreate, runs: Runs, owner: RunOwner) -> RunCreated:
    """Materialise the input and start computing every stage now. Follow it on `events_url`.
    With a session, the run is recorded in its workspace ("Your work")."""
    return await runs.create(body.root, owner=owner.workspace_id if owner else None)


@router.post(
    "/runs/{run_id}/again",
    operation_id="repeat_run",
    status_code=status.HTTP_201_CREATED,
    tags=["runs"],
    responses=problem_responses(403, 404, 410, 422, 503),
)
async def repeat_run(runs: Runs, owner: RunOwner, run_id: RunPath) -> RunCreated:
    """A new run of exactly the same input items; the earlier run is kept as it is."""
    return await runs.again(run_id, owner=owner.workspace_id if owner else None)


@router.get(
    "/runs/cases", operation_id="list_run_cases", tags=["runs"], responses=problem_responses(503)
)
async def list_run_cases(runs: Runs) -> RunCaseList:
    """Real situations found in the data by fixed rules over live computations."""
    return await runs.list_cases()


@router.get(
    "/runs/layouts",
    operation_id="list_draw_layouts",
    tags=["runs"],
    responses=problem_responses(503),
)
async def list_draw_layouts(runs: Runs) -> DrawLayoutList:
    """Real WM-811K die layouts to draw a defect on (every die starts as pass)."""
    return await runs.layouts()


@router.get(
    "/runs/{run_id}",
    operation_id="get_run",
    tags=["runs"],
    responses=problem_responses(404, 410, 503),
)
async def get_run(runs: Runs, session: CurrentSession, run_id: RunPath) -> Run:
    """The run's full state: every stage with its result and every listed alarm. Another
    workspace's run answers 404, as a missing one does."""
    return await runs.get(run_id, session.viewer)


@router.get(
    "/runs/{run_id}/compare/{other_id}",
    operation_id="compare_runs",
    tags=["runs"],
    responses=problem_responses(404, 410, 503),
)
async def compare_runs(
    runs: Runs, session: CurrentSession, run_id: RunPath, other_id: RunPath
) -> RunComparison:
    """Two runs side by side: each stage's status and alarms, the units and wafers flagged, and
    what changed from the first to the second."""
    first, second, same = await runs.compare(run_id, other_id, session.viewer)
    return compare(first, second, same_input=same)


@router.get(
    "/runs/{run_id}/results.csv",
    operation_id="get_run_results",
    tags=["runs"],
    response_class=Response,
    responses={
        200: {
            "description": "One row per sensor unit, wafer and alarm (column `record`).",
            "content": {"text/csv": {"schema": {"type": "string"}}},
        },
        **problem_responses(404, 410, 503),
    },
)
async def get_run_results(runs: Runs, session: CurrentSession, run_id: RunPath) -> Response:
    """The run's computed results as CSV: risk, T², SPE and chart level per unit, pattern and
    unknown flag per wafer, and every listed alarm."""
    run = await runs.get(run_id, session.viewer)
    return Response(
        content=results_csv(run),
        media_type=MEDIA_TYPES["csv"],
        headers={"Content-Disposition": f'attachment; filename="{run_id}-results.csv"'},
    )


@router.get(
    "/runs/{run_id}/units/{index}/chart",
    operation_id="get_run_unit_chart",
    tags=["runs"],
    responses=problem_responses(404, 410, 503),
)
async def get_run_unit_chart(
    runs: Runs,
    session: CurrentSession,
    run_id: RunPath,
    index: Annotated[int, Path(ge=0, le=100_000)],
) -> UnitChartResult:
    """One unit's control-chart result with `z` (every monitored sensor's standardised
    reading); the run and its events carry `z` for the first 200 units only."""
    return await runs.unit_chart(run_id, index, session.viewer)


@router.get(
    "/runs/{run_id}/events",
    operation_id="stream_run_events",
    tags=["runs"],
    response_model=None,
    responses={**SSE_RESPONSE, **problem_responses(404, 410, 503)},
)
async def stream_run_events(
    runs: Runs,
    session: CurrentSession,
    run_id: RunPath,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> EventSourceResponse:
    """Stored events after Last-Event-ID, then live ones; the stream closes after `run_done`."""
    await runs.get(run_id, session.viewer)
    after = int(last_event_id) if last_event_id and last_event_id.isdigit() else None

    async def events() -> AsyncIterator[dict[str, str]]:
        async for event in runs.events(run_id, after_seq=after):
            yield {"event": event.type, "id": str(event.seq), "data": event.model_dump_json()}

    return EventSourceResponse(events(), ping=15)


@router.post(
    "/uploads",
    operation_id="create_upload",
    status_code=status.HTTP_201_CREATED,
    tags=["uploads"],
    responses=problem_responses(403, 413, 422, 503),
)
async def create_upload(
    uploads: Uploads,
    owner: RunOwner,
    file: Annotated[UploadFile, File(description="The CSV or XLSX file.")],
    kind: Annotated[
        UploadKind | None,
        Form(description="sensors or wafers; read from the header row when omitted."),
    ] = None,
) -> UploadSummary:
    """Parse and validate a sensor or wafer file and keep it, in this workspace, as long as the
    workspace (24 h without a session). What is wrong inside the file comes back as issues
    (errors block the run); only an unreadable file is refused."""
    data = await file.read(MAX_BYTES + 1)
    return await uploads.upload(
        data, file.filename, kind, owner=owner.workspace_id if owner else None
    )


def _download(found: DownloadFile) -> Response:
    return Response(
        content=found.content,
        media_type=found.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{found.filename}"',
            **found.headers,
        },
    )


@router.get(
    "/uploads/templates/{kind}.{fmt}",
    operation_id="get_upload_template",
    tags=["uploads"],
    response_class=Response,
    responses=FILE_RESPONSE,
)
async def get_upload_template(kind: UploadKind, fmt: FileFormat) -> Response:
    """The header row only, ready to fill in."""
    return _download(template(kind, fmt))


@router.get(
    "/uploads/examples/{kind}.{fmt}",
    operation_id="get_upload_example",
    tags=["uploads"],
    response_class=Response,
    responses={**FILE_RESPONSE, **problem_responses(503)},
)
async def get_upload_example(uploads: Uploads, kind: UploadKind, fmt: FileFormat) -> Response:
    """Real data in the upload format: real SECOM units the risk model never saw, or every die
    of one real WM-811K demo lot. The source and licence ride in `X-Data-Attribution` and a
    `Link` header (rel cite-as); a workbook also has an About sheet."""
    return _download(await uploads.example(kind, fmt))
