"""Recorded runs, offline: the paused state moves to another checkpointer and can be decided
there without any model call; the cost bound; the scripts' refusals. Model replies are
scripted and their values synthetic."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
import respx
from langgraph.checkpoint.memory import InMemorySaver

from tests.agent.helpers import FakeScience, RecordingSink
from tests.agent.test_agent_graph import INV, UNIT, decision, happy_model, runner
from tests.llm.helpers import PLACEHOLDER_KEY
from yield_guardian.agent.graph import (
    InvestigationLimits,
    initial_state,
    paused_values,
    restore_paused,
)
from yield_guardian.agent.recording import (
    UnboundedError,
    _call_bound,
    investigation_bound,
)
from yield_guardian.agent.verifier import VERIFIER_MAX_TOKENS
from yield_guardian.llm.profiles import DOCUMENTED_PROFILES, ProfileCatalog
from yield_guardian.llm.registry import InMemoryRoleAssignmentStore, ModelRegistry, Role

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


# -- paused state -------------------------------------------------------------------------------


async def test_a_paused_run_moves_to_another_host_and_is_decided_without_a_model(
    respx_mock: respx.Router,
) -> None:
    happy_model(respx_mock)
    source = InMemorySaver()
    await runner(FakeScience(), checkpointer=source).run(INV, UNIT, RecordingSink())
    state = await paused_values(source, INV)
    assert state is not None
    assert state["investigation_id"] == INV
    calls_before = len(respx_mock.calls)

    target = InMemorySaver()
    assert await restore_paused(target, INV, state)
    assert not await restore_paused(target, INV, state)  # already there: nothing changes
    assert len(respx_mock.calls) == calls_before
    moved = runner(FakeScience(), checkpointer=target)
    assert await moved.waiting_for_decision(INV)
    sink = RecordingSink()
    await moved.resume(INV, decision(), sink)
    assert sink.of("error") == []
    assert sink.statuses == []
    assert sink.final_steps()[-1].node == "decision"
    assert sink.final_steps()[-1].status == "completed"
    assert len(respx_mock.calls) == calls_before  # deciding calls no model


async def test_only_a_run_waiting_for_a_decision_has_a_paused_state() -> None:
    assert await paused_values(InMemorySaver(), INV) is None


async def test_a_state_of_another_investigation_is_refused() -> None:
    state = dict(initial_state("inv_other", UNIT))
    with pytest.raises(ValueError, match="another investigation"):
        await restore_paused(InMemorySaver(), INV, state)


# -- cost bound ---------------------------------------------------------------------------------


def test_the_bound_counts_every_chain_model_at_its_whole_context_window() -> None:
    registry = ModelRegistry(ProfileCatalog(), InMemoryRoleAssignmentStore())
    limits = InvestigationLimits()
    bound = investigation_bound(registry, limits)
    by_role = {r.role: r for r in bound.roles}
    assert by_role[Role.INVESTIGATOR].calls == limits.max_tool_steps
    assert by_role[Role.WRITER].calls == 1 + limits.max_revisions
    assert by_role[Role.VERIFIER].max_tokens == VERIFIER_MAX_TOKENS

    def expected(model: str, max_tokens: int) -> float:
        profile = DOCUMENTED_PROFILES[model]
        assert profile.pricing is not None
        assert profile.context_length is not None
        prompt = profile.context_length - max_tokens
        return (prompt * profile.pricing.input_per_mtok + max_tokens * profile.pricing.output_per_mtok) / 1e6  # fmt: skip

    writer = by_role[Role.WRITER]
    assert writer.points == pytest.approx(
        writer.calls * sum(expected(m, writer.max_tokens) for m in writer.models)
    )
    assert bound.points == pytest.approx(sum(r.points for r in bound.roles))


def test_a_model_without_a_price_cannot_be_bounded() -> None:
    profile = DOCUMENTED_PROFILES["DeepSeek-V4-Flash"].model_copy(update={"pricing": None})
    catalog = ProfileCatalog({"DeepSeek-V4-Flash": profile})
    with pytest.raises(UnboundedError):
        _call_bound(catalog, "DeepSeek-V4-Flash", 100)


# -- scripts ------------------------------------------------------------------------------------


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in ("CI", "TOKEN_FACTORY_API_KEY", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_recording_refuses_in_ci(
    clean_env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], respx_mock: respx.Router
) -> None:
    clean_env.setenv("CI", "true")
    clean_env.setenv("TOKEN_FACTORY_API_KEY", PLACEHOLDER_KEY)
    assert load("record_investigations").main(["--confirm"]) == 2
    assert "refusing to run in CI" in capsys.readouterr().err
    assert not respx_mock.calls


def test_recording_needs_the_database(
    clean_env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], respx_mock: respx.Router
) -> None:
    clean_env.setenv("TOKEN_FACTORY_API_KEY", PLACEHOLDER_KEY)
    assert load("record_investigations").main(["--confirm"]) == 2
    assert "DATABASE_URL is not set" in capsys.readouterr().err
    assert not respx_mock.calls


def test_recording_refuses_without_the_key_or_the_confirmation() -> None:
    module = load("record_investigations")
    assert module.refusal({}, confirmed=True, has_key=False) == "TOKEN_FACTORY_API_KEY is not set"
    assert "--confirm" in module.refusal({}, confirmed=False, has_key=True)
    assert module.refusal({}, confirmed=True, has_key=True) is None


@pytest.mark.parametrize(
    ("script", "argv"),
    [("import_recorded", ["export"]), ("import_evaluation", ["result.json"])],
)
def test_the_import_scripts_need_the_database(
    clean_env: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    script: str,
    argv: list[str],
) -> None:
    assert load(script).main(argv) == 2
    assert "DATABASE_URL is not set" in capsys.readouterr().err


def test_the_recorder_prints_points_from_the_reported_usage() -> None:
    from tests.agent.test_agent_graph import UNIT as TRIGGER
    from yield_guardian.contracts.investigation import Investigation

    base = {
        "investigation_id": "inv_0000000000000000000000000a",
        "title": "Unit 1062",
        "status": "failed",
        "trigger": TRIGGER.model_dump(mode="json"),
        "created_at": "2026-10-14T12:00:00Z",
        "updated_at": "2026-10-14T12:00:01Z",
        "recorded": True,
        "models": [],
        "usage": None,
        "work_order_id": None,
        "steps": [],
        "evidence": [],
        "report": None,
        "verification": None,
        "decision": None,
        "error": None,
    }
    line = load("record_investigations").usage_line
    assert "no model call was made: 0 points" in line(Investigation.model_validate(base))
    used = Investigation.model_validate(
        base
        | {
            "models": [{"role": "investigator", "model_id": "DeepSeek-V4.1-Flash"}],
            "usage": {
                "requests": 3,
                "tokens_in": 1200,
                "tokens_out": 300,
                "tokens_reasoning": 40,
                "points": 0.00123,
                "cache_hits": 0,
                "requests_without_usage": 1,
            },
        }
    )
    text = line(used)
    assert "points 0.001230" in text
    assert "1 request(s) reported no usage" in text
    assert "investigator DeepSeek-V4.1-Flash" in text
