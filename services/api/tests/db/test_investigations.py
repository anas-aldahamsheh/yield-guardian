"""Investigations end to end with the fake runner: queue, events, snapshot, decision, alarms."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr
from sqlalchemy import select, update

from tests.agent.run_helpers import LOT, RUN_ID, FakeRuns
from tests.db.conftest import clean
from tests.db.fakes import REPORT, FakeRunner
from yield_guardian.contracts.investigation import (
    DecisionCreate,
    InvestigationEventPayload,
    InvestigationTrigger,
)
from yield_guardian.contracts.services import InvalidArgumentError, NotFoundError, NotReadyError
from yield_guardian.contracts.session import GuestSessionCreate
from yield_guardian.core.settings import Settings
from yield_guardian.db.tables import InvestigationJobRow, InvestigationRow
from yield_guardian.services.access import NOBODY, viewing
from yield_guardian.services.alarms import AlarmStateStore
from yield_guardian.services.errors import ConflictError
from yield_guardian.services.investigations import (
    check_run_alarm,
    new_investigation_id,
    trigger_title,
)
from yield_guardian.services.jobs import JobWorker, RunnerProvider
from yield_guardian.services.persistence import Persistence, build_persistence
from yield_guardian.services.protocols import ActiveSession, InvestigationStore

ALARM = InvestigationTrigger(kind="alarm", ref="AL-1043-t2")


async def _engineer(persistence: Persistence, name: str = "Dana") -> ActiveSession:
    session, _ = await persistence.sessions.guest(GuestSessionCreate(display_name=name), client="t")
    return session


async def _collect(
    persistence: Persistence, investigation_id: str, after: int | None = None
) -> list[InvestigationEventPayload]:
    async with asyncio.timeout(15):
        return [
            e async for e in persistence.investigations.events(investigation_id, after_seq=after)
        ]


def _provider(runner: FakeRunner) -> RunnerProvider:
    return lambda: runner


def _types(events: list[InvestigationEventPayload]) -> list[str]:
    return [e.type for e in events]


async def test_ids_and_titles() -> None:
    assert new_investigation_id().startswith("inv_")
    assert len(new_investigation_id()) == 30
    assert trigger_title(ALARM) == "T² alarm on unit 1043"
    assert trigger_title(InvestigationTrigger(kind="unit", ref="17")) == "Unit 17"
    assert trigger_title(InvestigationTrigger(kind="wafer", ref="lot1-3")) == "Wafer lot1-3"
    assert trigger_title(InvestigationTrigger(kind="lot", ref="lot47542")) == "Lot lot47542"
    for kind, ref in [("alarm", "AL-1-x"), ("unit", "u1"), ("wafer", "lot1"), ("lot", "a b")]:
        with pytest.raises(InvalidArgumentError):
            trigger_title(InvestigationTrigger.model_validate({"kind": kind, "ref": ref}))


async def test_run_streams_every_event_and_builds_the_snapshot(
    persistence: Persistence, runner: FakeRunner
) -> None:
    store: InvestigationStore = persistence.investigations
    alarms: AlarmStateStore = persistence.alarms
    created = await store.create(ALARM, session=await _engineer(persistence))
    assert created.status == "queued"
    assert created.title == "T² alarm on unit 1043"
    assert (await alarms.get("AL-1043-t2")).status == "investigating"

    events = await _collect(persistence, created.investigation_id)
    assert _types(events) == [
        "status",
        "status",
        "step",
        "evidence",
        "step",
        "report",
        "verification",
        "status",
        "end",
    ]
    assert [e.seq for e in events] == list(range(1, 10))
    assert [getattr(e, "status", None) for e in events if e.type in ("status", "end")] == [
        "queued",
        "running",
        "awaiting_decision",
        "awaiting_decision",
    ]
    assert runner.runs == [created.investigation_id]

    investigation = await store.get(created.investigation_id)
    assert investigation.status == "awaiting_decision"
    assert [s.status for s in investigation.steps] == ["completed"]
    assert investigation.report == REPORT
    assert investigation.verification is not None
    assert [e.evidence_id for e in investigation.evidence] == ["E1"]
    assert [(m.role, m.model_id) for m in investigation.models] == [
        ("investigator", "test-model"),
        ("writer", "test-writer"),
    ]
    assert investigation.usage is not None
    assert (investigation.usage.requests, investigation.usage.cache_hits) == (1, 1)
    assert investigation.usage.tokens_in == 150
    evidence = await store.get_evidence(created.investigation_id, "E1")
    assert evidence.data == {"risk": 0.5}
    with pytest.raises(NotFoundError):
        await store.get_evidence(created.investigation_id, "E9")

    created_audit = (await persistence.audit.list(action="investigation.created")).items
    assert [(a.actor_name, a.target_id) for a in created_audit] == [
        ("Dana", created.investigation_id)
    ]


async def test_stream_resumes_after_a_sequence_number(persistence: Persistence) -> None:
    created = await persistence.investigations.create(ALARM, session=await _engineer(persistence))
    events = await _collect(persistence, created.investigation_id)
    tail = await _collect(persistence, created.investigation_id, after=6)
    assert [e.seq for e in tail] == [7, 8, 9]
    assert tail == events[6:]


async def test_an_alarm_under_investigation_returns_the_same_investigation(
    persistence: Persistence,
) -> None:
    session = await _engineer(persistence)
    first = await persistence.investigations.create(ALARM, session=session)
    again = await persistence.investigations.create(ALARM, session=session)
    assert again.investigation_id == first.investigation_id
    assert (await persistence.investigations.list()).total == 1


async def test_approve_opens_a_work_order_and_closes_the_alarm(
    persistence: Persistence, runner: FakeRunner
) -> None:
    store = persistence.investigations
    session = await _engineer(persistence)
    created = await store.create(ALARM, session=session)
    first = await _collect(persistence, created.investigation_id)

    decided = await store.decide(
        created.investigation_id,
        DecisionCreate(verdict="approve", actions=[2, 0], note="Go"),
        session=session,
    )
    assert decided.decision is not None
    assert decided.decision.decided_by == "Dana"
    with pytest.raises(ConflictError):
        await store.decide(
            created.investigation_id, DecisionCreate(verdict="reject"), session=session
        )

    rest = await _collect(persistence, created.investigation_id, after=first[-1].seq)
    assert _types(rest) == ["decision", "status", "end"]
    decision_event = rest[0]
    assert decision_event.type == "decision"
    assert decision_event.work_order_id == "WO-000001"
    assert [d.actions for _, d in runner.resumes] == [[2, 0]]

    investigation = await store.get(created.investigation_id)
    assert investigation.status == "approved"
    assert investigation.work_order_id == "WO-000001"
    work_order = await persistence.work_orders.get("WO-000001")
    assert [a.action for a in work_order.actions] == ["Hold lot.", "Check sensor S060."]
    assert work_order.created_by == "Dana"
    assert work_order.note == "Go"
    alarm = await persistence.alarms.get("AL-1043-t2")
    assert (alarm.status, alarm.investigation_id) == ("closed", created.investigation_id)
    actions = {e.action for e in (await persistence.audit.list()).items}
    assert {"investigation.approved", "work_order.created"} <= actions

    # A full replay ends at the last end event and includes the decision.
    assert _types(await _collect(persistence, created.investigation_id))[-3:] == [
        "decision",
        "status",
        "end",
    ]
    # Nothing follows the last event of a finished investigation: the stream closes at once.
    assert await _collect(persistence, created.investigation_id, after=rest[-1].seq) == []


async def test_approve_all_and_reject(persistence: Persistence) -> None:
    store = persistence.investigations
    session = await _engineer(persistence)
    approved = await store.create(InvestigationTrigger(kind="unit", ref="5"), session=session)
    rejected = await store.create(InvestigationTrigger(kind="unit", ref="6"), session=session)
    await _collect(persistence, approved.investigation_id)
    await _collect(persistence, rejected.investigation_id)

    with pytest.raises(InvalidArgumentError):
        await store.decide(
            rejected.investigation_id,
            DecisionCreate(verdict="reject", actions=[0]),
            session=session,
        )
    for bad in ([3], [0, 0]):
        with pytest.raises(InvalidArgumentError):
            await store.decide(
                approved.investigation_id,
                DecisionCreate(verdict="approve", actions=bad),
                session=session,
            )
    await store.decide(
        approved.investigation_id, DecisionCreate(verdict="approve"), session=session
    )
    await store.decide(rejected.investigation_id, DecisionCreate(verdict="reject"), session=session)
    await _collect(persistence, approved.investigation_id, after=9)
    await _collect(persistence, rejected.investigation_id, after=9)

    done = await store.get(approved.investigation_id)
    assert done.decision is not None
    assert done.decision.actions == [0, 1, 2]
    assert done.work_order_id is not None
    assert len((await persistence.work_orders.get(done.work_order_id)).actions) == 3
    no = await store.get(rejected.investigation_id)
    assert (no.status, no.work_order_id) == ("rejected", None)
    assert (await persistence.work_orders.list()).total == 1


async def test_decide_needs_a_waiting_investigation(
    persistence: Persistence, runner: FakeRunner
) -> None:
    runner.behaviour = "block"
    session = await _engineer(persistence)
    created = await persistence.investigations.create(ALARM, session=session)
    with pytest.raises(ConflictError):
        await persistence.investigations.decide(
            created.investigation_id, DecisionCreate(verdict="approve"), session=session
        )
    with pytest.raises(NotFoundError):
        await persistence.investigations.decide(
            "inv_00000000", DecisionCreate(verdict="approve"), session=session
        )
    runner.release.set()
    await _collect(persistence, created.investigation_id)


async def test_live_events_reach_a_waiting_stream(
    persistence: Persistence, runner: FakeRunner
) -> None:
    runner.behaviour = "block"
    created = await persistence.investigations.create(ALARM, session=await _engineer(persistence))
    stream = asyncio.create_task(_collect(persistence, created.investigation_id))
    await asyncio.wait_for(runner.started.wait(), 10)
    await asyncio.sleep(0.2)
    assert not stream.done()
    runner.release.set()
    assert _types(await stream)[-1] == "end"


@pytest.mark.parametrize(
    ("behaviour", "code"),
    [("raise", "internal_error"), ("upstream", "upstream_error"), ("incomplete", "internal_error")],
)
async def test_runner_failures_fail_the_investigation_and_reopen_the_alarm(
    persistence: Persistence, runner: FakeRunner, behaviour: str, code: str
) -> None:
    runner.behaviour = behaviour  # type: ignore[assignment]
    created = await persistence.investigations.create(ALARM, session=await _engineer(persistence))
    events = await _collect(persistence, created.investigation_id)
    assert _types(events)[-3:] == ["error", "status", "end"]
    investigation = await persistence.investigations.get(created.investigation_id)
    assert investigation.status == "failed"
    assert investigation.error is not None
    assert investigation.error.code == code
    alarm = await persistence.alarms.get("AL-1043-t2")
    assert (alarm.status, alarm.investigation_id) == ("open", None)
    again = await persistence.investigations.create(ALARM, session=await _engineer(persistence))
    assert again.investigation_id != created.investigation_id


async def test_a_runner_reporting_failure_ends_the_stream(
    persistence: Persistence, runner: FakeRunner
) -> None:
    runner.behaviour = "fail"
    created = await persistence.investigations.create(ALARM, session=await _engineer(persistence))
    events = await _collect(persistence, created.investigation_id)
    assert _types(events)[-3:] == ["error", "status", "end"]
    assert (await persistence.alarms.get("AL-1043-t2")).status == "open"


async def test_without_a_runner_the_job_fails_cleanly(persistence: Persistence) -> None:
    worker = JobWorker(
        persistence.database.sessionmaker,
        persistence.investigations,
        lambda: None,
        persistence.notifier,
    )
    await persistence.jobs.stop()
    await worker.start()
    try:
        created = await persistence.investigations.create(
            ALARM, session=await _engineer(persistence)
        )
        events = await _collect(persistence, created.investigation_id)
    finally:
        await worker.stop()
    error = events[-3]
    assert error.type == "error"
    assert error.problem.code == "not_ready"
    assert (await persistence.investigations.get(created.investigation_id)).status == "failed"


async def test_list_pages_newest_first_with_a_status_filter(persistence: Persistence) -> None:
    session = await _engineer(persistence)
    ids = []
    for unit in range(5):
        created = await persistence.investigations.create(
            InvestigationTrigger(kind="unit", ref=str(unit)), session=session
        )
        ids.append(created.investigation_id)
        await _collect(persistence, created.investigation_id)
    page = await persistence.investigations.list(limit=2)
    seen = [i.investigation_id for i in page.items]
    while page.next_cursor:
        page = await persistence.investigations.list(cursor=page.next_cursor, limit=2)
        seen += [i.investigation_id for i in page.items]
    assert seen == ids[::-1]
    assert page.total == 5
    assert (await persistence.investigations.list(status="awaiting_decision")).total == 5
    assert (await persistence.investigations.list(status="approved")).items == []
    with pytest.raises(InvalidArgumentError):
        await persistence.investigations.list(cursor="bogus")


async def test_a_stale_run_is_failed_and_a_stale_resume_is_applied(
    persistence: Persistence,
) -> None:
    session = await _engineer(persistence)
    waiting = await persistence.investigations.create(ALARM, session=session)
    await _collect(persistence, waiting.investigation_id)
    await persistence.jobs.stop()
    await persistence.investigations.decide(
        waiting.investigation_id, DecisionCreate(verdict="approve"), session=session
    )
    lost_run = await persistence.investigations.create(
        InvestigationTrigger(kind="unit", ref="9"), session=session
    )
    long_ago = datetime.now(UTC) - timedelta(minutes=10)
    async with persistence.database.sessionmaker() as db, db.begin():
        await db.execute(
            update(InvestigationJobRow)
            .where(InvestigationJobRow.status == "queued")
            .values(status="running", heartbeat_at=long_ago, worker="dead-process", attempts=1)
        )

    worker = JobWorker(
        persistence.database.sessionmaker,
        persistence.investigations,
        lambda: FakeRunner(),
        persistence.notifier,
        stale_after_s=1,
    )
    await worker.start()
    try:
        failed = await _collect(persistence, lost_run.investigation_id)
        decided = await _collect(persistence, waiting.investigation_id, after=9)
    finally:
        await worker.stop()
    assert failed[-3].type == "error"
    assert failed[-3].problem.title == "Investigation interrupted"
    assert _types(decided) == ["decision", "status", "end"]
    assert (await persistence.investigations.get(waiting.investigation_id)).status == "approved"


async def test_shutdown_interrupts_a_running_job(
    persistence: Persistence, runner: FakeRunner
) -> None:
    runner.behaviour = "block"
    created = await persistence.investigations.create(ALARM, session=await _engineer(persistence))
    await asyncio.wait_for(runner.started.wait(), 10)
    await persistence.jobs.stop()
    investigation = await persistence.investigations.get(created.investigation_id)
    assert investigation.status == "failed"
    assert investigation.error is not None
    assert investigation.error.title == "Investigation interrupted"
    async with persistence.database.sessionmaker() as db:
        statuses = (await db.scalars(select(InvestigationJobRow.status))).all()
    assert statuses == ["failed"]


async def test_two_processes_share_the_queue_and_the_streams(database_url: str) -> None:
    """Two independent persistence stacks (as in two API processes) on one database."""
    await clean(database_url)
    settings = Settings(environment="test", log_json=False, database_url=SecretStr(database_url))
    runners = [FakeRunner(), FakeRunner()]
    stacks = [
        build_persistence(settings, runner_provider=_provider(runner), migrate=False)
        for runner in runners
    ]
    for stack in stacks:
        for resource in stack.resources:
            await resource.start()
    try:
        session = await _engineer(stacks[0])
        created = [
            await stacks[i % 2].investigations.create(
                InvestigationTrigger(kind="unit", ref=str(i)), session=session
            )
            for i in range(8)
        ]
        for i, investigation in enumerate(created):
            events = await _collect(stacks[(i + 1) % 2], investigation.investigation_id)
            assert _types(events)[-1] == "end"
    finally:
        for stack in stacks:
            for resource in reversed(stack.resources):
                await resource.stop()
    runs = runners[0].runs + runners[1].runs
    assert sorted(runs) == sorted(i.investigation_id for i in created)


async def test_investigations_are_found_by_unit(persistence: Persistence) -> None:
    session = await _engineer(persistence)
    alarm = await persistence.investigations.create(ALARM, session=session)
    unit = await persistence.investigations.create(
        InvestigationTrigger(kind="unit", ref="1043"), session=session
    )
    await persistence.investigations.create(
        InvestigationTrigger(kind="unit", ref="10430"), session=session
    )
    with viewing(session.viewer):
        found = await persistence.investigations.for_unit(1043)
        assert set(found) == {alarm.investigation_id, unit.investigation_id}
        assert await persistence.investigations.for_unit(104) == []
    # Another workspace, and a request of none, find none of them.
    other = await _engineer(persistence)
    with viewing(other.viewer):
        assert await persistence.investigations.for_unit(1043) == []
    assert await persistence.investigations.for_unit(1043) == []


async def test_each_workspace_has_its_own_investigations(persistence: Persistence) -> None:
    store = persistence.investigations
    mine, theirs = await _engineer(persistence), await _engineer(persistence)
    first = await store.create(ALARM, session=mine)
    # The same alarm in another workspace is a new investigation, never the first one.
    second = await store.create(ALARM, session=theirs)
    assert second.investigation_id != first.investigation_id
    assert (await store.create(ALARM, session=mine)).investigation_id == first.investigation_id
    assert [i.investigation_id for i in (await store.list(viewer=mine.viewer)).items] == [
        first.investigation_id
    ]
    assert (await store.list(viewer=theirs.viewer)).total == 1
    assert (await store.list(viewer=NOBODY)).total == 0
    with pytest.raises(NotFoundError) as hidden:
        await store.get(first.investigation_id, theirs.viewer)
    assert "does not exist" in str(hidden.value)
    with pytest.raises(NotFoundError):
        await store.get_evidence(first.investigation_id, "E1", theirs.viewer)
    for investigation in (first, second):
        async with asyncio.timeout(15):
            async for _ in store.events(investigation.investigation_id):
                pass
    with pytest.raises(NotFoundError):
        await store.decide(first.investigation_id, DecisionCreate(verdict="reject"), session=theirs)
    assert (await store.get(first.investigation_id)).status == "awaiting_decision"


async def test_a_run_past_its_wall_time_is_failed_and_its_alarm_reopened(
    persistence: Persistence, runner: FakeRunner
) -> None:
    runner.behaviour = "block"  # a run that never ends (the live run waited on hung calls)
    await persistence.jobs.stop()
    worker = JobWorker(
        persistence.database.sessionmaker,
        persistence.investigations,
        _provider(runner),
        persistence.notifier,
        run_timeout_s=0.5,
    )
    await worker.start()
    try:
        created = await persistence.investigations.create(
            ALARM, session=await _engineer(persistence)
        )
        events = await _collect(persistence, created.investigation_id)
    finally:
        await worker.stop()
        runner.release.set()
    assert _types(events)[-3:] == ["error", "status", "end"]
    investigation = await persistence.investigations.get(created.investigation_id)
    assert investigation.status == "failed"
    assert investigation.error is not None
    assert investigation.error.title == "Investigation timed out"
    assert "did not finish within" in (investigation.error.detail or "")
    alarm = await persistence.alarms.get("AL-1043-t2")
    assert (alarm.status, alarm.investigation_id) == ("open", None)


async def test_a_run_left_running_without_a_live_job_is_failed_at_startup(
    persistence: Persistence, runner: FakeRunner
) -> None:
    # The container stopped between the job's end and the run's close: no job is live.
    await persistence.jobs.stop()
    created = await persistence.investigations.create(ALARM, session=await _engineer(persistence))
    long_ago = datetime.now(UTC) - timedelta(minutes=10)
    async with persistence.database.sessionmaker() as db, db.begin():
        await db.execute(update(InvestigationJobRow).values(status="done"))
        await db.execute(
            update(InvestigationRow)
            .where(InvestigationRow.investigation_id == created.investigation_id)
            .values(status="running", updated_at=long_ago)
        )
    worker = JobWorker(
        persistence.database.sessionmaker,
        persistence.investigations,
        _provider(runner),
        persistence.notifier,
        stale_after_s=1,
    )
    await worker.start()
    try:
        events = await _collect(persistence, created.investigation_id)
    finally:
        await worker.stop()
    assert _types(events)[-3:] == ["error", "status", "end"]
    assert runner.runs == []  # closed by the sweep, not run
    investigation = await persistence.investigations.get(created.investigation_id)
    assert investigation.status == "failed"
    assert investigation.error is not None
    assert investigation.error.title == "Investigation interrupted"
    assert (await persistence.alarms.get("AL-1043-t2")).status == "open"


RUN_ALARM = InvestigationTrigger(kind="run_alarm", ref=f"{RUN_ID}:RA-1")


async def test_run_alarm_references_and_titles() -> None:
    assert trigger_title(RUN_ALARM) == f"Run alarm RA-1 in {RUN_ID}"
    for ref in ("RA-1", f"{RUN_ID}:AL-1-t2", f"{RUN_ID}:RA-1234567", "run_x:RA-1"):
        with pytest.raises(InvalidArgumentError):
            trigger_title(InvestigationTrigger(kind="run_alarm", ref=ref))
    runs = FakeRuns()
    assert await check_run_alarm(runs, RUN_ALARM) == (
        "Sensor relationships broke (SPE) on unit U-3 (RA-1)"
    )
    lot = InvestigationTrigger(kind="run_alarm", ref=f"{RUN_ID}:RA-3")
    assert await check_run_alarm(runs, lot) == f"Pattern repeats in the lot on lot {LOT} (RA-3)"
    with pytest.raises(NotFoundError, match="has no alarm RA-9"):
        await check_run_alarm(runs, InvestigationTrigger(kind="run_alarm", ref=f"{RUN_ID}:RA-9"))
    with pytest.raises(NotFoundError, match="does not exist or has expired"):
        await check_run_alarm(
            runs, InvestigationTrigger(kind="run_alarm", ref="run_doesnotexist:RA-1")
        )
    with pytest.raises(NotReadyError):
        await check_run_alarm(None, RUN_ALARM)


async def test_a_run_alarm_is_investigated_once_at_a_time_and_found_by_run(
    persistence: Persistence,
) -> None:
    store = persistence.investigations
    session = await _engineer(persistence)
    title = await check_run_alarm(FakeRuns(), RUN_ALARM)
    first = await store.create(RUN_ALARM, session=session, title=title)
    assert first.title == title
    again = await store.create(RUN_ALARM, session=session, title=title)
    assert again.investigation_id == first.investigation_id
    other = await store.create(
        InvestigationTrigger(kind="run_alarm", ref=f"{RUN_ID}:RA-2"), session=session
    )
    await _collect(persistence, first.investigation_id)
    await store.decide(first.investigation_id, DecisionCreate(verdict="reject"), session=session)
    await _collect(persistence, first.investigation_id, after=9)
    newer = await store.create(RUN_ALARM, session=session, title=title)
    assert newer.investigation_id != first.investigation_id  # the first one is closed
    assert await store.for_run(RUN_ID) == {
        "RA-1": newer.investigation_id,
        "RA-2": other.investigation_id,
    }
    assert await store.for_run("run_testcase000") == {}  # a prefix of the ID is another run
    assert await store.for_run("run_testcase_001") == {}  # "_" is not a wildcard
