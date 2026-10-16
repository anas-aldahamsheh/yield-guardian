"""Recorded runs in the database: made through the job queue, exported, imported idempotently
on another database (with the paused state), seeded at startup, and on that host the product's
read-only example. The runner is the fake one; its values are synthetic test data."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import SecretStr
from sqlalchemy import select

from tests.db.conftest import temporary_database
from tests.db.fakes import FakeRunner
from yield_guardian.agent.graph import initial_state, paused_values, restore_paused
from yield_guardian.agent.wiring import RecordedRunsResource
from yield_guardian.contracts.investigation import (
    Decision,
    DecisionCreate,
    InvestigationTrigger,
    Report,
)
from yield_guardian.contracts.session import GuestSessionCreate
from yield_guardian.core.settings import Settings
from yield_guardian.db.engine import Database
from yield_guardian.db.tables import InvestigationEventRow, InvestigationJobRow, InvestigationRow
from yield_guardian.services.audit import Actor
from yield_guardian.services.errors import ReadOnlyError
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
AS_OF = 1303


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


async def decided_before(
    persistence: Persistence,
    investigation_id: str,
    verdict: Literal["approve", "reject"],
    name: str,
) -> None:
    """Decide a recorded run as a visitor could before it was the read-only example: the
    decision stored as ``decide`` stored it, then the job's last step after the resume
    (``finalize``: the work order, the audit entries, the status). A host where that happened
    keeps them."""
    async with persistence.database.sessionmaker() as db, db.begin():
        row = await db.get(InvestigationRow, investigation_id, with_for_update=True)
        assert row is not None
        assert (row.status, row.decision) == ("awaiting_decision", None)
        assert row.report is not None
        actions = len(Report.model_validate(row.report).actions) if verdict == "approve" else 0
        row.decision = Decision(
            verdict=verdict,
            actions=list(range(actions)),
            note=None,
            decided_by=name,
            decided_at=datetime.now(UTC),
        ).model_dump(mode="json")
    await persistence.investigations.finalize(investigation_id, Actor(role="engineer", name=name))


async def _record(persistence: Persistence, trigger: InvestigationTrigger) -> str:
    created = await persistence.investigations.create_recorded(trigger, actor=RECORDER, as_of=AS_OF)
    assert created.recorded
    assert await _settled(persistence.investigations, created.investigation_id) == "awaiting_decision"  # fmt: skip
    return created.investigation_id


async def test_a_recorded_run_goes_through_the_job_queue(
    persistence: Persistence, runner: FakeRunner
) -> None:
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
    assert runner.as_of == [AS_OF]  # the recorded run's tools read the line as of its alarm
    summary = (await persistence.investigations.list()).items[0]
    assert (summary.investigation_id, summary.recorded) == (investigation_id, True)
    assert summary.models  # the fake runner's models are shown with the run
    alarm = await persistence.alarms.get(ALARM.ref)
    assert (alarm.status, alarm.investigation_id) == ("investigating", investigation_id)


@pytest.fixture
def target_url() -> Iterator[str]:
    with temporary_database(migrate=True) as url:
        yield url


async def test_export_then_import_is_idempotent_and_the_import_is_the_read_only_example(
    persistence: Persistence, runner: FakeRunner, target_url: str, tmp_path: Path
) -> None:
    recorded = await _record(persistence, ALARM)
    live = await persistence.investigations.create_recorded(UNIT, actor=RECORDER, as_of=AS_OF)
    session, _ = await persistence.sessions.guest(GuestSessionCreate(display_name="Dana"), client="t")  # fmt: skip
    plain = await persistence.investigations.create(InvestigationTrigger(kind="unit", ref="77"), session=session)  # fmt: skip
    await _settled(persistence.investigations, live.investigation_id)
    await _settled(persistence.investigations, plain.investigation_id)
    # The live run was decided before the export: it is left out (its decision stays here).
    await decided_before(persistence, live.investigation_id, "reject", "Dana")
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
        # On the new host it is the product's example: every visitor lists it, apart from
        # their own, and nobody decides it, since every visitor would see the decision.
        guest, _ = await target.sessions.guest(GuestSessionCreate(display_name="Lee"), client="t")
        listed = await target.investigations.list(viewer=guest.viewer)
        assert ([i.investigation_id for i in listed.examples], listed.items) == ([recorded], [])
        with pytest.raises(ReadOnlyError, match="nobody decides it"):
            await target.investigations.decide(recorded, DecisionCreate(verdict="approve", actions=[0]), session=guest)  # fmt: skip
        assert (await target.investigations.get(recorded)).status == "awaiting_decision"
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


async def test_a_live_run_never_gets_a_position(
    persistence: Persistence, runner: FakeRunner
) -> None:
    session, _ = await persistence.sessions.guest(GuestSessionCreate(display_name="Dana"), client="t")  # fmt: skip
    created = await persistence.investigations.create(UNIT, session=session)
    await _settled(persistence.investigations, created.investigation_id)
    assert runner.as_of == [None]


async def test_a_failed_recorded_run_stays_failed_and_is_never_exported_or_imported(
    persistence: Persistence, runner: FakeRunner
) -> None:
    runner.behaviour = "fail"
    created = await persistence.investigations.create_recorded(ALARM, actor=RECORDER, as_of=AS_OF)
    assert await _settled(persistence.investigations, created.investigation_id) == "failed"
    failed = await persistence.investigations.get(created.investigation_id)
    assert (failed.recorded, failed.status) == (True, "failed")
    assert failed.error is not None  # the UI shows the status and this error
    summary = (await persistence.investigations.list(status="failed")).items[0]
    assert (summary.investigation_id, summary.recorded) == (created.investigation_id, True)
    async with asyncio.timeout(15):  # the job reopens the alarm when it closes the run
        while True:
            if (await persistence.alarms.get(ALARM.ref)).status == "open":
                break  # so a new recording can take it
            await asyncio.sleep(0.05)

    exported, left_out = await export_recorded(persistence.database.sessionmaker, None)
    assert exported.runs == []
    assert left_out == [created.investigation_id]

    runner.behaviour = "report"
    good = await _record(persistence, UNIT)
    with_good, _ = await export_recorded(persistence.database.sessionmaker, None)
    (run,) = with_good.runs
    as_failed = run.investigation.model_copy(update={"status": "failed"})
    forged = RecordedRuns(
        exported_at=with_good.exported_at,
        runs=[run.model_copy(update={"investigation": as_failed})],
    )
    await clean_ids(persistence, good)
    report = await import_recorded(persistence.database.sessionmaker, forged, None)
    assert (report.imported, report.not_importable) == ([], [good])


async def clean_ids(persistence: Persistence, investigation_id: str) -> None:
    from sqlalchemy import delete

    from yield_guardian.db.tables import InvestigationRow

    async with persistence.database.sessionmaker() as db, db.begin():
        await db.execute(
            delete(InvestigationRow).where(InvestigationRow.investigation_id == investigation_id)
        )
