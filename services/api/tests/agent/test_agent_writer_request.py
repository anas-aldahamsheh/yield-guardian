"""The exact writer request each writer-chain model receives, checked against the constraints
we know (or suspect) the Token Factory applies.

The first live writer call on MiMo-V2.6-Flash answered HTTP 400 and Qwen3.8-27B ran out of
max_tokens while reasoning. The L10 evaluation only ever sent json_object (router on MiniCPM5-2B,
verifier on GLM-5.3-Flash), so strict json_schema has never been accepted live. These tests pin
the request shape to the conservative subset: documented parameters only, documented efforts
only, a flat schema without the features strict-mode servers commonly reject, and enough
max_tokens for a thinking model to finish its reasoning and the JSON.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx

from tests.agent.helpers import evidence
from tests.llm.helpers import HOST, make_stack
from yield_guardian.agent.writer import REPORT_SCHEMA_NAME, ReportWriter, WriterInput
from yield_guardian.contracts.investigation import InvestigationTrigger, Report
from yield_guardian.llm.gateway import CallOptions
from yield_guardian.llm.profiles import DOCUMENTED_PROFILES
from yield_guardian.llm.registry import DEFAULT_CHAINS, ModelChoice, ResponseMode, Role
from yield_guardian.llm.structured import strict_json_schema

TRIGGER = InvestigationTrigger(kind="alarm", ref="AL-1303-risk", question=None)
E1 = evidence("E1", {"unit_id": 1303, "risk": 0.41}, unit_id=1303)
REPORT: dict[str, Any] = {
    "summary": "Unit 1303 has a risk of 0.41.",
    "findings": [{"claim": "Risk is 0.41.", "evidence_ids": ["E1"], "strength": "moderate"}],
    "actions": [{"action": "Review unit 1303.", "rationale": "Its risk.", "evidence_ids": ["E1"]}],
    "numbers": [
        {"value": 0.41, "as_written": "0.41", "unit": None, "evidence_id": "E1", "path": "/risk"}
    ],
    "limitations": ["Association only."],
}

ACCEPTED_PARAMETERS = frozenset(
    {
        "model",
        "messages",
        "stream",
        "temperature",
        "top_p",
        "max_tokens",
        "presence_penalty",
        "frequency_penalty",
        "response_format",
        "tools",
        "tool_choice",
        "parallel_tool_calls",
        "reasoning_effort",
    }
)
VERIFIED_EFFORTS: dict[str, frozenset[str]] = {
    # The one value the docs name for MiMo ("none turns thinking off"); "low" was never verified
    # and the first live writer request with it answered 400.
    "MiMo-V2.6-Flash": frozenset({"none"}),
    # Documented for Qwen3.8-27B; it cannot switch thinking off.
    "Qwen3.8-27B": frozenset({"low", "medium", "xhigh"}),
}
UNSUPPORTED_SCHEMA_KEYS = frozenset(
    {
        "$ref",
        "$defs",
        "definitions",
        "oneOf",
        "allOf",
        "not",
        "if",
        "then",
        "else",
        "const",
        "pattern",
        "format",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minItems",
        "maxItems",
        "uniqueItems",
        "patternProperties",
        "default",
        "examples",
    }
)
MAX_ENUM_VALUES = 20
MAX_SCHEMA_BYTES = 8_000
MAX_SCHEMA_DEPTH = 5
THINKING_MIN_TOKENS = 8_192
WRITER_CHAIN = DEFAULT_CHAINS[Role.WRITER]


def walk(node: Any, depth: int = 0) -> Iterator[tuple[dict[str, Any], int]]:
    if isinstance(node, dict):
        yield node, depth
        for key, value in node.items():
            if key in ("properties",) and isinstance(value, dict):
                for child in value.values():
                    yield from walk(child, depth + 1)
            elif key in ("items", "anyOf"):
                children = value if isinstance(value, list) else [value]
                for child in children:
                    yield from walk(child, depth + (1 if key == "items" else 0))


def schema_problems(schema: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    size = len(json.dumps(schema, separators=(",", ":")))
    if size > MAX_SCHEMA_BYTES:
        problems.append(f"schema is {size} bytes")
    for node, depth in walk(schema):
        if depth > MAX_SCHEMA_DEPTH:
            problems.append(f"nesting depth {depth}")
        bad = UNSUPPORTED_SCHEMA_KEYS & node.keys()
        if bad:
            problems.append(f"unsupported keys {sorted(bad)}")
        if len(node.get("enum", ())) > MAX_ENUM_VALUES:
            problems.append(f"enum with {len(node['enum'])} values")
        for option in node.get("anyOf", ()):
            if "anyOf" in option:
                problems.append("nested anyOf")
        if node.get("type") == "object" or "properties" in node:
            if node.get("additionalProperties") is not False:
                problems.append(f"object without additionalProperties=false: {sorted(node)}")
            if sorted(node.get("required", ())) != sorted(node.get("properties", {})):
                problems.append("not every property is required")
    return problems


@pytest.mark.parametrize("choice", WRITER_CHAIN, ids=[c.model for c in WRITER_CHAIN])
async def test_each_writer_model_gets_a_request_inside_the_known_constraints(
    respx_mock: respx.Router, choice: ModelChoice
) -> None:
    stack = make_stack()
    await stack.registry.assign(Role.WRITER, [choice], actor="test")
    route = respx_mock.post(host=HOST).mock(
        return_value=httpx.Response(
            200,
            json={
                "model": choice.model,
                "choices": [{"message": {"content": json.dumps(REPORT)}, "finish_reason": "stop"}],
            },
        )
    )
    out = await ReportWriter(stack.gateway).write(WriterInput(TRIGGER, [E1]), options=CallOptions())
    assert out.value == Report.model_validate(REPORT)
    (call,) = route.calls
    body: dict[str, Any] = json.loads(call.request.content)
    profile = DOCUMENTED_PROFILES[choice.model]

    assert body["model"] == choice.model
    assert set(body) <= ACCEPTED_PARAMETERS, set(body) - ACCEPTED_PARAMETERS
    for absent in ("temperature", "top_p", "tools", "tool_choice", "stream"):
        assert absent not in body
    assert body["reasoning_effort"] in VERIFIED_EFFORTS[choice.model]
    assert body["reasoning_effort"] in profile.reasoning_efforts
    if profile.thinks_by_default and body["reasoning_effort"] != "none":
        assert body["max_tokens"] >= THINKING_MIN_TOKENS
    assert body["max_tokens"] < profile.context_length

    roles = [m["role"] for m in body["messages"]]
    assert roles == ["system", "user"]  # also fits Qwen's one-system-message-first rule

    fmt = body["response_format"]
    if choice.response_mode is ResponseMode.JSON_SCHEMA:
        assert profile.supports_json_schema
        assert set(fmt) == {"type", "json_schema"}
        assert fmt["type"] == "json_schema"
        spec = fmt["json_schema"]
        assert set(spec) == {"name", "schema", "strict"}
        assert spec["name"] == REPORT_SCHEMA_NAME
        assert spec["strict"] is True
        assert schema_problems(spec["schema"]) == []
    else:
        assert profile.supports_json_object
        assert fmt == {"type": "json_object"}
        assert "JSON" in body["messages"][0]["content"]  # json_object needs "JSON" in the prompt


def test_the_report_schema_stays_inside_the_strict_subset() -> None:
    schema = strict_json_schema(Report)
    assert schema_problems(schema) == []
    nullable = [n for n, _ in walk(schema) if "anyOf" in n]
    # The one union in the schema: an optional unit, string or null.
    assert [n["anyOf"] for n in nullable] == [[{"type": "string"}, {"type": "null"}]]


def test_the_checker_flags_what_strict_servers_reject() -> None:
    bad = {
        "type": "object",
        "properties": {
            "a": {"$ref": "#/$defs/A"},
            "b": {"type": "string", "enum": [str(i) for i in range(30)]},
            "c": {"type": "object", "properties": {"d": {"type": "string"}}},
        },
        "required": ["a"],
    }
    problems = schema_problems(bad)
    assert any("$ref" in p for p in problems)
    assert any("enum with 30" in p for p in problems)
    assert any("additionalProperties" in p for p in problems)
    assert any("required" in p for p in problems)
