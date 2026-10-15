"""What a reload of the Line page reads back (GET /runs/{id}): a snapshot that says which events
it includes, so the stream resumes right after it; when a running stage started, so its clock
goes on; and each alarm's investigation with its status, so the link outlives the browser.

Runs use the real SECOM engine on real SECOM units (tests/live/doubles.py) and the wafer double;
the investigator is the scripted FakeRunner (tests/db/fakes.py), whose values are synthetic."""

import asyncio
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from tests.db.conftest import clean
from tests.db.fakes import FakeRunner
from tests.live.doubles import (
    SECOM_DATA,
    WaferDouble,
    demo_wafers,
    held_out_ids,
    real_secom,
    real_sensor_engine,
)
from yield_guardian.api.app import create_app
from yield_guardian.api.deps import CSRF_HEADER
from yield_guardian.contracts.runs import RunOrigin, StageStartedEvent
from yield_guardian.core.settings import Settings
from yield_guardian.live.runs import Engines, RunOrchestrator
from yield_guardian.live.sensor_file import SecomSensorFileParser
from yield_guardian.live.wiring import install_runs
from yield_guardian.services.persistence import Persistence, build_persistence
from yield_guardian.services.registry import ServiceRegistry
from yield_guardian.services.runs import DbRunStore, RunInput, initial_stage, run_done

ORIGIN = RunOrigin(source="pick", datasets=["secom"], title="Your pick of real data", rule="test")
REAL_LOT = "lot10291"


@dataclass
class Clock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now


async def test_a_snapshot_names_its_last_event_and_when_a_running_stage_started(
    persistence: Persistence,
) -> None:
    clock = Clock(datetime(2026, 10, 15, 9, 0, tzinfo=UTC))
    store = DbRunStore(persistence.database.sessionmaker, persistence.notifier, now=clock)
    data = RunInput(units=real_sensor_engine().from_secom(held_out_ids()[:3]))
    run_id = (await store.create(ORIGIN, data, RunOrchestrator.plan(data))).run_id

    queued = await store.get(run_id)
    assert queued.last_seq == 1  # run_started
    assert queued.read_at == clock.now
    assert all(s.started_at is None for s in queued.stages)

    started_at = clock.now + timedelta(seconds=2)
    clock.now = started_at
    await store.update(
        run_id,
        status="running",
        stage=initial_stage("intake").model_copy(update={"status": "running"}),
        events=[lambda seq, at: StageStartedEvent(seq=seq, at=at, stage="intake")],
    )
    clock.now += timedelta(seconds=3)
    running = await store.get(run_id)
    assert running.last_seq == 2
    assert running.read_at == started_at + timedelta(seconds=3)
    intake = next(s for s in running.stages if s.stage == "intake")
    assert (intake.status, intake.started_at) == ("running", started_at)

    await store.update(run_id, status="done", events=[run_done("done", 0, 0)])
    after = [e async for e in store.events(run_id, after_seq=running.last_seq)]
    assert [(e.seq, e.type) for e in after] == [(3, "run_done")]
    assert (await store.get(run_id)).last_seq == 3


# Routes ---------------------------------------------------------------------------------------


@dataclass
class Api:
    client: httpx.AsyncClient
    runner: FakeRunner


@pytest.fixture
async def api(database_url: str, db_settings: Settings) -> AsyncIterator[Api]:
    await clean(database_url)
    runner = FakeRunner("block")
    registry = ServiceRegistry(settings=db_settings, runner=runner)
    persistence = build_persistence(db_settings, runner_provider=lambda: registry.runner)
    persistence.install(registry)
    install_runs(
        registry,
        persistence.runs,
        secom=real_secom(),
        wafermap=None,
        secom_attribution=SECOM_DATA / "ATTRIBUTION.md",
        engines=Engines(
            sensors=real_sensor_engine(),
            wafers=WaferDouble(demo={REAL_LOT: demo_wafers(REAL_LOT)}),
            sensor_file=SecomSensorFileParser(),
        ),
    )
    app = create_app(db_settings, registry)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield Api(client, runner)
    runner.release.set()


