"""Size guard for request bodies: an upload above the limit is refused with 413 before it is
read, by its Content-Length, or as soon as a body without one grows past the limit."""

from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from yield_guardian.api.problems import problem_response
from yield_guardian.contracts.base import Problem


def _detail(file_bytes: int) -> str:
    return f"The file is larger than {file_bytes // 1_048_576} MB. Split it into smaller files."


class BodyLimit:
    """ASGI middleware: request bodies on `paths` may hold at most `max_bytes`. The refusal names
    `file_bytes`, the limit on the file itself (the body also carries its multipart framing)."""

    def __init__(
        self, app: ASGIApp, *, paths: tuple[str, ...], max_bytes: int, file_bytes: int
    ) -> None:
        self.app = app
        self.paths = paths
        self.max_bytes = max_bytes
        self.file_bytes = file_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] not in self.paths:
            await self.app(scope, receive, send)
            return
        length = dict(scope["headers"]).get(b"content-length", b"")
        if length.isdigit() and int(length) > self.max_bytes:
            response = problem_response(
                Problem(
                    title="Request too large",
                    status=413,
                    detail=_detail(self.file_bytes),
                    code="bad_request",
                    instance=scope["path"],
                )
            )
            await response(scope, receive, send)
            return
        received = 0

        async def counted() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    # FastAPI passes an HTTPException raised while reading the body through.
                    raise HTTPException(413, _detail(self.file_bytes))
            return message

        await self.app(scope, counted, send)
