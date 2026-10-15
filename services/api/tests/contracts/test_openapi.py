import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI

COMMITTED = Path(__file__).resolve().parents[4] / "packages" / "contracts" / "openapi.json"


@pytest.fixture
def schema(app: FastAPI) -> dict[str, Any]:
    return app.openapi()


def test_every_operation_has_an_id(schema: dict[str, Any]) -> None:
    ids = [op["operationId"] for ops in schema["paths"].values() for op in ops.values()]
    assert len(ids) == len(set(ids))
    assert all(ids)


def test_stream_event_schemas_are_published(schema: dict[str, Any]) -> None:
    names = schema["components"]["schemas"]
    for name in ("RunEvent", "InvestigationEvent", "ChatEvent", "Problem"):
        assert name in names
    assert "HTTPValidationError" not in names
    # The v1 replay is gone with its socket.
    assert not {"LineEvent", "LineState", "PlantClock"} & set(names)


def test_errors_are_problem_json(schema: dict[str, Any]) -> None:
    for path, ops in schema["paths"].items():
        for method, op in ops.items():
            for status, response in op["responses"].items():
                if status.startswith(("4", "5")):
                    content = response["content"]
                    assert list(content) == ["application/problem+json"], (path, method, status)
                    assert content["application/problem+json"]["schema"] == {
                        "$ref": "#/components/schemas/Problem"
                    }


def test_committed_schema_is_current(schema: dict[str, Any]) -> None:
    assert COMMITTED.exists(), "Run: uv run python -m yield_guardian.api.openapi"
    assert json.loads(COMMITTED.read_text(encoding="utf-8")) == schema, (
        "packages/contracts/openapi.json is stale. Run: uv run python -m yield_guardian.api.openapi "
        "and pnpm contracts:generate"
    )
