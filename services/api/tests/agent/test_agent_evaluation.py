"""The evaluation harness, offline: task sets, the Wilson interval, the cost bound, scoring of
scripted answers, and the script's refusals. Every model answer here is scripted for the test;
no request reaches Token Factory."""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import httpx
import pytest
import respx

from tests.agent.helpers import USAGE, ScriptedModel, json_reply, text_reply
from tests.llm.helpers import PLACEHOLDER_KEY, make_stack
from yield_guardian.agent.evaluation import (
    EvaluationError,
    RouterTaskSet,
    VerifierTaskSet,
    estimate_cost,
    evaluated_choice,
    load_task_set,
    parse_task_set,
    prepared,
    run_task_set,
    single_model_registry,
    task_requests,
    wilson,
)
from yield_guardian.agent.router import INTENTS
from yield_guardian.llm.profiles import DOCUMENTED_PROFILES, ProfileCatalog, Usage
from yield_guardian.llm.registry import Role
from yield_guardian.llm.request_builder import build_chat_request

ROOT = Path(__file__).resolve().parents[2]
TASK_SETS = ROOT / "scripts" / "evaluation"
SCRIPT = ROOT / "scripts" / "run_evaluation.py"
ROUTER_MODEL = "MiniCPM5-2B"
VERIFIER_MODEL = "GLM-5.3-Flash"
RUN_AT = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)

ROUTER_SET = {
    "name": "router-test",
    "role": "router",
    "description": "test cases",
    "tasks": [
        {"id": "a", "question": "How likely is unit 5 to fail?", "expected": "unit_risk"},
        {"id": "b", "question": "Tell me a joke", "expected": "out_of_scope"},
        {"id": "c", "question": "Which sensors are dead?", "expected": "sensor_health"},
    ],
}
EVIDENCE = {
    "evidence_id": "E1",
    "tool": "get_risk",
    "arguments": {"unit_id": 5},
    "data": {"unit_id": 5, "probability": 0.5},
    "summary": "synthetic test evidence",
}
VERIFIER_SET = {
    "name": "verifier-test",
    "role": "verifier",
    "description": "test cases",
    "tasks": [
        {
            "id": "a",
            "summary": "s",
            "evidence": [EVIDENCE],
            "findings": [
                {"claim": "c1", "evidence_ids": ["E1"], "strength": "weak", "expected": "supported"},
                {"claim": "c2", "evidence_ids": ["E1"], "strength": "weak", "expected": "not_supported"},
            ],
        },
        {
            "id": "b",
            "summary": "s",
            "evidence": [EVIDENCE],
            "findings": [
                {"claim": "c3", "evidence_ids": ["E1"], "strength": "weak", "expected": "supported"},
            ],
        },
    ],
}  # fmt: skip


def router_set() -> RouterTaskSet:
    task_set = parse_task_set(json.dumps(ROUTER_SET))
    assert isinstance(task_set, RouterTaskSet)
    return task_set


def verifier_set() -> VerifierTaskSet:
    task_set = parse_task_set(json.dumps(VERIFIER_SET))
    assert isinstance(task_set, VerifierTaskSet)
    return task_set


# -- Wilson interval ----------------------------------------------------------------------------


def test_wilson_matches_the_textbook_values() -> None:
    estimate = wilson(8, 10)
    assert estimate.value == pytest.approx(0.8)
    assert estimate.ci_low == pytest.approx(0.4902, abs=1e-4)
    assert estimate.ci_high == pytest.approx(0.9433, abs=1e-4)
    assert (estimate.n, estimate.ci_level, estimate.method) == (10, 0.95, "Wilson score interval")


def test_wilson_stays_inside_zero_and_one_at_the_extremes() -> None:
    none, every = wilson(0, 12), wilson(12, 12)
    assert none.ci_low == 0.0
    assert none.ci_high is not None
    assert 0 < none.ci_high < 0.3
    assert every.ci_high == 1.0
    assert every.ci_low is not None
    assert 0.7 < every.ci_low < 1


