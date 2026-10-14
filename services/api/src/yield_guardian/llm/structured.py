"""Structured (JSON) output: strict schemas for ``json_schema`` and validation for both modes.

MiMo-V2.6-Flash is the only model documented to accept strict ``json_schema``; every other
model gets ``json_object`` and its answer is validated by Pydantic. Strict schemas follow
the common strict-mode subset: every property required, ``additionalProperties: false``,
references inlined, and only structural keywords kept (``type``, ``properties``,
``required``, ``additionalProperties``, ``items``, ``enum``, ``anyOf``, ``description``).
Value constraints that strict mode may not support (lengths, bounds, patterns) are removed
from the schema sent to the model; the Pydantic model still enforces them on the answer.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError

from yield_guardian.llm.errors import InvalidStructuredOutputError

_KEPT_KEYS = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "anyOf",
        "description",
    }
)
_FENCE = re.compile(r"^\s*```(?:json|JSON)?\s*\n(?P<body>.*)\n\s*```\s*$", re.DOTALL)


def _resolve(node: Any, defs: dict[str, Any], stack: tuple[str, ...]) -> Any:
    if isinstance(node, list):
        return [_resolve(item, defs, stack) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        ref = node["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
            raise ValueError(f"unsupported $ref {ref!r}")
        name = ref.removeprefix("#/$defs/")
        if name in stack:
            raise ValueError(f"recursive schema through {name!r} cannot be inlined")
        merged = {**copy.deepcopy(defs[name]), **{k: v for k, v in node.items() if k != "$ref"}}
        return _resolve(merged, defs, (*stack, name))
    if "allOf" in node and isinstance(node["allOf"], list) and len(node["allOf"]) == 1:
        merged = {**node["allOf"][0], **{k: v for k, v in node.items() if k != "allOf"}}
        return _resolve(merged, defs, stack)
    return {key: _resolve(value, defs, stack) for key, value in node.items()}


def _strictify(node: Any) -> Any:
    if isinstance(node, list):
        return [_strictify(item) for item in node]
    if not isinstance(node, dict):
        return node
    if "const" in node and "enum" not in node:
        node = {**node, "enum": [node["const"]]}
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key not in _KEPT_KEYS:
            continue
        if key == "properties" and isinstance(value, dict):
            out[key] = {name: _strictify(schema) for name, schema in value.items()}
        else:
            out[key] = _strictify(value)
    if out.get("type") == "object" or "properties" in out:
        properties = out.get("properties", {})
        out["type"] = "object"
        out["properties"] = properties
        out["required"] = list(properties)
        out["additionalProperties"] = False
    return out


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema of ``model`` in strict-mode form."""
    schema = model.model_json_schema(mode="validation")
    defs = schema.pop("$defs", {})
    resolved = _resolve(schema, defs, ())
    strict = _strictify(resolved)
    if not isinstance(strict, dict) or strict.get("type") != "object":
        raise ValueError("a structured output must be a JSON object")
    return strict


def strip_code_fence(text: str) -> str:
    """Remove one Markdown code fence around a JSON answer, if present."""
    match = _FENCE.match(text)
    return match.group("body") if match else text


def parse_structured[T: BaseModel](text: str | None, output_type: type[T], *, model: str) -> T:
    """Parse and validate a JSON answer, or raise :class:`InvalidStructuredOutputError`."""
    if text is None or not text.strip():
        raise InvalidStructuredOutputError(model, "empty answer")
    try:
        payload = json.loads(strip_code_fence(text.strip()))
    except json.JSONDecodeError as exc:
        raise InvalidStructuredOutputError(model, f"not JSON ({exc.msg} at {exc.pos})") from exc
    if not isinstance(payload, dict):
        raise InvalidStructuredOutputError(model, "the answer is not a JSON object")
    try:
        return output_type.model_validate(payload)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or '(root)'}: {err['msg']}"
            for err in exc.errors()[:5]
        )
        raise InvalidStructuredOutputError(model, details) from exc
