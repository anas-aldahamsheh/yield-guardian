import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from pydantic import TypeAdapter

from yield_guardian.contracts.chat import ChatEvent
from yield_guardian.contracts.investigation import InvestigationEvent
from yield_guardian.contracts.line import LineEvent, LineState

FIXTURES = Path(__file__).resolve().parents[4] / "packages" / "contracts" / "fixtures"
STREAMS: dict[str, Any] = {
    "stream_investigation_events": list[InvestigationEvent],
    "chat": list[ChatEvent],
    "line_socket": list[LineEvent],
}
# Operations retired from the API whose fixtures the v1 web still reads until it drops them
# (the replay: GET /line/state and /ws/line, PLAN_V2 §3.3); they still match their schema.
RETIRED: dict[str, Any] = {"get_line_state": LineState}
NO_FIXTURE = {"get_health", "get_readiness", "logout"}


def _walk(routes: list[Any]) -> list[APIRoute]:
    found: list[APIRoute] = []
    for route in routes:
        if isinstance(route, APIRoute):
            found.append(route)
        elif (included := getattr(route, "original_router", None)) is not None:
            found.extend(_walk(included.routes))  # routers stay nested since FastAPI 0.14x
    return found


def _routes(app: FastAPI) -> dict[str, APIRoute]:
    return {r.name: r for r in _walk(app.routes)}


def _files() -> list[Path]:
    return sorted(FIXTURES.glob("*.json"))


@pytest.mark.parametrize("path", _files(), ids=lambda p: p.stem)
def test_fixture_matches_contract(path: Path, app: FastAPI) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    name = path.stem
    if name in STREAMS or name in RETIRED:
        TypeAdapter(STREAMS.get(name) or RETIRED[name]).validate_python(data)
        return
    route = _routes(app).get(name)
    assert route is not None, f"{path.name} does not name an operation"
    assert route.response_model is not None
    TypeAdapter(route.response_model).validate_python(data)


def test_every_operation_has_a_fixture(app: FastAPI) -> None:
    names = {p.stem for p in _files()}
    missing = set(_routes(app)) - names - NO_FIXTURE
    assert not missing, f"Add fixtures for: {sorted(missing)}"