@pytest.mark.parametrize(("successes", "n"), [(0, 0), (3, 2), (-1, 4)])
def test_wilson_refuses_impossible_counts(successes: int, n: int) -> None:
    with pytest.raises(EvaluationError):
        wilson(successes, n)


# -- task sets ----------------------------------------------------------------------------------


@pytest.mark.parametrize("path", sorted(TASK_SETS.glob("*.json")), ids=lambda p: p.name)
def test_shipped_task_sets_are_valid_and_say_they_are_hand_written(path: Path) -> None:
    task_set = load_task_set(path)
    assert "Hand-written" in task_set.description
    assert len(task_set.tasks) >= 10


def test_the_shipped_router_set_covers_every_intent() -> None:
    task_set = load_task_set(TASK_SETS / "router_intents.json")
    assert isinstance(task_set, RouterTaskSet)
    assert {t.expected for t in task_set.tasks} == set(INTENTS)


def test_a_task_set_with_repeated_ids_is_refused() -> None:
    data = {**ROUTER_SET, "tasks": [ROUTER_SET["tasks"][0], ROUTER_SET["tasks"][0]]}
    with pytest.raises(EvaluationError, match="repeat"):
        parse_task_set(json.dumps(data))


def test_a_finding_citing_unknown_evidence_is_refused() -> None:
    task = json.loads(json.dumps(VERIFIER_SET["tasks"][0]))
    task["findings"][0]["evidence_ids"] = ["E9"]
    with pytest.raises(EvaluationError, match="unknown evidence E9"):
        parse_task_set(json.dumps({**VERIFIER_SET, "tasks": [task]}))


def test_an_unknown_intent_is_refused() -> None:
    task = {"id": "x", "question": "q", "expected": "launch_rocket"}
    with pytest.raises(ValueError):
        parse_task_set(json.dumps({**ROUTER_SET, "tasks": [task]}))


# -- the model and the cost bound ---------------------------------------------------------------


async def test_the_registry_holds_the_evaluated_model_alone() -> None:
    registry = await single_model_registry(Role.ROUTER, ROUTER_MODEL, ProfileCatalog())
    assert [c.model for c in registry.assignment(Role.ROUTER).chain] == [ROUTER_MODEL]


@pytest.mark.parametrize(
    ("role", "model", "message"),
    [
        (Role.ROUTER, "No-Such-Model", "not a documented model"),
        (Role.CHAT, ROUTER_MODEL, "no scored task sets"),
        (Role.VERIFIER, "MiMo-V2.6-Flash", "cannot serve the verifier role"),
    ],
)
async def test_a_model_the_role_cannot_use_is_refused(role: Role, model: str, message: str) -> None:
    with pytest.raises(EvaluationError, match=message):
        await single_model_registry(role, model, ProfileCatalog())


def test_the_cost_bound_counts_every_request_byte_and_every_output_token() -> None:
    catalog = ProfileCatalog()
    task_set = router_set()
    estimate = estimate_cost(task_set, ROUTER_MODEL, catalog)
    profile = DOCUMENTED_PROFILES[ROUTER_MODEL]
    assert profile.pricing is not None
    entry = evaluated_choice(Role.ROUTER, ROUTER_MODEL, catalog)
    sizes = 0
    for _, request, output in task_requests(task_set):
        body = build_chat_request(profile, prepared(request, entry, output)).body
        sizes += len(json.dumps(body, ensure_ascii=False).encode())
        assert body["model"] == ROUTER_MODEL
    assert estimate.prompt_bytes == sizes
    assert estimate.calls == 3
    assert estimate.max_output_tokens == 3 * 128
    expected = (sizes * profile.pricing.input_per_mtok + 384 * profile.pricing.output_per_mtok) / 1e6  # fmt: skip
    assert estimate.points_upper_bound == pytest.approx(expected)
    assert estimate.points_upper_bound > 0


