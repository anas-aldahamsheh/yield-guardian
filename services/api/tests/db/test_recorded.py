"""Recorded runs in the database: made through the job queue, exported, imported idempotently
on another database (with the paused state), seeded at startup. The runner is the fake one;
its values are synthetic test data."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import SecretStr
from sqlalchemy import select

from tests.db.conftest import temporary_database
from tests.db.fakes import FakeRunner
from yield_guardian.agent.graph import initial_state, paused_values, restore_paused
from yield_guardian.agent.wiring import RecordedRunsResource
from yield_guardian.contracts.investigation import DecisionCreate, InvestigationTrigger
from yield_guardian.contracts.session import GuestSessionCreate
from yield_guardian.core.settings import Settings
from yield_guardian.db.engine import Database
from yield_guardian.db.tables import InvestigationEventRow, InvestigationJobRow
from yield_guardian.services.audit import Actor
from yield_guardian.services.investigations import DbInvestigationStore
from yield_guardian.services.persistence import Persistence, build_persistence
from yield_guardian.services.recorded import (
    RecordedRuns,
    export_recorded,
    import_recorded,
    read_runs,
    write_runs,
)
from yield_guardian.services.registry import ServiceRegistry

RECORDER = Actor(role="system", name="Recorded demo run")
ALARM = InvestigationTrigger(kind="alarm", ref="AL-1303-risk")
UNIT = InvestigationTrigger(kind="unit", ref="1304")


async def _settled(store: DbInvestigationStore, investigation_id: str) -> str:
    async with asyncio.timeout(15):
        while True:
            status = (await store.get(investigation_id)).status
            if status in ("awaiting_decision", "failed"):
                return status
            await asyncio.sleep(0.05)


async def _events(database: Database, investigation_id: str) -> list[dict[str, object]]:
    async with database.sessionmaker() as db:
        rows = await db.scalars(
            select(InvestigationEventRow.payload)
            .where(InvestigationEventRow.investigation_id == investigation_id)
            .order_by(InvestigationEventRow.seq)
        )
        return list(rows)


async def _record(persistence: Persistence, trigger: InvestigationTrigger) -> str:
    created = await persistence.investigations.create_recorded(trigger, actor=RECORDER)
    assert created.recorded
    assert await _settled(persistence.investigations, created.investigation_id) == "awaiting_decision"  # fmt: skip
    return created.investigation_id


async def test_a_recorded_run_goes_through_the_job_queue(persistence: Persistence) -> None:
    investigation_id = await _record(persistence, ALARM)
    async with persistence.database.sessionmaker() as db:
        kinds = (
            await db.scalars(
                select(InvestigationJobRow.kind).where(
                    InvestigationJobRow.investigation_id == investigation_id
                )
            )
        ).all()
    assert list(kinds) == ["run"]
    summary = (await persistence.investigations.list()).items[0]
    assert (summary.investigation_id, summary.recorded) == (investigation_id, True)
    assert summary.models  # the fake runner's models are shown with the run
    alarm = await persistence.alarms.get(ALARM.ref)
    assert (alarm.status, alarm.investigation_id) == ("investigating", investigation_id)


@pytest.fixture
def target_url() -> Iterator[str]:
    with temporary_database(migrate=True) as url:
        yield url


async def test_export_then_import_is_idempotent_and_keeps_the_run_decidable(
    persistence: Persistence, runner: FakeRunner, target_url: str, tmp_path: Path
) -> None:
    recorded = await _record(persistence, ALARM)
    live = await persistence.investigations.create_recorded(UNIT, actor=RECORDER)
    session, _ = await persistence.sessions.guest(GuestSessionCreate(display_name="Dana"), client="t")  # fmt: skip
    plain = await persistence.investigations.create(InvestigationTrigger(kind="unit", ref="77"), session=session)  # fmt: skip
    await _settled(persistence.investigations, live.investigation_id)
    await _settled(persistence.investigations, plain.investigation_id)
    # The live run is decided before the export: it is left out (its work order stays here).
    await persistence.investigations.decide(
        live.investigation_id, DecisionCreate(verdict="reject"), session=session
    )
    source_saver = InMemorySaver()
    await restore_paused(source_saver, recorded, dict(initial_state(recorded, ALARM)))

    exported, left_out = await export_recorded(persistence.database.sessionmaker, source_saver)
    assert [r.investigation.investigation_id for r in exported.runs] == [recorded]
    assert left_out == [live.investigation_id]
    assert plain.investigation_id not in left_out
    run = exported.runs[0]
    assert run.paused_state is not None
    assert run.created_by == "Recorded demo run"
    path = tmp_path / "recorded" / "investigations.json"
    write_runs(path, exported)
    assert read_runs(path) == exported

    target = build_persistence_for(target_url, runner)
    for resource in target.resources:
        await resource.start()
    try:
        saver = InMemorySaver()
        first = await import_recorded(target.database.sessionmaker, read_runs(path), saver)
        again = await import_recorded(target.database.sessionmaker, read_runs(path), saver)
        assert (first.imported, first.skipped, first.without_state) == ([recorded], [], [])
        assert (again.imported, again.skipped) == ([], [recorded])
        copy = await target.investigations.get(recorded)
        original = await persistence.investigations.get(recorded)
        assert copy == original
        assert await _events(target.database, recorded) == await _events(
            persistence.database, recorded
        )
        assert await paused_values(saver, recorded) is not None
        alarm = await target.alarms.get(ALARM.ref)
        assert (alarm.status, alarm.investigation_id) == ("investigating", recorded)
        # A person decides the imported run on the new host as on any other.
        guest, _ = await target.sessions.guest(GuestSessionCreate(display_name="Lee"), client="t")
        await target.investigations.decide(recorded, DecisionCreate(verdict="approve", actions=[0]), session=guest)  # fmt: skip
        async with asyncio.timeout(15):
            while True:
                if (await target.investigations.get(recorded)).status == "approved":
                    break
                await asyncio.sleep(0.05)
    finally:
        for resource in reversed(target.resources):
            await resource.stop()


def build_persistence_for(url: str, runner: FakeRunner) -> Persistence:
    settings = Settings(environment="test", log_json=False, database_url=SecretStr(url))
    return build_persistence(settings, runner_provider=lambda: runner, migrate=False)


async def test_an_invalid_file_imports_nothing(persistence: Persistence) -> None:
    investigation_id = await _record(persistence, ALARM)
    exported, _ = await export_recorded(persistence.database.sessionmaker, None)
    broken = exported.model_copy(deep=True)
    broken.runs[0].events.pop(0)  # seq no longer starts at 1
    with pytest.raises(ValueError, match="seq"):
        await import_recorded(persistence.database.sessionmaker, broken, None)
    unrecorded = exported.model_copy(deep=True)
    unrecorded.runs[0].investigation = unrecorded.runs[0].investigation.model_copy(
        update={"recorded": False}
    )
    with pytest.raises(ValueError, match="not a recorded run"):
        await import_recorded(persistence.database.sessionmaker, unrecorded, None)
    assert exported.runs[0].investigation.investigation_id == investigation_id
    assert exported.runs[0].paused_state is None  # exported without a checkpointer


async def test_startup_seeds_missing_runs_with_their_paused_state(
    persistence: Persistence, target_url: str, tmp_path: Path
) -> None:
    recorded = await _record(persistence, ALARM)
    saver = InMemorySaver()
    await restore_paused(saver, recorded, dict(initial_state(recorded, ALARM)))
    exported, _ = await export_recorded(persistence.database.sessionmaker, saver)
    path = tmp_path / "investigations.json"
    write_runs(path, exported)

    database = Database(target_url, migrate_on_start=False)
    registry = ServiceRegistry(settings=Settings(environment="test", log_json=False))
    try:
        seed = RecordedRunsResource(registry, database.sessionmaker, target_url, path)
        await seed.start()
        await seed.start()  # every start: nothing new, nothing changed
        assert "recorded_runs" not in registry.problems
        store = DbInvestigationStore(database.sessionmaker)
        assert (await store.get(recorded)).recorded
        assert (await store.list()).total == 1
        missing = RecordedRunsResource(registry, database.sessionmaker, target_url, tmp_path / "none.json")  # fmt: skip
        await missing.start()
        assert "recorded_runs" not in registry.problems
        (tmp_path / "bad.json").write_text("{}", encoding="utf-8")
        bad = RecordedRunsResource(registry, database.sessionmaker, target_url, tmp_path / "bad.json")  # fmt: skip
        await bad.start()
        assert "not imported" in registry.problems["recorded_runs"]
    finally:
        await database.stop()


def test_the_export_format_is_versioned() -> None:
    with pytest.raises(ValueError):
        RecordedRuns.model_validate(
            {"format": "other", "exported_at": "2026-10-14T00:00:00Z", "runs": []}
        )
