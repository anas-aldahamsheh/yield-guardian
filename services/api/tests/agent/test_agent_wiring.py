"""Startup wiring: what is installed with and without a key, and that startup calls nothing."""

from __future__ import annotations

from pathlib import Path

import pytest
import respx
from pydantic import SecretStr

from tests.llm.helpers import PLACEHOLDER_KEY
from yield_guardian.agent.graph import InvestigatorRunner
from yield_guardian.agent.wiring import (
    MEMORY_CHECKPOINTS,
    NO_KEY,
    AgentResource,
    Unavailable,
    install_agent,
    psycopg_conninfo,
    science_services,
)
from yield_guardian.bootstrap import build_registry
from yield_guardian.contracts.services import NotReadyError
from yield_guardian.core.settings import Settings
from yield_guardian.services.registry import ServiceRegistry


def settings(tmp_path: Path, key: str | None) -> Settings:
    return Settings(
        environment="test",
        log_json=False,
        database_url=None,
        artifacts_dir=tmp_path,
        token_factory_api_key=SecretStr(key) if key is not None else None,
    )


@pytest.mark.parametrize("key", [None, "", "   "])
def test_without_a_key_nothing_is_installed_and_the_reason_is_recorded(
    tmp_path: Path, key: str | None
) -> None:
    registry = build_registry(settings(tmp_path, key))
    assert registry.llm is None
    assert registry.runner is None
    assert registry.chat is None
    assert registry.problems["llm"] == NO_KEY
    assert registry.problems["investigator"] == NO_KEY
    assert "chat" in registry.problems
    assert "knowledge" in registry.problems
    assert not [r for r in registry.resources if isinstance(r, AgentResource)]


async def test_with_a_key_the_admin_is_set_and_the_runner_starts_without_any_call(
    tmp_path: Path, respx_mock: respx.Router
) -> None:
    registry = build_registry(settings(tmp_path, PLACEHOLDER_KEY))
    assert registry.llm is not None
    assert await registry.llm.live_calls_available()
    (resource,) = [r for r in registry.resources if isinstance(r, AgentResource)]
    assert registry.resources.index(resource) == 0  # before any job worker
    await resource.start()
    assert isinstance(registry.runner, InvestigatorRunner)
    assert registry.problems["investigation_checkpoints"] == MEMORY_CHECKPOINTS
    assert "investigator" not in registry.problems
    assert respx_mock.calls.call_count == 0
    await resource.stop()
    assert registry.runner is None


async def test_a_failing_start_is_recorded_not_raised(tmp_path: Path) -> None:
    config = settings(tmp_path, PLACEHOLDER_KEY).model_copy(
        update={"database_url": SecretStr("not a url")}
    )
    registry = ServiceRegistry(settings=config)
    resource = install_agent(registry, config)
    assert resource is not None
    await resource.start()
    assert registry.runner is None
    assert "DATABASE_URL" in registry.problems["investigator"]
    await resource.stop()


async def test_missing_science_services_answer_not_ready(tmp_path: Path) -> None:
    registry = ServiceRegistry(settings=settings(tmp_path, None))
    registry.problems["secom_bundle"] = "no bundle in /artifacts"
    services = science_services(registry)
    with pytest.raises(NotReadyError, match="no bundle in /artifacts"):
        await services.secom.get_unit(1)
    with pytest.raises(NotReadyError, match="knowledge"):
        await services.knowledge.search("edge ring")
    with pytest.raises(AttributeError):
        Unavailable("x", "y").__wrapped__  # noqa: B018


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("postgresql+asyncpg://u:p@db:5432/yg", "postgresql://u:p@db:5432/yg"),
        ("postgresql+psycopg://u:p@db/yg", "postgresql://u:p@db/yg"),
        ("postgres://u@db/yg", "postgresql://u@db/yg"),
    ],
)
def test_psycopg_conninfo(url: str, expected: str) -> None:
    assert psycopg_conninfo(url) == expected


def test_psycopg_conninfo_refuses_a_non_url() -> None:
    with pytest.raises(ValueError, match="DATABASE_URL"):
        psycopg_conninfo("not a url")
