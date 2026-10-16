from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from sse_starlette import EventSourceResponse

from yield_guardian.api.deps import Chat, EngineerSession, Registry
from yield_guardian.api.problems import problem_responses
from yield_guardian.contracts.chat import ChatContext, ChatRequest
from yield_guardian.services.access import Viewer, viewing
from yield_guardian.services.registry import ServiceRegistry
from yield_guardian.services.runs import missing

router = APIRouter(tags=["chat"])

SSE_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Server-sent events. `event` is the event type, `data` the JSON event.",
        "content": {"text/event-stream": {"schema": {"$ref": "#/components/schemas/ChatEvent"}}},
    }
}


async def _check_context(registry: ServiceRegistry, viewer: Viewer, context: ChatContext) -> None:
    """The run and the investigation the question is about must be ones this workspace may open:
    another workspace's answer what a missing one does, before any model is asked."""
    if context.run_id is not None and registry.run_reader is not None:
        with viewing(viewer):
            if await registry.run_reader.get_run(context.run_id) is None:
                raise missing("Run", context.run_id, now=datetime.now(UTC))
    if context.investigation_id is not None and registry.investigations is not None:
        await registry.investigations.get(context.investigation_id, viewer)


@router.post(
    "/chat",
    operation_id="chat",
    response_model=None,
    responses={**SSE_RESPONSE, **problem_responses(401, 403, 404, 410, 503)},
)
async def chat(
    session: EngineerSession, body: ChatRequest, responder: Chat, registry: Registry
) -> EventSourceResponse:
    """Ask about the plant data. Answers cite evidence; numbers are checked against it. The
    tools read for this workspace only: a run or investigation in the context must be its own
    (or of no workspace), else 404 as for a missing one."""
    if body.context is not None:
        await _check_context(registry, session.viewer, body.context)

    async def events() -> AsyncIterator[dict[str, str]]:
        with viewing(session.viewer):
            async for event in responder.answer(body, session=session.info()):
                yield {"event": event.type, "data": event.model_dump_json()}

    return EventSourceResponse(events(), ping=15)
