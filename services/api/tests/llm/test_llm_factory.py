"""Wiring from settings: no key means no network at all; a key means one catalog read."""

from __future__ import annotations

import respx
from pydantic import SecretStr

from tests.llm.helpers import PLACEHOLDER_KEY, mount
from yield_guardian.core.settings import Settings
from yield_guardian.llm.factory import build_llm_stack, key_configured
from yield_guardian.llm.profiles import Availability
from yield_guardian.llm.registry import Role


def settings(key: str | None) -> Settings:
    return Settings(
        environment="test",
        log_json=False,
        token_factory_api_key=SecretStr(key) if key is not None else None,
    )


def test_key_configured_ignores_blank_keys() -> None:
    assert key_configured(settings(PLACEHOLDER_KEY))
    assert not key_configured(settings(None))
    assert not key_configured(settings("   "))


async def test_without_a_key_the_stack_makes_no_request(respx_mock: respx.Router) -> None:
    stack = await build_llm_stack(settings(None))
    try:
        assert not await stack.admin.live_calls_available()
        assert stack.catalog.availability("GLM-5.3-Flash") is Availability.NOT_SYNCED
        assert stack.registry.assignment(Role.WRITER).primary.model == "Qwen3.8-Flash-Next"
        assert (await stack.admin.usage()).quota.source == "unknown"
        assert not respx_mock.calls
    finally:
        await stack.aclose()


async def test_with_a_key_the_catalog_is_read_once_at_startup(respx_mock: respx.Router) -> None:
    player = mount(respx_mock, "catalog_and_usage")
    stack = await build_llm_stack(settings(PLACEHOLDER_KEY))
    try:
        assert await stack.admin.live_calls_available()
        assert len(player.requests) == 1
        assert player.requests[0].url.path.endswith("/models")
        assert stack.catalog.availability("Gemma-4-31B-IT") is Availability.WITHDRAWN
        assert stack.catalog.require("MiniCPM-V-4.7-1B").source == "catalog_only"
        report = await stack.admin.usage()  # the Models page reads /v1/usage on demand
        assert report.quota.source == "usage_endpoint"
        assert report.quota.remaining == 0.75
        player.assert_done()
    finally:
        await stack.aclose()
