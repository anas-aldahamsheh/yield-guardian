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
from yield_guardian.llm.messages import ChatMessage, ChatRequest
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


def test_the_verifier_never_uses_tokenharbor() -> None:
    stack = stack_with(HARBOR_KEY)
    models = [r.choice.model for r in stack.registry.resolve(Role.VERIFIER).usable]
    assert models == ["GLM-5.3-Flash", "DeepSeek-V4-Flash"]
    assert stack.registry.resolve(Role.CHAT).usable[0].choice.model == TOKENHARBOR_MODEL
