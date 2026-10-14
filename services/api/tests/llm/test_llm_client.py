"""HTTP client against recorded (hand-authored) Token Factory exchanges; nothing leaves the process."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
import respx

from tests.llm.helpers import HOST, PLACEHOLDER_KEY, SleepRecorder, make_client, mount
from yield_guardian.llm.client import parse_ocr_response
from yield_guardian.llm.errors import (
    ErrorKind,
    ResponseShapeError,
    StreamProtocolError,
    StreamReportedError,
    TokenFactoryHttpError,
    TransportError,
)
from yield_guardian.llm.retry import RetryPolicy

CHAT_BODY: dict[str, Any] = {
    "model": "DeepSeek-V4-Flash",
    "messages": [{"role": "user", "content": "Say hello."}],
    "max_tokens": 64,
    "reasoning_effort": "none",
}
STREAM_BODY: dict[str, Any] = {**CHAT_BODY, "model": "Qwen3.8-Flash-Next", "stream": True}


def error_response(status: int, message: str, **headers: str) -> httpx.Response:
    return httpx.Response(
        status, headers=headers, json={"error": {"message": message, "type": "fixture"}}
    )


async def test_completion_sends_the_body_unchanged_with_the_bearer_key(
    respx_mock: respx.Router,
) -> None:
    player = mount(respx_mock, "chat_text_deepseek")
    client = make_client()
    reply = await client.chat_completion(CHAT_BODY)
    (request,) = player.requests
    assert request.url == "https://developer.amd.com.cn/radeon/api/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {PLACEHOLDER_KEY}"
    assert json.loads(request.content) == CHAT_BODY
    assert reply.status == 200
    assert reply.attempts == 1
    assert reply.headers["x-ratelimit-remaining-requests"] == "19"
    player.assert_done()


async def test_without_a_key_no_authorization_header_is_sent(respx_mock: respx.Router) -> None:
    player = mount(respx_mock, "chat_text_deepseek")
    await make_client(api_key=None).chat_completion(CHAT_BODY)
    assert "authorization" not in player.requests[0].headers


def test_repr_never_shows_the_key() -> None:
    client = make_client()
    assert PLACEHOLDER_KEY not in repr(client)
    assert "key=set" in repr(client)
    assert "key=unset" in repr(make_client(api_key=None))


async def test_header_observers_see_every_response(respx_mock: respx.Router) -> None:
    mount(respx_mock, "chat_text_deepseek")
    client = make_client()
    seen: list[dict[str, str]] = []
    client.add_header_observer(lambda headers: seen.append(dict(headers)))
    await client.chat_completion(CHAT_BODY)
    assert seen[0]["x-ratelimit-limit-requests"] == "20"


async def test_429_waits_for_retry_after_then_succeeds(respx_mock: respx.Router) -> None:
    player = mount(respx_mock, "error_429_retry_after")
    sleep = SleepRecorder()
    reply = await make_client(sleep=sleep).chat_completion(CHAT_BODY)
    assert reply.attempts == 2
    assert sleep.delays == [1.0]  # Retry-After 1 s; the jitter ceiling of retry 1 is also 1 s
    player.assert_done()


async def test_a_retry_after_beyond_the_wait_bound_is_returned_not_waited(
    respx_mock: respx.Router,
) -> None:
    route = respx_mock.post(host=HOST).mock(
        return_value=error_response(429, "spend cap reached", **{"retry-after": "32400"})
    )
    sleep = SleepRecorder()
    with pytest.raises(TokenFactoryHttpError) as caught:
        await make_client(sleep=sleep).chat_completion(CHAT_BODY)
    assert caught.value.kind is ErrorKind.RATE_LIMITED
    assert caught.value.retry_after == 32400.0
    assert caught.value.attempts == 1
    assert sleep.delays == []
    assert route.call_count == 1


async def test_503_is_retried_three_times_with_growing_jitter(respx_mock: respx.Router) -> None:
    route = respx_mock.post(host=HOST).mock(return_value=error_response(503, "saturated"))
    sleep = SleepRecorder()
    with pytest.raises(TokenFactoryHttpError) as caught:
        await make_client(sleep=sleep).chat_completion(CHAT_BODY)
    assert route.call_count == 4
    assert caught.value.attempts == 4
    assert caught.value.kind is ErrorKind.UNAVAILABLE
    assert len(sleep.delays) == 3
    for delay, ceiling in zip(sleep.delays, [1.0, 2.0, 4.0], strict=True):
        assert 0.0 <= delay <= ceiling


async def test_502_then_success(respx_mock: respx.Router) -> None:
    ok = httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]})
    route = respx_mock.post(host=HOST).mock(side_effect=[error_response(502, "bad gw"), ok])
    reply = await make_client().chat_completion(CHAT_BODY)
    assert reply.attempts == 2
    assert route.call_count == 2


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422, 500, 504])
async def test_other_errors_are_not_retried(respx_mock: respx.Router, status: int) -> None:
    route = respx_mock.post(host=HOST).mock(return_value=error_response(status, "no"))
    sleep = SleepRecorder()
    with pytest.raises(TokenFactoryHttpError) as caught:
        await make_client(sleep=sleep).chat_completion(CHAT_BODY)
    assert caught.value.status == status
    assert route.call_count == 1
    assert sleep.delays == []


async def test_every_documented_error_shape_is_classified(respx_mock: respx.Router) -> None:
    player = mount(respx_mock, "error_shapes")
    client = make_client(retry=RetryPolicy(max_retries=0))
    expected = [
        (400, ErrorKind.UNKNOWN_MODEL, "gateway", "Requested model Fixture-Missing-Model"),
        (400, ErrorKind.INSUFFICIENT_CREDITS, "platform", "Not enough credits"),
        (401, ErrorKind.UNAUTHORIZED, "gateway", "Invalid API key"),
        (403, ErrorKind.ACCOUNT_NOT_VERIFIED, "platform", "Account is in review"),
        (422, ErrorKind.UNPROCESSABLE, "platform", "reasoning_effort 'xhigh'"),
        (503, ErrorKind.UNAVAILABLE, "gateway", "Upstream saturated"),
    ]
    for status, kind, shape, message in expected:
        with pytest.raises(TokenFactoryHttpError) as caught:
            await client.chat_completion(CHAT_BODY)
        assert caught.value.status == status
        assert caught.value.kind is kind
        assert caught.value.error.shape == shape
        assert caught.value.error.message.startswith(message)
    player.assert_done()


async def test_an_error_body_that_is_not_json_keeps_its_text(respx_mock: respx.Router) -> None:
    respx_mock.post(host=HOST).mock(return_value=httpx.Response(404, text="Not Found"))
    with pytest.raises(TokenFactoryHttpError) as caught:
        await make_client().chat_completion(CHAT_BODY)
    assert caught.value.error.message == "Not Found"
    assert caught.value.kind is ErrorKind.NOT_FOUND


@pytest.mark.parametrize(
    ("error", "fragment"),
    [(httpx.ConnectError("refused"), "failed"), (httpx.ReadTimeout("slow"), "timeout")],
)
async def test_transport_failures_are_not_retried(
    respx_mock: respx.Router, error: Exception, fragment: str
) -> None:
    route = respx_mock.post(host=HOST).mock(side_effect=error)
    with pytest.raises(TransportError, match=fragment):
        await make_client().chat_completion(CHAT_BODY)
    assert route.call_count == 1


async def test_a_success_without_json_is_a_shape_error(respx_mock: respx.Router) -> None:
    respx_mock.post(host=HOST).mock(return_value=httpx.Response(200, text="<html>"))
    with pytest.raises(ResponseShapeError):
        await make_client().chat_completion(CHAT_BODY)


async def test_streaming_and_plain_bodies_go_to_the_right_method() -> None:
    client = make_client()
    with pytest.raises(ValueError, match="stream_chat_completion"):
        await client.chat_completion(STREAM_BODY)
    with pytest.raises(ValueError, match="stream: true"):
        async for _ in client.stream_chat_completion(CHAT_BODY):
            pass


async def collect(client: Any, body: dict[str, Any]) -> list[dict[str, Any]]:
    return [chunk async for chunk in client.stream_chat_completion(body)]


async def test_stream_yields_chunks_until_done(respx_mock: respx.Router) -> None:
    player = mount(respx_mock, "stream_text_qwen")
    client = make_client()
    seen: list[dict[str, str]] = []
    client.add_header_observer(lambda headers: seen.append(dict(headers)))
    chunks = await collect(client, STREAM_BODY)
    assert len(chunks) == 6
    assert chunks[3]["choices"][0]["delta"]["content"] == "T² chart."
    assert player.requests[0].headers["accept"] == "text/event-stream"
    assert seen[0]["x-ratelimit-remaining-requests"] == "16"


async def test_stream_without_done_is_a_protocol_error(respx_mock: respx.Router) -> None:
    body = 'data: {"choices":[{"delta":{"content":"cut"}}]}\n\n'
    respx_mock.post(host=HOST).mock(
        return_value=httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
    )
    with pytest.raises(StreamProtocolError, match="DONE"):
        await collect(make_client(), STREAM_BODY)


async def test_an_error_event_inside_the_stream_is_raised(respx_mock: respx.Router) -> None:
    body = (
        'data: {"choices":[{"delta":{"content":"start"}}]}\n\n'
        'data: {"error":{"message":"upstream reset","type":"server_error"}}\n\n'
        "data: [DONE]\n\n"
    )
    respx_mock.post(host=HOST).mock(return_value=httpx.Response(200, text=body))
    with pytest.raises(StreamReportedError, match="upstream reset"):
        await collect(make_client(), STREAM_BODY)


async def test_a_stream_event_that_is_not_json_is_a_protocol_error(
    respx_mock: respx.Router,
) -> None:
    respx_mock.post(host=HOST).mock(return_value=httpx.Response(200, text="data: {oops\n\n"))
    with pytest.raises(StreamProtocolError, match="not JSON"):
        await collect(make_client(), STREAM_BODY)


async def test_stream_retries_a_429_before_the_first_chunk(respx_mock: respx.Router) -> None:
    ok = httpx.Response(
        200, text='data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n'
    )
    route = respx_mock.post(host=HOST).mock(
        side_effect=[error_response(429, "busy", **{"retry-after": "1"}), ok]
    )
    sleep = SleepRecorder()
    chunks = await collect(make_client(sleep=sleep), STREAM_BODY)
    assert [c["choices"][0]["delta"]["content"] for c in chunks] == ["ok"]
    assert route.call_count == 2
    assert sleep.delays == [1.0]


async def test_stream_failure_after_retries_keeps_the_server_error(
    respx_mock: respx.Router,
) -> None:
    route = respx_mock.post(host=HOST).mock(return_value=error_response(503, "saturated"))
    with pytest.raises(TokenFactoryHttpError) as caught:
        await collect(make_client(), STREAM_BODY)
    assert caught.value.error.message == "saturated"
    assert caught.value.attempts == 4
    assert route.call_count == 4


async def test_catalog_and_usage_endpoints(respx_mock: respx.Router) -> None:
    player = mount(respx_mock, "catalog_and_usage")
    client = make_client()
    entries = await client.list_models()
    assert [e.id for e in entries][:2] == ["DeepSeek-V4-Flash", "DeepSeek-V4.1-Flash"]
    assert {e.id: e.context_length for e in entries}["MiniCPM-V-4.7-1B"] == 65_536
    usage = await client.get_usage()
    assert isinstance(usage, dict)
    assert usage["remaining"] == 0.75
    assert player.requests[1].url.params["include_recent"] == "true"
    player.assert_done()


async def test_ocr_request_and_page_indices(respx_mock: respx.Router) -> None:
    player = mount(respx_mock, "ocr_mineru")
    result = await make_client().ocr(document_url="https://example.org/paper.pdf", pages="0-1")
    assert json.loads(player.requests[0].content) == {
        "model": "MinerU2.5-Pro",
        "document": {"type": "document_url", "document_url": "https://example.org/paper.pdf"},
        "pages": "0-1",
    }
    assert [page.index for page in result.pages] == [0, 1]
    assert result.pages[1].markdown.startswith("## 2. Method")
    assert result.pages_processed == 2


def test_ocr_pages_are_numbered_from_the_first_requested_page() -> None:
    payload = {"pages": [{"markdown": "a"}, {"markdown": "b", "index": 9}]}
    result = parse_ocr_response(payload, model="MinerU2.5-Pro", requested_pages="4-5")
    assert [page.index for page in result.pages] == [4, 9]
    assert result.pages_processed is None
    with pytest.raises(ResponseShapeError):
        parse_ocr_response({"pages": [{"text": "a"}]}, model="m", requested_pages=None)


async def test_the_client_does_not_cap_requests_in_flight(respx_mock: respx.Router) -> None:
    """No request limits (owner decision): ten calls are all in flight at the same time."""
    in_flight = 0
    peak = 0
    release = asyncio.Event()

    async def slow(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        if in_flight == 10:
            release.set()
        await asyncio.wait_for(release.wait(), timeout=5)
        in_flight -= 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]})

    respx_mock.post(host=HOST).mock(side_effect=slow)
    client = make_client()
    replies = await asyncio.gather(*(client.chat_completion(CHAT_BODY) for _ in range(10)))
    assert peak == 10
    assert all(reply.attempts == 1 for reply in replies)