def test_the_cost_bound_is_above_what_a_scripted_run_reports() -> None:
    """With the scripted usage (120 prompt, 30 completion tokens per call), the bound holds."""
    estimate = estimate_cost(verifier_set(), VERIFIER_MODEL, ProfileCatalog())
    pricing = DOCUMENTED_PROFILES[VERIFIER_MODEL].pricing
    assert pricing is not None
    per_call = pricing.points(
        Usage(prompt_tokens=USAGE["prompt_tokens"], completion_tokens=USAGE["completion_tokens"])
    )
    assert per_call is not None
    assert estimate.points_upper_bound > 2 * per_call


# -- runs on scripted answers -------------------------------------------------------------------


async def test_router_answers_are_scored_against_the_expected_intent(
    respx_mock: respx.Router,
) -> None:
    stack = make_stack()
    stack.gateway.registry = await single_model_registry(Role.ROUTER, ROUTER_MODEL, stack.catalog)
    model = ScriptedModel().mount(respx_mock)
    model.add(
        "router",
        json_reply({"intent": "unit_risk"}),
        json_reply({"intent": "general"}),
        text_reply("not json at all"),
    )
    run = await run_task_set(stack.gateway, router_set(), ROUTER_MODEL, wall_clock=lambda: RUN_AT)
    assert [(o.success, o.violation) for o in run.outcomes] == [(True, False), (False, False), (False, True)]  # fmt: skip
    result = run.result
    assert (result.role, result.model_id, result.task_set) == (
        "router",
        ROUTER_MODEL,
        "router-test",
    )
    assert (result.tasks, result.violations, result.run_at) == (3, 1, RUN_AT)
    assert result.success_rate.value == pytest.approx(1 / 3)
    assert result.success_rate.n == 3
    assert result.tokens_in == 3 * 120
    assert result.tokens_out == 3 * 30
    assert result.points > 0
    assert result.latency_ms_p50 is not None
    assert {b["model"] for b in model.bodies("router")} == {ROUTER_MODEL}
    assert "hand-written" in (result.success_rate.note or "")
    assert run.calls_without_usage == 0
    assert model.remaining() == {}


async def test_the_cache_is_bypassed_so_each_task_is_a_fresh_answer(
    respx_mock: respx.Router,
) -> None:
    stack = make_stack()
    stack.gateway.registry = await single_model_registry(Role.ROUTER, ROUTER_MODEL, stack.catalog)
    model = ScriptedModel().mount(respx_mock)
    twice = parse_task_set(json.dumps({**ROUTER_SET, "tasks": [ROUTER_SET["tasks"][0]]}))
    model.add("router", json_reply({"intent": "unit_risk"}), json_reply({"intent": "general"}))
    first = await run_task_set(stack.gateway, twice, ROUTER_MODEL)
    second = await run_task_set(stack.gateway, twice, ROUTER_MODEL)
    assert (first.outcomes[0].success, second.outcomes[0].success) == (True, False)


async def test_verifier_verdicts_are_scored_per_finding(respx_mock: respx.Router) -> None:
    stack = make_stack()
    stack.gateway.registry = await single_model_registry(
        Role.VERIFIER, VERIFIER_MODEL, stack.catalog
    )
    model = ScriptedModel().mount(respx_mock)
    model.add(
        "verifier",
        json_reply(
            {
                "claims": [
                    {"finding_index": 0, "verdict": "supported", "note": "ok"},
                    {"finding_index": 1, "verdict": "partially_supported", "note": "partly"},
                ]
            }
        ),
        json_reply({"claims": []}),  # no verdict for the only finding: a violation
    )
    run = await run_task_set(stack.gateway, verifier_set(), VERIFIER_MODEL)
    first, second = run.outcomes
    assert (first.success, first.violation, first.answer) == (
        True,
        False,
        "supported,not_supported",
    )
    assert (second.success, second.violation, second.answer) == (False, True, "no_verdict")
    assert run.result.violations == 1
    assert run.result.success_rate.value == pytest.approx(0.5)


