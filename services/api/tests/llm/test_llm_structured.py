"""Strict JSON schemas for json_schema mode and validation of JSON answers."""

from __future__ import annotations

from typing import Any, Literal

import pytest
from pydantic import BaseModel, ConfigDict, Field

from yield_guardian.llm.errors import InvalidStructuredOutputError
from yield_guardian.llm.structured import parse_structured, strict_json_schema, strip_code_fence


class Ref(BaseModel):
    evidence_id: str = Field(pattern=r"^E\d+$", description="Cited evidence.")
    path: str


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=400)
    kind: Literal["observation", "hypothesis"]
    refs: list[Ref] = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)


class Answer(BaseModel):
    version: Literal["v1"] = "v1"
    claims: list[Claim]
    summary: Claim


def walk(node: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        found.append(node)
        for value in node.values():
            found.extend(walk(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(walk(item))
    return found


def test_strict_schema_inlines_references_and_closes_every_object() -> None:
    schema = strict_json_schema(Answer)
    nodes = walk(schema)
    assert all("$ref" not in n and "$defs" not in n for n in nodes)
    objects = [n for n in nodes if n.get("type") == "object"]
    assert len(objects) >= 4  # Answer, Claim (twice, inlined), Ref
    for obj in objects:
        assert obj["additionalProperties"] is False
        assert obj["required"] == list(obj["properties"])


def test_strict_schema_keeps_structure_and_drops_value_constraints() -> None:
    schema = strict_json_schema(Answer)
    keys = {key for node in walk(schema) for key in node}
    assert not keys & {
        "title",
        "default",
        "minLength",
        "maxLength",
        "pattern",
        "minimum",
        "minItems",
    }
    claim = schema["properties"]["claims"]["items"]
    assert claim["properties"]["kind"]["enum"] == ["observation", "hypothesis"]
    assert schema["properties"]["version"]["enum"] == ["v1"]  # const becomes enum
    nullable = claim["properties"]["confidence"]["anyOf"]
    assert {"type": "null"} in nullable
    assert claim["properties"]["refs"]["items"]["properties"]["evidence_id"]["description"]


def test_a_recursive_output_type_is_refused() -> None:
    class Recursive(BaseModel):
        child: Recursive | None = None

    with pytest.raises(ValueError, match="recursive"):
        strict_json_schema(Recursive)


@pytest.mark.parametrize(
    "text",
    [
        '{"label": "a", "count": 1}',
        '```json\n{"label": "a", "count": 1}\n```',
        '```\n{"label": "a", "count": 1}\n```  ',
        '  {"label": "a", "count": 1}  ',
    ],
)
def test_parse_structured_accepts_plain_and_fenced_json(text: str) -> None:
    class Small(BaseModel):
        label: str
        count: int

    assert parse_structured(text, Small, model="m") == Small(label="a", count=1)


@pytest.mark.parametrize(
    ("text", "detail"),
    [
        (None, "empty answer"),
        ("   ", "empty answer"),
        ("Sure! Here it is.", "not JSON"),
        ("[1, 2]", "not a JSON object"),
        ('{"label": "a"}', "count: Field required"),
        ('{"label": "a", "count": "many"}', "count: Input should be a valid integer"),
    ],
)
def test_parse_structured_reports_why_an_answer_is_invalid(text: str | None, detail: str) -> None:
    class Small(BaseModel):
        label: str
        count: int

    with pytest.raises(InvalidStructuredOutputError) as caught:
        parse_structured(text, Small, model="Fixture-Model")
    assert detail in caught.value.detail
    assert caught.value.model == "Fixture-Model"


def test_validation_still_enforces_constraints_left_out_of_the_schema() -> None:
    bad = '{"claims": [], "summary": {"text": "", "kind": "observation", "refs": [], "confidence": 2}}'
    with pytest.raises(InvalidStructuredOutputError) as caught:
        parse_structured(bad, Answer, model="m")
    assert "summary.text" in caught.value.detail


def test_strip_code_fence_leaves_unfenced_text_alone() -> None:
    assert strip_code_fence('{"a": 1}') == '{"a": 1}'
    assert strip_code_fence('```json\n{"a": 1}\n```') == '{"a": 1}'
