"""Recorded HTTP exchanges ("cassettes") that stand in for Token Factory in tests.

Replay is the default: a :class:`CassettePlayer` serves the recorded responses in order and
fails loudly when a request does not match the next recorded one (method, path, and any
body fields the cassette pins). Tests mount it on a respx route, so no request leaves the
process.

Record mode needs both ``YG_LLM_CASSETTE_MODE=record`` and ``TOKEN_FACTORY_API_KEY``; it wraps
a real transport in :class:`RecordingTransport`, which saves each exchange with the
``Authorization`` header removed. It spends the team's shared quota, so it is never run in
CI and only with the lead's go-ahead.

Cassettes written by hand from the documented shapes carry ``"hand_authored": true`` in
their metadata (see ``tests/fixtures/llm/README.md``); a recorded cassette carries the
recording time instead.
"""

from __future__ import annotations

import json
import os
from collections import deque
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from yield_guardian.llm.errors import CassetteError

MODE_VARIABLE = "YG_LLM_CASSETTE_MODE"
KEY_VARIABLE = "TOKEN_FACTORY_API_KEY"
CassetteMode = Literal["replay", "record"]

_REDACTED_HEADERS = frozenset({"authorization", "cookie", "set-cookie", "x-api-key"})


class CassetteMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hand_authored: bool
    description: str
    source: str = Field(description="Where the shapes come from (a document or a live run).")
    recorded_at: datetime | None = None


class RecordedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: str
    path: str = Field(description="Path suffix the request URL must end with.")
    match: dict[str, Any] = Field(
        default_factory=dict,
        description="Top-level JSON body fields the request must carry with these values.",
    )


class RecordedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: int
    headers: dict[str, str] = Field(default_factory=dict)
    json_body: Any = None
    text: str | None = None
    sse: list[str] | None = Field(
        default=None, description="Data payloads of server-sent events, sent in order."
    )
    chunk_size: int | None = Field(
        default=None, ge=1, description="Split the body into chunks of this many bytes."
    )

    @model_validator(mode="after")
    def _one_body(self) -> RecordedResponse:
        bodies = [self.json_body is not None, self.text is not None, self.sse is not None]
        if sum(bodies) > 1:
            raise ValueError("a response has at most one of json_body, text and sse")
        return self

    def body_bytes(self) -> bytes:
        if self.sse is not None:
            return "".join(f"data: {data}\n\n" for data in self.sse).encode("utf-8")
        if self.text is not None:
            return self.text.encode("utf-8")
        if self.json_body is not None:
            return json.dumps(self.json_body, ensure_ascii=False).encode("utf-8")
        return b""

    def content_type(self) -> str:
        if self.sse is not None:
            return "text/event-stream"
        if self.json_body is not None:
            return "application/json"
        return "text/plain; charset=utf-8"


class Interaction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: RecordedRequest
    response: RecordedResponse
    note: str | None = None


class Cassette(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: CassetteMeta
    interactions: list[Interaction]

    @classmethod
    def load(cls, path: Path) -> Cassette:
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, path: Path) -> None:
        path.write_text(self.model_dump_json(indent=2, exclude_none=True) + "\n", encoding="utf-8")


class _ChunkedStream(httpx.AsyncByteStream):
    def __init__(self, body: bytes, size: int) -> None:
        self._body = body
        self._size = size

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for start in range(0, len(self._body), self._size):
            yield self._body[start : start + self._size]


def _body_json(request: httpx.Request) -> object:
    if not request.content:
        return None
    try:
        return json.loads(request.content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


class CassettePlayer:
    """Serves a cassette's responses in order (use as a respx side effect)."""

    def __init__(self, cassette: Cassette) -> None:
        self.cassette = cassette
        self._queue: deque[Interaction] = deque(cassette.interactions)
        self.requests: list[httpx.Request] = []

    @property
    def remaining(self) -> int:
        return len(self._queue)

    def bodies(self) -> list[object]:
        """JSON bodies of the requests served so far."""
        return [_body_json(request) for request in self.requests]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self._queue:
            raise CassetteError(f"unexpected request {request.method} {request.url}: cassette done")
        interaction = self._queue.popleft()
        expected = interaction.request
        if request.method != expected.method or not request.url.path.endswith(expected.path):
            raise CassetteError(
                f"request {request.method} {request.url.path} does not match the recorded "
                f"{expected.method} ...{expected.path}"
            )
        if expected.match:
            body = _body_json(request)
            if not isinstance(body, Mapping):
                raise CassetteError(
                    "the recorded request pins body fields but the body is not JSON"
                )
            for key, value in expected.match.items():
                if body.get(key) != value:
                    raise CassetteError(
                        f"body field {key!r} is {body.get(key)!r}, recorded {value!r}"
                    )
        recorded = interaction.response
        headers = {"content-type": recorded.content_type(), **recorded.headers}
        body_bytes = recorded.body_bytes()
        if recorded.chunk_size is not None:
            return httpx.Response(
                recorded.status,
                headers=headers,
                stream=_ChunkedStream(body_bytes, recorded.chunk_size),
            )
        return httpx.Response(recorded.status, headers=headers, content=body_bytes)

    def assert_done(self) -> None:
        if self._queue:
            raise CassetteError(f"{len(self._queue)} recorded interaction(s) were not used")


def cassette_mode(environ: Mapping[str, str] | None = None) -> CassetteMode:
    """``replay`` unless record mode is asked for explicitly *and* a key is present."""
    env = os.environ if environ is None else environ
    mode = env.get(MODE_VARIABLE, "replay").strip().lower() or "replay"
    if mode == "replay":
        return "replay"
    if mode != "record":
        raise CassetteError(f"{MODE_VARIABLE} must be 'replay' or 'record', not {mode!r}")
    if not env.get(KEY_VARIABLE, "").strip():
        raise CassetteError(f"record mode needs {KEY_VARIABLE}; refusing to record without it")
    return "record"


def _redact(headers: httpx.Headers) -> dict[str, str]:
    return {k.lower(): v for k, v in headers.items() if k.lower() not in _REDACTED_HEADERS}


class RecordingTransport(httpx.AsyncBaseTransport):
    """Sends requests through ``inner`` and records each exchange into ``cassette``."""

    def __init__(self, inner: httpx.AsyncBaseTransport, cassette: Cassette) -> None:
        self._inner = inner
        self.cassette = cassette

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        body = await response.aread()
        await response.aclose()
        content_type = response.headers.get("content-type", "")
        recorded = RecordedResponse(status=response.status_code, headers=_redact(response.headers))
        text = body.decode("utf-8", errors="replace")
        if "text/event-stream" in content_type:
            recorded.sse = [
                line.removeprefix("data:").strip()
                for line in text.splitlines()
                if line.startswith("data:")
            ]
        elif "json" in content_type:
            try:
                recorded.json_body = json.loads(text)
            except json.JSONDecodeError:
                recorded.text = text
        else:
            recorded.text = text
        request_body = _body_json(request)
        match = (
            {"model": request_body["model"]}
            if isinstance(request_body, Mapping) and "model" in request_body
            else {}
        )
        self.cassette.interactions.append(
            Interaction(
                request=RecordedRequest(method=request.method, path=request.url.path, match=match),
                response=recorded,
            )
        )
        self.cassette.meta.recorded_at = datetime.now(UTC)
        self.cassette.meta.hand_authored = False
        # aread() decoded any content-encoding; the rebuilt response carries the decoded bytes.
        headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")
        }
        return httpx.Response(response.status_code, headers=headers, content=body, request=request)

    async def aclose(self) -> None:
        await self._inner.aclose()
