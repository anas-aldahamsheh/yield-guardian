"""Async HTTP client for AMD Token Factory (or any OpenAI-compatible endpoint).

Built directly on httpx so that the request body is exactly what
:func:`~yield_guardian.llm.request_builder.build_chat_request` produced: no SDK adds fields,
and ``stream_options`` is never relied on (the gateway drops unknown fields, so usage may be
missing from a stream). Every attempt goes through the :class:`RateLimiter`; only 429, 502
and 503 are retried (see :mod:`yield_guardian.llm.limits`).

The key is held as a :class:`~pydantic.SecretStr` and never logged.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, SecretStr

from yield_guardian.llm.errors import (
    ResponseShapeError,
    StreamProtocolError,
    StreamReportedError,
    TokenFactoryHttpError,
    TransportError,
    parse_error_body,
)
from yield_guardian.llm.limits import Clock, RateLimiter, RetryPolicy, Sleep, parse_retry_after
from yield_guardian.llm.profiles import CatalogEntry, parse_catalog
from yield_guardian.llm.sse import DONE_SENTINEL, SseEvent, SseParser

log = structlog.get_logger(__name__)

DEFAULT_BASE_URL = "https://developer.amd.com.cn/radeon/api/v1"
DEFAULT_TIMEOUT = httpx.Timeout(600.0, connect=15.0)
"""10 minutes: the documented non-streaming timeout and maximum gap between stream chunks."""

HeaderObserver = Callable[[Mapping[str, str]], None]


@dataclass(frozen=True, slots=True)
class HttpReply:
    status: int
    payload: object
    headers: dict[str, str]
    latency_ms: float
    attempts: int


class OcrPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int
    markdown: str


class OcrResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str
    pages: tuple[OcrPage, ...]
    pages_processed: int | None


def _lower_headers(headers: httpx.Headers) -> dict[str, str]:
    return {key.lower(): value for key, value in headers.items()}


def _json_or_none(response: httpx.Response) -> object:
    try:
        return response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _first_page(pages: str | None) -> int:
    if pages is None:
        return 0
    head = pages.split(",")[0].split("-")[0].strip()
    return int(head) if head.isdigit() else 0


def parse_ocr_response(payload: object, *, model: str, requested_pages: str | None) -> OcrResult:
    """Parse ``POST /v1/ocr``: ``pages[].markdown`` and ``usage_info.pages_processed``. When a
    page has no index, its position is counted from the first requested page."""
    if not isinstance(payload, Mapping) or not isinstance(payload.get("pages"), list):
        raise ResponseShapeError("OCR response has no 'pages' list")
    start = _first_page(requested_pages)
    pages: list[OcrPage] = []
    for position, item in enumerate(payload["pages"]):
        if not isinstance(item, Mapping) or not isinstance(item.get("markdown"), str):
            raise ResponseShapeError(f"OCR page {position} has no markdown")
        index = item.get("index")
        pages.append(
            OcrPage(
                index=index
                if isinstance(index, int) and not isinstance(index, bool)
                else start + position,
                markdown=item["markdown"],
            )
        )
    usage_info = payload.get("usage_info")
    processed = usage_info.get("pages_processed") if isinstance(usage_info, Mapping) else None
    return OcrResult(
        model=model,
        pages=tuple(pages),
        pages_processed=processed if isinstance(processed, int) else None,
    )


class TokenFactoryClient:
    def __init__(
        self,
        *,
        api_key: SecretStr | str | None,
        base_url: str = DEFAULT_BASE_URL,
        http: httpx.AsyncClient | None = None,
        limiter: RateLimiter | None = None,
        retry: RetryPolicy | None = None,
        rng: random.Random | None = None,
        sleep: Sleep = asyncio.sleep,
        clock: Clock = time.monotonic,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ) -> None:
        self._key = (
            api_key if isinstance(api_key, SecretStr) or api_key is None else SecretStr(api_key)
        )
        self.base_url = base_url.rstrip("/")
        self._owns_http = http is None
        self._http = http or httpx.AsyncClient(timeout=timeout)
        self.limiter = limiter or RateLimiter()
        self.retry = retry or RetryPolicy()
        self._rng = rng or random.Random()  # noqa: S311 - jitter, not cryptography
        self._sleep = sleep
        self._clock = clock
        self._timeout = timeout
        self._observers: list[HeaderObserver] = []

    def __repr__(self) -> str:
        return (
            f"TokenFactoryClient(base_url={self.base_url!r}, key={'set' if self._key else 'unset'})"
        )

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self) -> TokenFactoryClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    def add_header_observer(self, observer: HeaderObserver) -> None:
        """Called with the lower-cased headers of every response (the budget guard)."""
        self._observers.append(observer)

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._key is not None and self._key.get_secret_value():
            headers["Authorization"] = f"Bearer {self._key.get_secret_value()}"
        return headers

    def _notify(self, headers: Mapping[str, str]) -> None:
        for observer in self._observers:
            observer(headers)

    async def _backoff(self, status: int, headers: Mapping[str, str], retries_done: int) -> bool:
        """Sleep before a retry; False when no retry is allowed."""
        if not self.retry.should_retry(status, retries_done):
            return False
        retry_after = parse_retry_after(headers.get("retry-after"))
        if status == 429 and retry_after is not None:
            self.limiter.bucket.pause_until(self._clock() + min(retry_after, 3600.0))
        delay = self.retry.delay(retries_done, retry_after, self._rng)
        if delay is None:
            return False
        log.info("llm.http.retry", status=status, retry=retries_done + 1, delay_s=round(delay, 3))
        await self._sleep(delay)
        return True

    def _error(
        self, status: int, payload: object, text: str, headers: dict[str, str], attempts: int
    ) -> TokenFactoryHttpError:
        return TokenFactoryHttpError(
            status,
            parse_error_body(payload, text),
            retry_after=parse_retry_after(headers.get("retry-after")),
            attempts=attempts,
            headers=headers,
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, Any] | None = None,
        params: Mapping[str, str] | None = None,
    ) -> HttpReply:
        """Send one logical request (with policy retries) and return the parsed JSON."""
        retries = 0
        started = self._clock()
        while True:
            async with self.limiter.slot():
                try:
                    response = await self._http.request(
                        method,
                        self._url(path),
                        json=json_body,
                        params=params,
                        headers=self._headers(),
                        timeout=self._timeout,
                    )
                except httpx.TimeoutException as exc:
                    raise TransportError(
                        f"timeout on {method} {path}: {type(exc).__name__}"
                    ) from exc
                except httpx.HTTPError as exc:
                    raise TransportError(f"{method} {path} failed: {type(exc).__name__}") from exc
            headers = _lower_headers(response.headers)
            self._notify(headers)
            payload = _json_or_none(response)
            if response.is_success:
                if payload is None:
                    raise ResponseShapeError(f"{method} {path} returned a non-JSON body")
                return HttpReply(
                    status=response.status_code,
                    payload=payload,
                    headers=headers,
                    latency_ms=(self._clock() - started) * 1000.0,
                    attempts=retries + 1,
                )
            if await self._backoff(response.status_code, headers, retries):
                retries += 1
                continue
            raise self._error(response.status_code, payload, response.text, headers, retries + 1)

    async def chat_completion(self, body: Mapping[str, Any]) -> HttpReply:
        if body.get("stream"):
            raise ValueError("use stream_chat_completion for streaming bodies")
        return await self.request("POST", "/chat/completions", json_body=body)

    async def stream_chat_completion(
        self, body: Mapping[str, Any]
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield each ``chat.completion.chunk`` object until ``data: [DONE]``.

        Retries (429, 502, 503) happen only before the first chunk. A stream that ends
        without ``[DONE]`` raises :class:`StreamProtocolError`; an error object inside the
        stream raises :class:`StreamReportedError`. Response headers are passed to the
        observers as soon as the stream opens.
        """
        if not body.get("stream"):
            raise ValueError("a streaming body must set stream: true")
        retries = 0
        while True:
            failure: TokenFactoryHttpError | None = None
            async with self.limiter.slot():
                try:
                    async with self._http.stream(
                        "POST",
                        self._url("/chat/completions"),
                        json=body,
                        headers={**self._headers(), "Accept": "text/event-stream"},
                        timeout=self._timeout,
                    ) as response:
                        headers = _lower_headers(response.headers)
                        self._notify(headers)
                        if response.is_success:
                            async for chunk in self._read_stream(response):
                                yield chunk
                            return
                        await response.aread()
                        failure = self._error(
                            response.status_code,
                            _json_or_none(response),
                            response.text,
                            headers,
                            retries + 1,
                        )
                except httpx.TimeoutException as exc:
                    raise TransportError(f"stream timeout: {type(exc).__name__}") from exc
                except httpx.HTTPError as exc:
                    raise TransportError(f"stream failed: {type(exc).__name__}") from exc
            assert failure is not None  # a successful stream returned above
            if not await self._backoff(failure.status, failure.headers, retries):
                raise failure
            retries += 1

    async def _read_stream(self, response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
        parser = SseParser()
        async for raw in response.aiter_bytes():
            for event in parser.feed(raw):
                chunk = self._decode_event(event)
                if chunk is None:
                    return
                yield chunk
        for event in parser.close():
            chunk = self._decode_event(event)
            if chunk is None:
                return
            yield chunk
        raise StreamProtocolError("stream ended without data: [DONE]")

    @staticmethod
    def _decode_event(event: SseEvent) -> dict[str, Any] | None:
        data = event.data.strip()
        if data == DONE_SENTINEL:
            return None
        try:
            payload = json.loads(data)
        except json.JSONDecodeError as exc:
            raise StreamProtocolError(f"stream event is not JSON: {data[:80]!r}") from exc
        if not isinstance(payload, dict):
            raise StreamProtocolError("stream event is not a JSON object")
        if "error" in payload and "choices" not in payload:
            raise StreamReportedError(parse_error_body(payload))
        return payload

    async def list_models(self) -> list[CatalogEntry]:
        reply = await self.request("GET", "/models")
        return parse_catalog(reply.payload)

    async def get_usage(self) -> object:
        reply = await self.request("GET", "/usage", params={"include_recent": "true"})
        return reply.payload

    async def ocr(
        self, *, document_url: str, pages: str | None = None, model: str = "MinerU2.5-Pro"
    ) -> OcrResult:
        body: dict[str, Any] = {
            "model": model,
            "document": {"type": "document_url", "document_url": document_url},
        }
        if pages is not None:
            body["pages"] = pages
        reply = await self.request("POST", "/ocr", json_body=body)
        return parse_ocr_response(reply.payload, model=model, requested_pages=pages)
