"""OpenAPI schema with the stream event schemas added, and its export to packages/contracts.

Run from services/api: `uv run python -m yield_guardian.api.openapi ../../packages/contracts/openapi.json`
"""

import json
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from yield_guardian.api.problems import PROBLEM_MEDIA_TYPE
from yield_guardian.contracts.chat import ChatEvent
from yield_guardian.contracts.investigation import InvestigationEvent
from yield_guardian.contracts.line import LineEvent
from yield_guardian.contracts.runs import (
    Run,
    RunCaseList,
    RunCreate,
    RunCreated,
    RunEvent,
    UploadSummary,
)

STREAM_SCHEMAS: tuple[type[BaseModel], ...] = (
    LineEvent,
    InvestigationEvent,
    ChatEvent,
    # V1: the run contract is published ahead of its routes (V4) so the web can build on it.
    RunEvent,
    RunCreate,
    RunCreated,
    Run,
    RunCaseList,
    UploadSummary,
)
REF_TEMPLATE = "#/components/schemas/{model}"


def _normalise(node: Any) -> Any:
    """Drop the cosmetic differences FastAPI introduces (null defaults, integer bounds as floats)."""
    if isinstance(node, dict):
        return {k: _normalise(v) for k, v in node.items() if not (k == "default" and v is None)}
    if isinstance(node, list):
        return [_normalise(v) for v in node]
    if isinstance(node, int | float) and not isinstance(node, bool):
        return float(node)
    return node


def build_openapi(app: FastAPI) -> dict[str, Any]:
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        separate_input_output_schemas=False,
    )
    components: dict[str, Any] = schema.setdefault("components", {}).setdefault("schemas", {})
    _, extra = models_json_schema(
        [(model, "validation") for model in STREAM_SCHEMAS], ref_template=REF_TEMPLATE
    )
    for name, definition in extra.get("$defs", {}).items():
        existing = components.get(name)
        if existing is None:
            components[name] = definition
        elif _normalise(existing) != _normalise(definition):
            raise RuntimeError(f"Schema {name} differs between routes and stream events")
    _use_problem_for_validation_errors(schema)
    schema["components"]["schemas"] = dict(sorted(components.items()))
    return schema


def _use_problem_for_validation_errors(schema: dict[str, Any]) -> None:
    """Validation errors are answered as problem+json, not FastAPI's default body."""
    problem = {
        "description": "Invalid request",
        "content": {PROBLEM_MEDIA_TYPE: {"schema": {"$ref": "#/components/schemas/Problem"}}},
    }
    for operations in schema.get("paths", {}).values():
        for operation in operations.values():
            responses = operation.get("responses", {})
            if "422" in responses:
                responses["422"] = problem
    for name in ("HTTPValidationError", "ValidationError"):
        schema["components"]["schemas"].pop(name, None)


def export(path: Path) -> None:
    from yield_guardian.api.app import create_app
    from yield_guardian.core.settings import Settings

    app = create_app(Settings(environment="test", log_json=False))
    text = json.dumps(app.openapi(), indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    export(Path(sys.argv[1] if len(sys.argv) > 1 else "../../packages/contracts/openapi.json"))
