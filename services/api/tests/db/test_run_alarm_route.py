"""POST /investigations with a run alarm (PLAN_V2 3.4): the run and its alarm must exist, the
title names the alarm, and a second start of the same alarm returns the first investigation.
The run is a SYNTHETIC test value (tests/agent/run_helpers.py)."""

from collections.abc import AsyncIterator

import httpx
import pytest

from tests.agent.run_helpers import RUN_ID, FakeRuns
from tests.db.conftest import clean
from tests.db.fakes import FakeRunner
from yield_guardian.api.app import create_app
from yield_guardian.api.deps import CSRF_HEADER
from yield_guardian.core.settings import Settings
from yield_guardian.services.persistence import build_persistence
from yield_guardian.services.registry import ServiceRegistry


async def _client(
    database_url: str, settings: Settings, runs: FakeRuns | None
) -> AsyncIterator[httpx.AsyncClient]:
    await clean(database_url)
    registry = ServiceRegistry(settings=settings, runner=FakeRunner())
    build_persistence(settings, runner_provider=lambda: registry.runner, migrate=True).install(
        registry
    )
    registry.run_reader = runs  # after install, which sets the database run store
    app = create_app(settings, registry)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            started = await client.post("/api/v1/session/guest", json={"display_name": "Mia"})
            client.headers[CSRF_HEADER] = started.json()["csrf_token"]
            yield client


@pytest.fixture
async def api(database_url: str, db_settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    async for client in _client(database_url, db_settings, FakeRuns()):
        yield client


@pytest.fixture
async def without_runs(
    database_url: str, db_settings: Settings
) -> AsyncIterator[httpx.AsyncClient]:
    async for client in _client(database_url, db_settings, None):
        yield client


def start(alarm_id: str, run_id: str = RUN_ID) -> dict[str, object]:
    return {"trigger": {"kind": "run_alarm", "ref": f"{run_id}:{alarm_id}"}}


async def test_a_run_alarm_starts_one_investigation(api: httpx.AsyncClient) -> None:
    first = await api.post("/api/v1/investigations", json=start("RA-1"))
    assert first.status_code == 202, first.text
    body = first.json()
    assert body["title"] == "Sensor relationships broke (SPE) on unit U-3 (RA-1)"
    assert body["trigger"] == {"kind": "run_alarm", "ref": f"{RUN_ID}:RA-1", "question": None}
    again = await api.post("/api/v1/investigations", json=start("RA-1"))
    assert again.status_code == 202
    assert again.json()["investigation_id"] == body["investigation_id"]


@pytest.mark.parametrize(
    ("payload", "status", "detail"),
    [
        (start("RA-9"), 404, f"Run {RUN_ID} has no alarm RA-9."),
        (start("RA-1", "run_doesnotexist"), 404, "Run run_doesnotexist does not exist"),
        ({"trigger": {"kind": "run_alarm", "ref": "RA-1"}}, 400, "not a valid run_alarm"),
    ],
)
async def test_a_run_alarm_that_cannot_be_found_is_refused(
    api: httpx.AsyncClient, payload: dict[str, object], status: int, detail: str
) -> None:
    response = await api.post("/api/v1/investigations", json=payload)
    assert response.status_code == status, response.text
    assert detail in response.json()["detail"]
    assert (await api.get("/api/v1/investigations")).json()["items"] == []


async def test_without_a_run_store_a_run_alarm_is_not_ready(
    without_runs: httpx.AsyncClient,
) -> None:
    response = await without_runs.post("/api/v1/investigations", json=start("RA-1"))
    assert response.status_code == 503
    assert response.json()["code"] == "not_ready"
