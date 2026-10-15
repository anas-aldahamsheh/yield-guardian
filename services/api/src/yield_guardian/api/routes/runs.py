"""Live runs and uploads (PLAN_V2 §3.3). No sign-in is needed to run."""

from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Header, Path, Response, UploadFile, status
from sse_starlette import EventSourceResponse

from yield_guardian.api.deps import Runs, Uploads
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
from yield_guardian.live.tabular import MAX_BYTES
from yield_guardian.live.uploads import MEDIA_TYPES, DownloadFile, FileFormat, template

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
    responses=problem_responses(400, 404, 410, 503),
)
async def create_run(body: RunCreate, runs: Runs) -> RunCreated:
    """Materialise the input and start computing every stage now. Follow it on `events_url`."""
    return await runs.create(body.root)


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
async def get_run(runs: Runs, run_id: RunPath) -> Run:
    """The run's full state: every stage with its result and every listed alarm."""
    return await runs.get(run_id)


@router.get(
    "/runs/{run_id}/units/{index}/chart",
    operation_id="get_run_unit_chart",
    tags=["runs"],
    responses=problem_responses(404, 410, 503),
)
async def get_run_unit_chart(
    runs: Runs, run_id: RunPath, index: Annotated[int, Path(ge=0, le=100_000)]
) -> UnitChartResult:
    """One unit's control-chart result with `z` (every monitored sensor's standardised
    reading); the run and its events carry `z` for the first 200 units only."""
    return await runs.unit_chart(run_id, index)


@router.get(
    "/runs/{run_id}/events",
    operation_id="stream_run_events",
    tags=["runs"],
    response_model=None,
    responses={**SSE_RESPONSE, **problem_responses(404, 410, 503)},
)
async def stream_run_events(
    runs: Runs,
    run_id: RunPath,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> EventSourceResponse:
    """Stored events after Last-Event-ID, then live ones; the stream closes after `run_done`."""
    await runs.get(run_id)
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
    responses=problem_responses(413, 422, 503),
)
async def create_upload(
    uploads: Uploads,
    file: Annotated[UploadFile, File(description="The CSV or XLSX file.")],
    kind: Annotated[
        UploadKind | None,
        Form(description="sensors or wafers; read from the header row when omitted."),
    ] = None,
) -> UploadSummary:
    """Parse and validate a sensor or wafer file and keep it for 24 h. What is wrong inside the
    file comes back as issues (errors block the run); only an unreadable file is refused."""
    data = await file.read(MAX_BYTES + 1)
    return await uploads.upload(data, file.filename, kind)


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