async def stream_ids(client: httpx.AsyncClient, run_id: str, after: int | None = None) -> list[int]:
    headers = {"Last-Event-ID": str(after)} if after is not None else {}
    async with client.stream("GET", f"/api/v1/runs/{run_id}/events", headers=headers) as response:
        assert response.status_code == 200
        body = "".join([chunk async for chunk in response.aiter_text()])
    return [int(m) for m in re.findall(r"^id: (\d+)\r?$", body, flags=re.MULTILINE)]


async def status_of(client: httpx.AsyncClient, investigation_id: str, wanted: str) -> str:
    for _ in range(100):
        status = (await client.get(f"/api/v1/investigations/{investigation_id}")).json()["status"]
        if status == wanted:
            return str(status)
        await asyncio.sleep(0.05)
    raise AssertionError(f"{investigation_id} never reached {wanted}")


async def test_a_reload_reads_the_whole_run_and_the_stream_after_it(api: Api) -> None:
    created = (await api.client.post("/api/v1/runs", json={"source": "sample", "seed": 11})).json()
    run_id = created["run_id"]
    every = await stream_ids(api.client, run_id)  # to run_done
    run = (await api.client.get(f"/api/v1/runs/{run_id}")).json()
    assert run["status"] == "done"
    assert run["last_seq"] == every[-1] == len(every)
    assert run["read_at"] is not None
    assert await stream_ids(api.client, run_id, after=run["last_seq"]) == []
    assert all(s["started_at"] is None for s in run["stages"] if s["status"] != "running")


async def test_an_alarm_keeps_its_investigation_and_status_across_a_reload(api: Api) -> None:
    created = (await api.client.post("/api/v1/runs", json={"source": "sample", "seed": 11})).json()
    run_id = created["run_id"]
    await stream_ids(api.client, run_id)
    before = (await api.client.get(f"/api/v1/runs/{run_id}")).json()
    assert before["alarms"], "the real sample raises at least one alarm"
    assert all(a["investigation_id"] is None for a in before["alarms"])
    assert all(a["investigation_status"] is None for a in before["alarms"])
    alarm = before["alarms"][0]["alarm_id"]

    session = await api.client.post("/api/v1/session/guest", json={"display_name": "Mia"})
    api.client.headers[CSRF_HEADER] = session.json()["csrf_token"]
    started = await api.client.post(
        "/api/v1/investigations",
        json={"trigger": {"kind": "run_alarm", "ref": f"{run_id}:{alarm}"}},
    )
    assert started.status_code == 202, started.text
    investigation_id = started.json()["investigation_id"]
    assert await status_of(api.client, investigation_id, "running") == "running"

    # A reload (or another browser of the same workspace) reads the link and its status back.
    del api.client.headers[CSRF_HEADER]
    reloaded = (await api.client.get(f"/api/v1/runs/{run_id}")).json()
    linked = {a["alarm_id"]: a for a in reloaded["alarms"]}
    assert linked[alarm]["investigation_id"] == investigation_id
    assert linked[alarm]["investigation_status"] == "running"
    others = [a for a in reloaded["alarms"] if a["alarm_id"] != alarm]
    assert all(a["investigation_id"] is None for a in others)
    assert reloaded["expires_at"] is None  # kept while the investigation uses it
    # Nothing else of the stored run changed.
    drop = ("alarms", "expires_at", "read_at")
    assert json.dumps({k: v for k, v in reloaded.items() if k not in drop}) == json.dumps(
        {k: v for k, v in before.items() if k not in drop}
    )

    api.runner.release.set()
    await status_of(api.client, investigation_id, "awaiting_decision")
    finished = (await api.client.get(f"/api/v1/runs/{run_id}")).json()
    assert {a["alarm_id"]: a for a in finished["alarms"]}[alarm][
        "investigation_status"
    ] == "awaiting_decision"
