from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter
from sse_starlette import EventSourceResponse

from yield_guardian.api.deps import Chat, EngineerSession
from yield_guardian.api.problems import problem_responses
from yield_guardian.contracts.chat import ChatRequest

router = APIRouter(tags=["chat"])

SSE_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Server-sent events. `event` is the event type, `data` the JSON event.",
        "content": {"text/event-stream": {"schema": {"$ref": "#/components/schemas/ChatEvent"}}},
    }
}


@router.post(
    "/chat",
    operation_id="chat",
    response_model=None,
    responses={**SSE_RESPONSE, **problem_responses(401, 403, 429, 503)},
)
async def chat(session: EngineerSession, body: ChatRequest, responder: Chat) -> EventSourceResponse:
    """Ask about the plant data. Answers cite evidence; numbers are checked against it."""

    async def events() -> AsyncIterator[dict[str, str]]:
        async for event in responder.answer(body, session=session.info()):
            yield {"event": event.type, "data": event.model_dump_json()}

    return EventSourceResponse(events(), ping=15)
