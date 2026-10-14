from typing import Annotated

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from yield_guardian.api.deps import Line, get_registry
from yield_guardian.api.problems import problem_responses
from yield_guardian.contracts.line import AlarmKind, AlarmPage, AlarmStatus, LineState

router = APIRouter(tags=["line"])
ws_router = APIRouter()


@router.get("/line/state", operation_id="get_line_state", responses=problem_responses(503))
async def get_line_state(
    line: Line, window: Annotated[int, Query(ge=10, le=600)] = 120
) -> LineState:
    """Plant clock, the latest units, counts and open alarms. Live updates: WebSocket /ws/line."""
    return await line.state(window=window)


@router.get("/alarms", operation_id="list_alarms", responses=problem_responses(503))
async def list_alarms(
    line: Line,
    status: AlarmStatus | None = None,
    kind: AlarmKind | None = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> AlarmPage:
    return await line.list_alarms(status=status, kind=kind, cursor=cursor, limit=limit)


@ws_router.websocket("/ws/line")
async def line_socket(websocket: WebSocket) -> None:
    """Live line messages (schema LineEvent), JSON text frames, hello first."""
    registry = get_registry(websocket)  # type: ignore[arg-type]
    if registry.line is None:
        await websocket.close(code=1013, reason="Line replay not available")
        return
    await websocket.accept()
    try:
        async for message in registry.line.stream():
            await websocket.send_text(message.model_dump_json())
    except WebSocketDisconnect:
        return
