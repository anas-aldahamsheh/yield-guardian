"""The investigator on the Postgres checkpointer: a paused investigation survives a restart.

Needs TEST_DATABASE_URL (skipped otherwise, like the other database tests); model replies are
scripted and the fixture values are SYNTHETIC.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
import respx
from pydantic import SecretStr

from tests.agent.helpers import FakeScience, RecordingSink, ScriptedModel, json_reply, text_reply
from tests.agent.test_agent_graph import GOOD_REPORT, PLAN_EVIDENCE, SUPPORTED, UNIT
from tests.db.conftest import temporary_database
from tests.llm.helpers import PLACEHOLDER_KEY
from yield_guardian.agent.graph import InvestigatorRunner
from yield_guardian.agent.wiring import AgentResource, install_agent
from yield_guardian.contracts.investigation import Decision
from yield_guardian.contracts.services import KnowledgeService, SecomService, WaferService
from yield_guardian.core.settings import Settings
from yield_guardian.services.registry import ServiceRegistry

INV = "inv_00000000db01"


@pytest.fixture(scope="module")
def checkpoint_url() -> Iterator[str]:
    with temporary_database(migrate=False) as url:
        yield url


def started_registry(url: str, tmp_path: Path) -> tuple[ServiceRegistry, AgentResource]:
    settings = Settings(
        environment="test",
        log_json=False,
        database_url=SecretStr(url),
        artifacts_dir=tmp_path,
        token_factory_api_key=SecretStr(PLACEHOLDER_KEY),
    )
    registry = ServiceRegistry(settings=settings)
    science = FakeScience()
    registry.secom = cast(SecomService, science.secom)
    registry.wafer = cast(WaferService, science.wafer)
    registry.knowledge = cast(KnowledgeService, science.knowledge)
    resource = install_agent(registry, settings)
    assert resource is not None
    return registry, resource


async def test_a_paused_investigation_resumes_after_a_restart(
    checkpoint_url: str, tmp_path: Path, respx_mock: respx.Router
) -> None:
    model = ScriptedModel().mount(respx_mock)
    model.add("investigator", PLAN_EVIDENCE, text_reply("READY"))
    model.add("writer", json_reply(GOOD_REPORT))
    model.add("verifier", json_reply(SUPPORTED))

    registry, resource = started_registry(checkpoint_url, tmp_path)
    await resource.start()
    assert "investigator" not in registry.problems
    assert "investigation_checkpoints" not in registry.problems
    runner = registry.runner
    assert isinstance(runner, InvestigatorRunner)
    sink = RecordingSink()
    await runner.run(INV, UNIT, sink)
    assert sink.statuses == ["running", "awaiting_decision"]
    await resource.stop()

    registry, resource = started_registry(checkpoint_url, tmp_path)
    await resource.start()
    restarted = registry.runner
    assert isinstance(restarted, InvestigatorRunner)
    assert await restarted.waiting_for_decision(INV)
    decision = Decision(
        verdict="approve",
        actions=[0],
        note=None,
        decided_by="engineer@example.test",
        decided_at=datetime(2026, 10, 14, 13, 0, tzinfo=UTC),
    )
    resumed = RecordingSink()
    await restarted.resume(INV, decision, resumed)
    assert resumed.of("error") == []
    assert [(s.node, s.status) for s in resumed.steps] == [("decision", "completed")]
    state = await restarted.graph.aget_state(restarted.config(INV))
    assert state.values["decision"]["verdict"] == "approve"
    assert len(state.values["evidence"]) == 3
    assert not await restarted.waiting_for_decision(INV)
    await resource.stop()
    assert model.remaining() == {}
