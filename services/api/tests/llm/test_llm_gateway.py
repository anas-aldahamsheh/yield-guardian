"""Gateway: role chains, fallback rules, cache, structured output, streaming, call records."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx
from pydantic import BaseModel, ConfigDict

from tests.llm.helpers import HOST, Stack, load_cassette, make_stack, mount
from yield_guardian.llm.calllog import CallStatus, to_llm_call
from yield_guardian.llm.errors import (
    NoModelAvailableError,
    StreamProtocolError,
    TokenFactoryHttpError,
)
from yield_guardian.llm.gateway import CallOptions
from yield_guardian.llm.messages import ChatMessage, ChatRequest, FunctionSpec, ToolSpec
from yield_guardian.llm.registry import ModelChoice, ResponseMode, Role
from yield_guardian.llm.results import ChatResult, StreamDelta


class Verdicts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdicts: list[str]


class FixtureAnswer(BaseModel):
    label: str
    count: int


def json_request(max_tokens: int = 512) -> ChatRequest:
    return ChatRequest(
        messages=(
            ChatMessage.system("Answer with one JSON object."),
            ChatMessage.user("Check the claims."),
        ),
        max_tokens=max_tokens,
    )


def text_request() -> ChatRequest:
    return ChatRequest(
        messages=(ChatMessage.system("Be brief."), ChatMessage.user("Hello?")), max_tokens=256
    )


def completion(model: str, content: str | None, **usage: int) -> httpx.Response:
    body: dict[str, Any] = {
        "model": model,
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
    }
    if usage:
        body["usage"] = usage
    return httpx.Response(200, json=body)


def failure(status: int, message: str, **headers: str) -> httpx.Response:
    return httpx.Response(status, headers=headers, json={"error": {"message": message}})


def sent_bodies(route: respx.Route) -> list[dict[str, Any]]:
    return [json.loads(call.request.content) for call in route.calls]


@pytest.fixture
def stack() -> Stack:
    return make_stack()


async def test_structured_call_records_tokens_points_and_headers(
    respx_mock: respx.Router, stack: Stack
) -> None:
    player = mount(respx_mock, "chat_reasoning_glm")
    out = await stack.gateway.complete_structured(
        Role.VERIFIER,
        json_request(),
        Verdicts,
        schema_name="verdicts",
        options=CallOptions(correlation_id="inv_fixture01"),
    )
    assert out.value == Verdicts(verdicts=[])
    body = player.bodies()[0]
    assert isinstance(body, dict)
    assert body["reasoning_effort"] == "low"
    assert body["response_format"] == {"type": "json_object"}
    expected_points = (1500 * 0.15 + 500 * 0.03 + 400 * 0.50) / 1_000_000
    assert out.result.points == pytest.approx(expected_points)
    assert out.result.reasoning is not None
    assert out.result.rate_limit_headers["x-ratelimit-remaining-requests"] == "18"
    (record,) = stack.call_log.records
    assert record.status is CallStatus.OK
    assert (record.role, record.model, record.correlation_id) == (
        "verifier",
        "GLM-5.3-Flash",
        "inv_fixture01",
    )
    assert (record.tokens_in, record.tokens_out, record.tokens_reasoning, record.tokens_cached) == (
        2000,
        400,
        300,
        500,
    )
    assert record.points == pytest.approx(expected_points)
    state = stack.quota.state()
    assert state.local_spend_since_snapshot == pytest.approx(expected_points)
    assert state.headers_seen["x-ratelimit-reset-requests"] == "42s"


async def test_a_repeated_call_is_answered_from_the_cache(
    respx_mock: respx.Router, stack: Stack
) -> None:
    player = mount(respx_mock, "chat_reasoning_glm")
    first = await stack.gateway.complete_structured(
        Role.VERIFIER, json_request(), Verdicts, schema_name="verdicts"
    )
    second = await stack.gateway.complete_structured(
        Role.VERIFIER, json_request(), Verdicts, schema_name="verdicts"
    )
    assert len(player.requests) == 1
    assert second.result.cache_hit
    assert second.result.points == 0.0
    assert second.result.attempts == 0
    assert second.result.cache_key == first.result.cache_key
    assert second.value == first.value
    hit = stack.call_log.records[1]
    assert hit.cache_hit
    assert not hit.sent
    assert hit.tokens_in == 0
    assert to_llm_call(hit).status == "cached"


async def test_use_cache_false_calls_the_endpoint_again(
    respx_mock: respx.Router, stack: Stack
) -> None:
    route = respx_mock.post(host=HOST).mock(
        return_value=completion("GLM-5.3-Flash", '{"verdicts": []}')
    )
    for _ in range(2):
        await stack.gateway.complete_structured(
            Role.VERIFIER,
            json_request(),
            Verdicts,
            schema_name="verdicts",
            options=CallOptions(use_cache=False),
        )
    assert route.call_count == 2


async def test_writer_falls_back_from_mimo_prose_to_qwen_json_object(
    respx_mock: respx.Router, stack: Stack
) -> None:
    player = mount(respx_mock, "structured_fallback")
    out = await stack.gateway.complete_structured(
        Role.WRITER, json_request(), FixtureAnswer, schema_name="fixture_answer"
    )
    assert out.value == FixtureAnswer(label="fixture", count=3)
    assert out.result.model == "Qwen3.8-27B"
    first, second = player.bodies()
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    schema_format = first["response_format"]
    assert schema_format["type"] == "json_schema"
    assert schema_format["json_schema"]["name"] == "fixture_answer"
    assert schema_format["json_schema"]["strict"] is True
    assert schema_format["json_schema"]["schema"]["additionalProperties"] is False
    assert second["response_format"] == {"type": "json_object"}
    statuses = [(r.model, r.status) for r in stack.call_log.records]
    assert statuses == [
        ("MiMo-V2.6-Flash", CallStatus.INVALID_OUTPUT),
        ("Qwen3.8-27B", CallStatus.OK),
    ]
    # Both calls were billed; Qwen3.8-27B reports no reasoning count.
    assert stack.call_log.records[0].points == pytest.approx((1500 * 0.14 + 50 * 0.28) / 1e6)
    assert stack.call_log.records[1].tokens_reasoning is None
    assert out.result.points == pytest.approx((1500 * 0.50 + 40 * 3.00) / 1e6)
    player.assert_done()


async def test_an_empty_answer_falls_back_and_is_not_cached(
    respx_mock: respx.Router, stack: Stack
) -> None:
    empty = load_cassette("chat_length_empty").interactions[0].response.json_body
    route = respx_mock.post(host=HOST).mock(
        side_effect=[
            httpx.Response(200, json=empty),
            completion("Qwen3.8-27B", '{"label": "x", "count": 1}'),
        ]
    )
    out = await stack.gateway.complete_structured(
        Role.WRITER, json_request(), FixtureAnswer, schema_name="fixture_answer"
    )
    assert out.result.model == "Qwen3.8-27B"
    assert [r.status for r in stack.call_log.records] == [CallStatus.EMPTY, CallStatus.OK]
    assert route.call_count == 2
    assert len(stack.cache) == 1  # only the valid answer


async def test_an_unknown_model_falls_back_to_the_next_entry(
    respx_mock: respx.Router, stack: Stack
) -> None:
    route = respx_mock.post(host=HOST).mock(
        side_effect=[
            failure(400, "Requested model DeepSeek-V4.1-Flash not supported"),
            completion("GLM-5.3-Flash", "Investigating.", prompt_tokens=10, completion_tokens=2),
        ]
    )
    result = await stack.gateway.complete(Role.INVESTIGATOR, text_request())
    assert result.model == "GLM-5.3-Flash"
    assert [body["model"] for body in sent_bodies(route)] == [
        "DeepSeek-V4.1-Flash",
        "GLM-5.3-Flash",
    ]
    error = stack.call_log.records[0]
    assert (error.status, error.http_status, error.error_kind) == (
        CallStatus.ERROR,
        400,
        "unknown_model",
    )
    assert error.tokens_in is None
    assert to_llm_call(error).error == "Requested model DeepSeek-V4.1-Flash not supported"


@pytest.mark.parametrize(
    "response",
    [
        failure(401, "Invalid API key"),
        failure(400, "Not enough credits"),
        failure(429, "daily spend cap reached", **{"retry-after": "32400"}),
    ],
)
async def test_account_wide_failures_stop_the_chain(
    respx_mock: respx.Router, stack: Stack, response: httpx.Response
) -> None:
    route = respx_mock.post(host=HOST).mock(return_value=response)
    with pytest.raises(TokenFactoryHttpError):
        await stack.gateway.complete(Role.INVESTIGATOR, text_request())
    assert route.call_count == 1
    assert len(stack.call_log.records) == 1


async def test_a_profile_refusal_is_logged_unsent_and_falls_back(
    respx_mock: respx.Router, stack: Stack
) -> None:
    route = respx_mock.post(host=HOST).mock(
        return_value=completion("DeepSeek-V4-Flash", '{"verdicts": ["ok"]}')
    )
    # 300,000 tokens exceed GLM-5.3-Flash's 262,144-token window, not DeepSeek-V4-Flash's.
    out = await stack.gateway.complete_structured(
        Role.VERIFIER, json_request(max_tokens=300_000), Verdicts, schema_name="verdicts"
    )
    assert out.result.model == "DeepSeek-V4-Flash"
    refused, ok = stack.call_log.records
    assert refused.status is CallStatus.REFUSED_PROFILE
    assert not refused.sent
    assert refused.points == 0.0
    assert to_llm_call(refused).status == "refused"
    assert ok.status is CallStatus.OK
    assert route.call_count == 1


async def test_when_every_model_fails_each_failure_is_listed(
    respx_mock: respx.Router, stack: Stack
) -> None:
    respx_mock.post(host=HOST).mock(return_value=completion("x", "not json at all"))
    with pytest.raises(NoModelAvailableError) as caught:
        await stack.gateway.complete_structured(
            Role.VERIFIER, json_request(), Verdicts, schema_name="verdicts"
        )
    assert [model for model, _ in caught.value.failures] == ["GLM-5.3-Flash", "DeepSeek-V4-Flash"]
    assert all("invalid structured output" in why for _, why in caught.value.failures)


async def test_the_verifier_can_exclude_the_writer_family(
    respx_mock: respx.Router, stack: Stack
) -> None:
    route = respx_mock.post(host=HOST).mock(
        return_value=completion("DeepSeek-V4-Flash", '{"verdicts": []}')
    )
    out = await stack.gateway.complete_structured(
        Role.VERIFIER,
        json_request(),
        Verdicts,
        schema_name="verdicts",
        options=CallOptions(exclude_families=frozenset({"glm"})),
    )
    assert out.result.model == "DeepSeek-V4-Flash"
    assert route.call_count == 1


async def test_callers_cannot_choose_reasoning_effort_or_skip_json(stack: Stack) -> None:
    with pytest.raises(ValueError, match="per role"):
        await stack.gateway.complete(
            Role.CHAT, text_request().model_copy(update={"reasoning_effort": "high"})
        )
    with pytest.raises(ValueError, match="mention JSON"):
        await stack.gateway.complete_structured(
            Role.VERIFIER, text_request(), Verdicts, schema_name="verdicts"
        )


async def test_tool_calls_come_back_on_the_result(respx_mock: respx.Router, stack: Stack) -> None:
    player = mount(respx_mock, "chat_tool_calls_deepseek")
    tool = ToolSpec(
        function=FunctionSpec(
            name="get_shap",
            description="SHAP contributions of one unit.",
            parameters={"type": "object", "properties": {"unit_id": {"type": "integer"}}},
        )
    )
    request = text_request().model_copy(update={"tools": (tool,)})
    result = await stack.gateway.complete(Role.INVESTIGATOR, request)
    assert [call.function.name for call in result.tool_calls] == ["get_shap", "get_contributions"]
    assert not result.is_empty
    body = player.bodies()[0]
    assert isinstance(body, dict)
    assert body["tools"][0]["function"]["name"] == "get_shap"


async def collect(stack: Stack, request: ChatRequest) -> list[StreamDelta | ChatResult]:
    return [item async for item in stack.gateway.stream(Role.CHAT, request)]


async def test_stream_yields_deltas_then_the_result(respx_mock: respx.Router, stack: Stack) -> None:
    player = mount(respx_mock, "stream_text_qwen")
    items = await collect(stack, text_request())
    *deltas, final = items
    assert [d.type for d in deltas if isinstance(d, StreamDelta)] == [
        "reasoning",
        "content",
        "content",
    ]
    assert isinstance(final, ChatResult)
    assert final.content == "Fixture answer, T² chart."
    assert final.points == pytest.approx((300 * 0.15 + 25 * 0.47) / 1e6)
    body = player.bodies()[0]
    assert isinstance(body, dict)
    assert body["stream"] is True
    assert body["reasoning_effort"] == "none"
    assert "stream_options" not in body
    (record,) = stack.call_log.records
    assert record.stream
    assert record.status is CallStatus.OK


async def test_stream_without_usage_reports_unknown_usage(
    respx_mock: respx.Router, stack: Stack
) -> None:
    mount(respx_mock, "stream_no_usage")
    final = (await collect(stack, text_request()))[-1]
    assert isinstance(final, ChatResult)
    assert final.points is None
    (record,) = stack.call_log.records
    assert record.tokens_in is None
    assert to_llm_call(record).error == "usage not reported by the endpoint"


async def test_stream_falls_back_only_before_the_first_delta(
    respx_mock: respx.Router, stack: Stack
) -> None:
    ok = httpx.Response(
        200, text='data: {"choices":[{"delta":{"content":"fallback"}}]}\n\ndata: [DONE]\n\n'
    )
    route = respx_mock.post(host=HOST).mock(
        side_effect=[failure(400, "Requested model Qwen3.8-Flash-Next not supported"), ok]
    )
    final = (await collect(stack, text_request()))[-1]
    assert isinstance(final, ChatResult)
    assert final.model == "DeepSeek-V4-Flash"
    assert route.call_count == 2


async def test_a_stream_that_breaks_after_a_delta_is_not_retried_elsewhere(
    respx_mock: respx.Router, stack: Stack
) -> None:
    broken = httpx.Response(200, text='data: {"choices":[{"delta":{"content":"partial"}}]}\n\n')
    route = respx_mock.post(host=HOST).mock(return_value=broken)
    seen: list[StreamDelta | ChatResult] = []

    async def drain() -> None:
        async for item in stack.gateway.stream(Role.CHAT, text_request()):
            seen.append(item)

    with pytest.raises(StreamProtocolError):
        await drain()
    assert [d.text for d in seen if isinstance(d, StreamDelta)] == ["partial"]
    assert route.call_count == 1
    assert stack.call_log.records[0].status is CallStatus.ERROR


async def test_a_repeated_stream_is_served_from_the_cache(
    respx_mock: respx.Router, stack: Stack
) -> None:
    player = mount(respx_mock, "stream_text_qwen")
    await collect(stack, text_request())
    again = await collect(stack, text_request())
    assert len(player.requests) == 1
    delta, final = again
    assert isinstance(delta, StreamDelta)
    assert delta.text == "Fixture answer, T² chart."
    assert isinstance(final, ChatResult)
    assert final.cache_hit


async def test_role_changes_apply_to_the_next_call(respx_mock: respx.Router, stack: Stack) -> None:
    route = respx_mock.post(host=HOST).mock(return_value=completion("DeepSeek-V4-Flash", "hi"))
    await stack.registry.assign(
        Role.CHAT,
        [ModelChoice(model="DeepSeek-V4-Flash", reasoning_effort="low")],
        actor="engineer",
    )
    result = await stack.gateway.complete(Role.CHAT, text_request())
    assert result.model == "DeepSeek-V4-Flash"
    assert sent_bodies(route)[0]["reasoning_effort"] == "low"


async def test_structured_output_needs_a_json_mode_in_the_chain(stack: Stack) -> None:
    await stack.registry.assign(
        Role.CHAT,
        [
            ModelChoice(
                model="DeepSeek-V4-Flash", reasoning_effort="none", response_mode=ResponseMode.TEXT
            )
        ],
        actor="engineer",
    )
    with pytest.raises(NoModelAvailableError, match="structured output needs a JSON mode"):
        await stack.gateway.complete_structured(
            Role.CHAT, json_request(), Verdicts, schema_name="verdicts"
        )


SCHEMA_400 = {
    "error": {
        "message": "Invalid response_format",
        "type": "invalid_request_error",
        "param": "response_format.json_schema",
    }
}


async def test_a_refused_schema_is_retried_on_the_same_model_as_json_object(
    respx_mock: respx.Router, stack: Stack
) -> None:
    route = respx_mock.post(host=HOST).mock(
        side_effect=[
            httpx.Response(400, json=SCHEMA_400),
            completion("MiMo-V2.6-Flash", '{"label": "x", "count": 1}'),
        ]
    )
    out = await stack.gateway.complete_structured(
        Role.WRITER, json_request(), FixtureAnswer, schema_name="fixture_answer"
    )
    assert out.result.model == "MiMo-V2.6-Flash"
    first, second = sent_bodies(route)
    assert (first["model"], first["response_format"]["type"]) == ("MiMo-V2.6-Flash", "json_schema")
    assert (second["model"], second["response_format"]) == (
        "MiMo-V2.6-Flash",
        {"type": "json_object"},
    )
    assert second["reasoning_effort"] == first["reasoning_effort"]
    error, ok = stack.call_log.records
    assert (error.status, error.http_status, error.error_kind) == (
        CallStatus.ERROR,
        400,
        "bad_request",
    )
    assert error.error_body is not None
    assert "response_format.json_schema" in error.error_body
    assert ok.status is CallStatus.OK


async def test_when_both_shapes_fail_the_chain_moves_on_and_names_both_reasons(
    respx_mock: respx.Router, stack: Stack
) -> None:
    respx_mock.post(host=HOST).mock(
        side_effect=[
            httpx.Response(400, json=SCHEMA_400),
            failure(400, "reasoning_effort low is not supported"),
            failure(400, "bad request again"),
        ]
    )
    with pytest.raises(NoModelAvailableError) as caught:
        await stack.gateway.complete_structured(
            Role.WRITER, json_request(), FixtureAnswer, schema_name="fixture_answer"
        )
    text = str(caught.value)
    assert "MiMo-V2.6-Flash: HTTP 400 bad_request: Invalid response_format" in text
    assert "as json_object: HTTP 400 bad_request: reasoning_effort low is not supported" in text
    assert "Qwen3.8-27B: HTTP 400 bad_request: bad request again" in text
    assert [r.model for r in stack.call_log.records] == [
        "MiMo-V2.6-Flash",
        "MiMo-V2.6-Flash",
        "Qwen3.8-27B",
    ]
    assert all(r.error_body for r in stack.call_log.records)


async def test_a_400_on_a_json_object_model_is_not_retried_on_the_same_model(
    respx_mock: respx.Router, stack: Stack
) -> None:
    await stack.registry.assign(
        Role.WRITER,
        [
            ModelChoice(
                model="Qwen3.8-27B", reasoning_effort="low", response_mode=ResponseMode.JSON_OBJECT
            )
        ],
        actor="test",
    )
    route = respx_mock.post(host=HOST).mock(return_value=failure(400, "no"))
    with pytest.raises(NoModelAvailableError):
        await stack.gateway.complete_structured(
            Role.WRITER, json_request(), FixtureAnswer, schema_name="fixture_answer"
        )
    assert route.call_count == 1


async def test_an_http_error_body_is_logged_without_the_key(
    respx_mock: respx.Router, stack: Stack
) -> None:
    from structlog.testing import capture_logs

    secret = "rc-" + "ab" * 24
    respx_mock.post(host=HOST).mock(
        return_value=httpx.Response(
            422,
            json={"error": {"message": f"bad schema for key {secret}", "param": "messages"}},
        )
    )
    with capture_logs() as logs, pytest.raises(NoModelAvailableError):
        await stack.gateway.complete(Role.INVESTIGATOR, text_request())
    warnings = [e for e in logs if e["event"] == "llm_http_error"]
    assert warnings
    assert warnings[0]["status"] == 422
    assert warnings[0]["param"] == "messages"
    assert "bad schema" in warnings[0]["body"]
    assert all(secret not in str(e) for e in logs)
    assert all(secret not in (r.error_body or "") for r in stack.call_log.records)
