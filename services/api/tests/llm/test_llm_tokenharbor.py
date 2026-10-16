"""TokenHarbor first on the text roles, Token Factory after it; no real network (respx).

The keys below are placeholders, not keys.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx
from pydantic import SecretStr

from tests.llm.helpers import PLACEHOLDER_KEY
from yield_guardian.core.settings import Settings
from yield_guardian.llm.factory import LlmStack, assemble_llm_stack
from yield_guardian.llm.messages import ChatMessage, ChatRequest, FunctionCall, ToolCall
from yield_guardian.llm.profiles import TOKENHARBOR_MODEL
from yield_guardian.llm.registry import Role
from yield_guardian.llm.results import ChatResult

HARBOR_URL = "https://tokenharbor.ai/v1/chat/completions"
FACTORY_URL = "https://developer.amd.com.cn/radeon/api/v1/chat/completions"
HARBOR_KEY = "th-placeholder-not-a-key"


def settings(*, harbor_key: str | None) -> Settings:
    return Settings(
        environment="test",
        log_json=False,
        token_factory_api_key=SecretStr(PLACEHOLDER_KEY),
        tokenharbor_api_key=SecretStr(harbor_key) if harbor_key is not None else None,
    )


def request() -> ChatRequest:
    return ChatRequest(
        messages=(ChatMessage.system("Be brief."), ChatMessage.user("Hello?")), max_tokens=256
    )


def completion(model: str, content: str, **extra: Any) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": model,
            "choices": [{"message": {"content": content, **extra}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    )


def body(route: respx.Route) -> dict[str, Any]:
    sent: dict[str, Any] = json.loads(route.calls.last.request.content)
    return sent


def stack_with(harbor_key: str | None) -> LlmStack:
    return assemble_llm_stack(settings(harbor_key=harbor_key))


async def test_tokenharbor_answers_first_with_its_own_url_and_key(
    respx_mock: respx.Router,
) -> None:
    harbor = respx_mock.post(HARBOR_URL).mock(
        # The live shape: the served id has no ":free", and thinking is in reasoning_content.
        return_value=completion("deepseek-v4.1-flash", "Hi.", reasoning_content="thinking")
    )
    factory = respx_mock.post(FACTORY_URL)
    stack = stack_with(HARBOR_KEY)
    try:
        result = await stack.gateway.complete(Role.CHAT, request())
    finally:
        await stack.aclose()
    assert result.model == TOKENHARBOR_MODEL
    assert result.served_model == "deepseek-v4.1-flash"
    assert result.content == "Hi."
    assert result.reasoning == "thinking"
    assert result.points is None  # no Token Factory pricing: points unknown
    assert not factory.calls
    assert harbor.calls.last.request.headers["authorization"] == f"Bearer {HARBOR_KEY}"
    assert body(harbor)["model"] == TOKENHARBOR_MODEL
    assert "reasoning_effort" not in body(harbor)


@pytest.mark.parametrize(
    "harbor_reply",
    [
        httpx.Response(500, json={"error": {"message": "upstream failed"}}),
        httpx.Response(429, json={"error": {"message": "rate limited"}}),
        httpx.Response(401, json={"error": {"message": "bad key"}}),
        httpx.ReadTimeout("timed out"),
        httpx.ConnectError("refused"),
    ],
    ids=["500", "429", "401", "timeout", "transport"],
)
async def test_any_tokenharbor_failure_falls_back_to_token_factory(
    respx_mock: respx.Router, harbor_reply: httpx.Response | Exception
) -> None:
    harbor = respx_mock.post(HARBOR_URL).mock(side_effect=[harbor_reply])
    factory = respx_mock.post(FACTORY_URL).mock(
        return_value=completion("Qwen3.8-Flash-Next", "Hello.")
    )
    stack = stack_with(HARBOR_KEY)
    try:
        result = await stack.gateway.complete(Role.CHAT, request())
    finally:
        await stack.aclose()
    assert harbor.call_count == 1  # no retry on TokenHarbor: straight to the fallback
    assert result.model == "Qwen3.8-Flash-Next"
    assert body(factory)["model"] == "Qwen3.8-Flash-Next"
    assert factory.calls.last.request.headers["authorization"] == f"Bearer {PLACEHOLDER_KEY}"


async def test_a_tokenharbor_stream_failure_falls_back_to_token_factory(
    respx_mock: respx.Router,
) -> None:
    respx_mock.post(HARBOR_URL).mock(return_value=httpx.Response(503))
    stream = (
        'data: {"model":"Qwen3.8-Flash-Next","choices":[{"delta":{"content":"Hi"}}]}\n\n'
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        "data: [DONE]\n\n"
    )
    respx_mock.post(FACTORY_URL).mock(
        return_value=httpx.Response(
            200, content=stream.encode(), headers={"content-type": "text/event-stream"}
        )
    )
    stack = stack_with(HARBOR_KEY)
    try:
        items = [item async for item in stack.gateway.stream(Role.CHAT, request())]
    finally:
        await stack.aclose()
    final = items[-1]
    assert isinstance(final, ChatResult)
    assert final.model == "Qwen3.8-Flash-Next"


async def test_without_a_tokenharbor_key_the_chain_starts_at_token_factory(
    respx_mock: respx.Router,
) -> None:
    harbor = respx_mock.post(HARBOR_URL)
    factory = respx_mock.post(FACTORY_URL).mock(
        return_value=completion("Qwen3.8-Flash-Next", "Hello.")
    )
    stack = stack_with(None)
    try:
        assert stack.harbor_client is None
        for role in (Role.INVESTIGATOR, Role.WRITER, Role.CHAT, Role.ROUTER):
            usable = stack.registry.resolve(role).usable
            assert all(r.choice.model != TOKENHARBOR_MODEL for r in usable)
        assert stack.registry.resolve(Role.CHAT).skipped == ()  # skipped silently
        result = await stack.gateway.complete(Role.CHAT, request())
    finally:
        await stack.aclose()
    assert result.model == "Qwen3.8-Flash-Next"
    assert not harbor.calls
    assert factory.call_count == 1


def test_tokenharbor_goes_first_on_every_text_role_but_the_writer() -> None:
    stack = stack_with(HARBOR_KEY)
    for role in (Role.INVESTIGATOR, Role.VERIFIER, Role.CHAT, Role.ROUTER):
        assert stack.registry.resolve(role).usable[0].choice.model == TOKENHARBOR_MODEL
    assert stack.registry.resolve(Role.WRITER).usable[0].choice.model == "Qwen3.8-Flash-Next"
    models = [r.choice.model for r in stack.registry.resolve(Role.VERIFIER).usable]
    assert models == [TOKENHARBOR_MODEL, "GLM-5.3-Flash", "DeepSeek-V4-Flash"]


async def test_tokenharbor_gets_a_thinking_budget_and_a_cut_off_tool_call_falls_back(
    respx_mock: respx.Router,
) -> None:
    cut = {"id": "c1", "type": "function", "function": {"name": "get_run", "arguments": '{"ru'}}
    harbor = respx_mock.post(HARBOR_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "deepseek-v4.1-flash",
                "choices": [
                    {
                        "message": {"content": None, "tool_calls": [cut]},
                        "finish_reason": "length",
                    }
                ],
            },
        )
    )
    respx_mock.post(FACTORY_URL).mock(return_value=completion("Qwen3.8-Flash-Next", "Hello."))
    stack = stack_with(HARBOR_KEY)
    try:
        result = await stack.gateway.complete(Role.CHAT, request())
    finally:
        await stack.aclose()
    assert body(harbor)["max_tokens"] == 8192
    assert result.model == "Qwen3.8-Flash-Next"


async def test_malformed_tool_arguments_in_history_are_sent_as_a_json_object(
    respx_mock: respx.Router,
) -> None:
    # One model's broken tool call must not make every fallback answer HTTP 400.
    factory = respx_mock.post(FACTORY_URL).mock(
        return_value=completion("Qwen3.8-Flash-Next", "Hello.")
    )
    broken = ToolCall(id="c1", function=FunctionCall(name="get_run", arguments="{run_id: 'x'"))
    good = ToolCall(id="c2", function=FunctionCall(name="get_run", arguments='{"run_id": "x"}'))
    req = ChatRequest(
        messages=(
            ChatMessage.user("Hello?"),
            ChatMessage(role="assistant", content=None, tool_calls=(broken, good)),
            ChatMessage(role="tool", tool_call_id="c1", content="refused"),
            ChatMessage(role="tool", tool_call_id="c2", content="ok"),
        ),
        max_tokens=256,
    )
    stack = stack_with(None)
    try:
        await stack.gateway.complete(Role.CHAT, req)
    finally:
        await stack.aclose()
    calls = body(factory)["messages"][1]["tool_calls"]
    assert [c["function"]["arguments"] for c in calls] == ["{}", '{"run_id": "x"}']


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


async def test_openrouter_answers_first_and_a_402_falls_back_to_the_next_provider(
    respx_mock: respx.Router,
) -> None:
    # The live shape of a busy free model: HTTP 429, then TokenHarbor answers.
    router = respx_mock.post(OPENROUTER_URL).mock(
        return_value=httpx.Response(
            429, json={"error": {"message": "temporarily rate-limited upstream"}}
        )
    )
    harbor = respx_mock.post(HARBOR_URL).mock(return_value=completion("deepseek-v4.1-flash", "Hi."))
    stack = assemble_llm_stack(
        settings(harbor_key=HARBOR_KEY).model_copy(
            update={"openrouter_api_key": SecretStr("or-placeholder-not-a-key")}
        )
    )
    try:
        assert (
            stack.registry.resolve(Role.CHAT).usable[0].choice.model == "google/gemma-4-31b-it:free"
        )
        result = await stack.gateway.complete(Role.CHAT, request())
    finally:
        await stack.aclose()
    assert router.call_count == 1
    assert harbor.call_count == 1
    assert result.model == TOKENHARBOR_MODEL
    assert router.calls.last.request.headers["authorization"] == "Bearer or-placeholder-not-a-key"
    assert body(router)["model"] == "google/gemma-4-31b-it:free"
    assert "reasoning_effort" not in body(router)


async def test_openrouter_answers_when_it_works(respx_mock: respx.Router) -> None:
    router = respx_mock.post(OPENROUTER_URL).mock(
        return_value=completion("google/gemma-4-31b-it:free", "Hello from OpenRouter.")
    )
    stack = assemble_llm_stack(
        settings(harbor_key=None).model_copy(
            update={"openrouter_api_key": SecretStr("or-placeholder-not-a-key")}
        )
    )
    try:
        result = await stack.gateway.complete(Role.INVESTIGATOR, request())
    finally:
        await stack.aclose()
    assert result.model == "google/gemma-4-31b-it:free"
    assert router.call_count == 1