async def test_a_run_refuses_a_gateway_whose_chain_has_other_models() -> None:
    stack = make_stack()  # default router chain: two models
    with pytest.raises(EvaluationError, match="alone"):
        await run_task_set(stack.gateway, router_set(), ROUTER_MODEL)


async def test_unreported_usage_is_counted_not_guessed(respx_mock: respx.Router) -> None:
    stack = make_stack()
    stack.gateway.registry = await single_model_registry(Role.ROUTER, ROUTER_MODEL, stack.catalog)
    body = json_reply({"intent": "unit_risk"}).json()
    del body["usage"]
    model = ScriptedModel().mount(respx_mock)
    model.add("router", httpx.Response(200, json=body))
    single = parse_task_set(json.dumps({**ROUTER_SET, "tasks": [ROUTER_SET["tasks"][0]]}))
    run = await run_task_set(stack.gateway, single, ROUTER_MODEL)
    assert run.calls_without_usage == 1
    assert (run.result.tokens_in, run.result.tokens_out, run.result.points) == (0, 0, 0)
    assert "1 call(s) reported no usage" in (run.result.success_rate.note or "")
    assert run.to_json()["calls_without_usage"] == 1


# -- the script ---------------------------------------------------------------------------------


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_evaluation", SCRIPT)
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


@pytest.mark.parametrize(
    ("environ", "argv", "message", "estimate_shown"),
    [
        ({"CI": "true", "TOKEN_FACTORY_API_KEY": PLACEHOLDER_KEY}, ["--confirm"], "refusing to run in CI", False),
        ({}, ["--confirm"], "TOKEN_FACTORY_API_KEY is not set", True),
        ({"TOKEN_FACTORY_API_KEY": PLACEHOLDER_KEY}, [], "add --confirm", True),
    ],
)  # fmt: skip
def test_the_script_refuses_without_every_condition(
    clean_env: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    respx_mock: respx.Router,
    environ: dict[str, str],
    argv: list[str],
    message: str,
    estimate_shown: bool,
) -> None:
    for name, value in environ.items():
        clean_env.setenv(name, value)
    task_set = str(TASK_SETS / "router_intents.json")
    assert load_script().main([task_set, "--model", ROUTER_MODEL, *argv]) == 2
    out = capsys.readouterr()
    assert message in out.err
    assert ("Upper bound for this run" in out.out) is estimate_shown
    assert not respx_mock.calls


def test_the_script_refuses_a_model_without_a_bound(
    clean_env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], respx_mock: respx.Router
) -> None:
    task_set = str(TASK_SETS / "router_intents.json")
    assert load_script().main([task_set, "--model", "No-Such-Model"]) == 2
    assert "not a documented model" in capsys.readouterr().err
    assert not respx_mock.calls


def test_the_confirmed_script_runs_and_writes_the_result(
    clean_env: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    respx_mock: respx.Router,
    tmp_path: Path,
) -> None:
    clean_env.setenv("TOKEN_FACTORY_API_KEY", PLACEHOLDER_KEY)
    path = tmp_path / "set.json"
    path.write_text(json.dumps(ROUTER_SET), encoding="utf-8")
    out = tmp_path / "result.json"
    model = ScriptedModel().mount(respx_mock)
    model.add("router", *(json_reply({"intent": "unit_risk"}) for _ in range(3)))
    code = load_script().main([str(path), "--model", ROUTER_MODEL, "--confirm", "--out", str(out)])
    assert code == 0
    assert "Upper bound for this run" in capsys.readouterr().out
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["result"]["tasks"] == 3
    assert written["result"]["success_rate"]["value"] == pytest.approx(1 / 3)
    assert [o["success"] for o in written["outcomes"]] == [True, False, False]
    assert len(model.bodies("router")) == 3
