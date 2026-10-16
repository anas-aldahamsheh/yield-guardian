"""Workspaces and device sessions (the owner's rules of 2026-10-15): every visitor is a separate
user without signing in, a role change keeps the workspace, a handoff code attaches one more
device once, a workspace lives 30 days after its last use and then goes with everything in it,
and the admin sees sessions and counts, never a token. Runs are on real SECOM units; the
investigator is the FakeRunner double."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from pydantic import SecretStr
from sqlalchemy import func, select, text, update

from tests.db.conftest import ADMIN_PASSWORD, ADMIN_USERNAME
from tests.db.fakes import FakeRunner
from tests.db.test_runs import ORIGIN, units
from yield_guardian.agent.wiring import psycopg_conninfo
from yield_guardian.contracts.investigation import (
    DecisionCreate,
    InvestigationTrigger,
)
from yield_guardian.contracts.runs import Run, UploadSummary
from yield_guardian.contracts.services import InvalidArgumentError, InvestigationSink, NotFoundError
from yield_guardian.contracts.session import GuestSessionCreate, LoginRequest
from yield_guardian.contracts.workspace import WorkRunUpdate
from yield_guardian.db.tables import (
    AuditEntryRow,
    HandoffRow,
    InvestigationRow,
    RunRow,
    SessionRow,
    UploadRow,
    WorkOrderRow,
    WorkspaceRow,
)
from yield_guardian.live.runs import RunOrchestrator
from yield_guardian.services.access import NOBODY, Viewer, current_viewer
from yield_guardian.services.persistence import Persistence
from yield_guardian.services.protocols import VISITOR, ActiveSession
from yield_guardian.services.runs import RUN_TTL, WORKSPACE_LIFE, DbRunStore, GoneError, RunInput
from yield_guardian.services.sessions import (
    CHECKPOINT_TABLES,
    CODE_USED,
    NO_SUCH_CODE,
    NOT_A_CODE,
    SAME_WORKSPACE,
    normalise_code,
)


class ViewingRunner(FakeRunner):
    """The FakeRunner, also noting which workspace each investigation job acts for and which
    of the `probe` runs it could read while it ran."""

    def __init__(self) -> None:
        super().__init__()
        self.viewers: list[Viewer | None] = []
        self.probe: list[str] = []
        self.readable: list[list[str]] = []
        self.reader: DbRunStore | None = None

    async def run(
        self,
        investigation_id: str,
        trigger: InvestigationTrigger,
        sink: InvestigationSink,
        *,
        as_of: int | None = None,
    ) -> None:
        self.viewers.append(current_viewer())
        if self.reader is not None:
            found: list[Run | None] = [await self.reader.get_run(r) for r in self.probe]
            self.readable.append([r.run_id for r in found if r is not None])
        await super().run(investigation_id, trigger, sink, as_of=as_of)


@pytest.fixture
def runner() -> ViewingRunner:
    return ViewingRunner()


async def visitor(persistence: Persistence) -> tuple[ActiveSession, str]:
    return await persistence.sessions.open_visitor(client="test")


async def engineer(persistence: Persistence, name: str = "Mia") -> ActiveSession:
    opened, _ = await visitor(persistence)
    session, _ = await persistence.sessions.guest(
        GuestSessionCreate(display_name=name), client="test", current=opened
    )
    return session


async def run_of(persistence: Persistence, owner: str | None, n: int = 2) -> str:
    data = RunInput(units=units(n))
    run = await persistence.runs.create(ORIGIN, data, RunOrchestrator.plan(data), owner=owner)
    return run.run_id


async def upload_of(persistence: Persistence, owner: str | None) -> str:
    data = RunInput(units=units(3))

    def summary(upload_id: str, expires_at: datetime) -> UploadSummary:
        return UploadSummary(
            upload_id=upload_id,
            kind="sensors",
            filename="units.csv",
            units=3,
            wafers=0,
            lots=0,
            missing_readings=0,
            issues=[],
            runnable=True,
            expires_at=expires_at,
        )

    made = await persistence.runs.create_upload(
        kind="sensors", filename="units.csv", data=data, summary=summary, owner=owner
    )
    return made.upload_id


async def drain(persistence: Persistence, investigation_id: str, after: int = 0) -> None:
    async with asyncio.timeout(15):
        async for _ in persistence.investigations.events(investigation_id, after_seq=after):
            pass


async def count(persistence: Persistence, query: Any) -> int:
    async with persistence.database.sessionmaker() as db:
        return int(await db.scalar(query) or 0)


SOMEONE_ELSE = "inv_someoneelse0"
"""The thread of an investigation in no workspace this test deletes."""


async def pause(database_url: str, *threads: str) -> None:
    """Saved investigator state of these investigations, in LangGraph's own tables (its setup
    makes them, as the API does when it starts): a checkpoint with a blob, and a pending write."""
    async with AsyncPostgresSaver.from_conn_string(psycopg_conninfo(database_url)) as saver:
        await saver.setup()
        for thread in threads:
            checkpoint = empty_checkpoint()
            # Not a primitive, so the saver keeps it as a blob.
            checkpoint["channel_values"] = {"report": {"findings": ["E1"]}}
            checkpoint["channel_versions"] = {"report": "1"}
            saved = await saver.aput(
                {"configurable": {"thread_id": thread, "checkpoint_ns": ""}},
                checkpoint,
                {},
                {"report": "1"},
            )
            await saver.aput_writes(saved, [("report", "draft")], task_id="task")


async def threads_in(persistence: Persistence, table: str) -> set[str]:
    async with persistence.database.sessionmaker() as db:
        return set((await db.scalars(text(f"SELECT DISTINCT thread_id FROM {table}"))).all())


# Sessions -------------------------------------------------------------------------------------


async def test_a_first_visit_opens_a_visitor_session_with_its_own_workspace(
    persistence: Persistence,
) -> None:
    before = datetime.now(UTC)
    first, token = await visitor(persistence)
    second, _ = await visitor(persistence)
    assert (first.role, first.display_name, first.expires_at) == ("visitor", None, None)
    assert first.workspace_id is not None
    assert first.workspace_id != second.workspace_id
    assert first.csrf_token
    assert first.csrf_token != second.csrf_token
    assert first.session_expires_at is not None
    assert before + WORKSPACE_LIFE <= first.session_expires_at <= datetime.now(UTC) + WORKSPACE_LIFE
    assert await persistence.sessions.resolve(token) == first
    info = first.info()
    assert info.workspace is not None
    assert info.workspace.workspace_id == first.workspace_id
    assert (await persistence.sessions.workspace(first)).devices[0].current


async def test_a_role_keeps_the_workspace_and_its_csrf_token_and_rotates_the_cookie(
    persistence: Persistence,
) -> None:
    sessions = persistence.sessions
    opened, token = await visitor(persistence)
    raised, raised_token = await sessions.guest(
        GuestSessionCreate(display_name="Mia"), client="test", current=opened
    )
    assert (raised.role, raised.display_name) == ("engineer", "Mia")
    assert (raised.session_id, raised.workspace_id, raised.csrf_token) == (
        opened.session_id,
        opened.workspace_id,
        opened.csrf_token,
    )
    assert raised_token != token
    assert await sessions.resolve(token) is VISITOR  # a token planted before is worthless
    admin, admin_token = await sessions.login(
        LoginRequest(username=ADMIN_USERNAME, password=SecretStr(ADMIN_PASSWORD)),
        client="test",
        current=raised,
    )
    assert (admin.role, admin.workspace_id) == ("admin", opened.workspace_id)
    ended = await sessions.logout(admin)
    assert ended is not None
    back, back_token = ended
    assert (back.role, back.workspace_id, back.csrf_token) == (
        "visitor",
        opened.workspace_id,
        opened.csrf_token,
    )
    assert await sessions.resolve(admin_token) is VISITOR
    assert await sessions.resolve(back_token) == back
    assert await sessions.logout(back) is None  # nothing left to sign out
    actions = [e.action for e in (await persistence.audit.list(viewer=back.viewer)).items]
    assert actions == ["session.logout", "session.login", "session.guest"]


async def test_an_ended_role_goes_back_to_visitor_in_the_same_workspace(
    persistence: Persistence,
) -> None:
    opened, _ = await visitor(persistence)
    raised, token = await persistence.sessions.guest(
        GuestSessionCreate(display_name="Mia"), client="test", current=opened
    )
    async with persistence.database.sessionmaker() as db, db.begin():
        await db.execute(
            update(SessionRow)
            .where(SessionRow.session_id == opened.session_id)
            .values(role_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    resolved = await persistence.sessions.resolve(token)
    assert (resolved.role, resolved.display_name, resolved.expires_at) == ("visitor", None, None)
    assert (resolved.session_id, resolved.workspace_id) == (raised.session_id, raised.workspace_id)


async def test_each_use_moves_the_workspace_life_on(persistence: Persistence) -> None:
    opened, token = await visitor(persistence)
    long_ago = datetime.now(UTC) - timedelta(days=20)
    async with persistence.database.sessionmaker() as db, db.begin():
        await db.execute(
            update(SessionRow)
            .where(SessionRow.session_id == opened.session_id)
            .values(last_seen_at=long_ago, expires_at=long_ago + WORKSPACE_LIFE)
        )
        await db.execute(
            update(WorkspaceRow)
            .where(WorkspaceRow.workspace_id == opened.workspace_id)
            .values(last_seen_at=long_ago)
        )
    run_id = await run_of(persistence, opened.workspace_id)
    kept = (await persistence.runs.get(run_id, opened.viewer)).expires_at
    assert kept == long_ago + WORKSPACE_LIFE
    resolved = await persistence.sessions.resolve(token)  # this visit moves both on
    assert resolved.session_expires_at is not None
    assert resolved.session_expires_at > datetime.now(UTC) + WORKSPACE_LIFE - timedelta(minutes=1)
    moved = (await persistence.runs.get(run_id, opened.viewer)).expires_at
    assert moved is not None
    assert moved > datetime.now(UTC) + WORKSPACE_LIFE - timedelta(minutes=1)


# Handoff --------------------------------------------------------------------------------------


async def test_a_handoff_code_attaches_one_more_device_once(persistence: Persistence) -> None:
    sessions = persistence.sessions
    laptop, _ = await visitor(persistence)
    run_id = await run_of(persistence, laptop.workspace_id)
    made = await sessions.create_handoff(laptop)
    raw = normalise_code(made.code)
    assert raw is not None
    assert len(made.code) == 14
    assert made.code.count("-") == 2
    assert made.join_path == f"/join#code={made.code}"
    assert timedelta(minutes=9) < made.expires_at - datetime.now(UTC) <= timedelta(minutes=10)
    async with persistence.database.sessionmaker() as db:
        stored = (await db.scalars(select(HandoffRow))).one()
        entries = (await db.scalars(select(AuditEntryRow))).all()
    assert stored.code_hash == hashlib.sha256(raw.encode()).digest()  # only the hash is kept
    assert all(raw not in json.dumps(e.details) and made.code not in e.target_id for e in entries)

    phone, phone_token = await visitor(persistence)
    with pytest.raises(NotFoundError):
        await persistence.runs.get(run_id, phone.viewer)
    typed = made.code.lower().replace("-", " ").replace("1", "l").replace("0", "o")
    joined, joined_token = await sessions.join(phone, typed)  # case, spaces and lookalikes
    assert (joined.workspace_id, joined.role) == (laptop.workspace_id, "visitor")
    assert joined.session_id == phone.session_id
    assert await sessions.resolve(phone_token) is VISITOR
    assert await sessions.resolve(joined_token) == joined
    assert (await persistence.runs.get(run_id, joined.viewer)).run_id == run_id
    summary = await sessions.workspace(joined)
    assert [d.current for d in summary.devices].count(True) == 1
    assert (len(summary.devices), summary.runs) == (2, 1)

    third, _ = await visitor(persistence)
    with pytest.raises(GoneError, match=CODE_USED):
        await sessions.join(third, made.code)
    with pytest.raises(InvalidArgumentError, match=NOT_A_CODE):
        await sessions.join(third, "not a code")
    with pytest.raises(NotFoundError, match=NO_SUCH_CODE):
        await sessions.join(third, "0000-0000-0000")
    actions = [e.action for e in (await persistence.audit.list(viewer=laptop.viewer)).items]
    assert actions == ["workspace.joined", "workspace.handoff_created"]


async def test_a_handoff_code_ends_is_replaced_and_is_not_for_its_own_workspace(
    persistence: Persistence,
) -> None:
    sessions = persistence.sessions
    laptop, _ = await visitor(persistence)
    phone, _ = await visitor(persistence)
    first = await sessions.create_handoff(laptop)
    second = await sessions.create_handoff(laptop)
    with pytest.raises(NotFoundError):
        await sessions.join(phone, first.code)  # a new code replaces the last unused one
    with pytest.raises(InvalidArgumentError, match=SAME_WORKSPACE):
        await sessions.join(laptop, second.code)
    async with persistence.database.sessionmaker() as db, db.begin():
        await db.execute(
            update(HandoffRow).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    with pytest.raises(GoneError, match="minutes"):
        await sessions.join(phone, second.code)
    assert (await persistence.sessions.prune()).handoffs == 1


async def test_joining_brings_this_devices_own_work_unless_another_device_shares_it(
    persistence: Persistence,
) -> None:
    sessions = persistence.sessions
    laptop, _ = await visitor(persistence)
    phone, _ = await visitor(persistence)
    phone_run = await run_of(persistence, phone.workspace_id)
    phone_upload = await upload_of(persistence, phone.workspace_id)
    joined, _ = await sessions.join(phone, (await sessions.create_handoff(laptop)).code)
    listed = await persistence.workspace.list_runs(laptop.workspace_id)
    assert [r.run_id for r in listed.items] == [phone_run]  # nothing made on the phone is lost
    uploads = await persistence.workspace.list_uploads(laptop.workspace_id)
    assert [u.upload_id for u in uploads.items] == [phone_upload]
    assert (await persistence.runs.get(phone_run, joined.viewer)).run_id == phone_run

    # A workspace another device still uses keeps its own work.
    tablet, _ = await visitor(persistence)
    desk, _ = await visitor(persistence)
    shared, _ = await sessions.join(desk, (await sessions.create_handoff(tablet)).code)
    shared_run = await run_of(persistence, tablet.workspace_id)
    await sessions.join(tablet, (await sessions.create_handoff(laptop)).code)
    assert (await persistence.runs.get(shared_run, shared.viewer)).run_id == shared_run
    with pytest.raises(NotFoundError):
        await persistence.runs.get(shared_run, laptop.viewer)


async def test_a_fresh_workspace_leaves_the_old_one_to_the_other_devices(
    persistence: Persistence,
) -> None:
    sessions = persistence.sessions
    laptop, _ = await visitor(persistence)
    phone, _ = await visitor(persistence)
    phone, _ = await sessions.join(phone, (await sessions.create_handoff(laptop)).code)
    run_id = await run_of(persistence, laptop.workspace_id)
    assert (await sessions.prune()).workspaces == 1  # the phone's own, emptied when it joined
    fresh, _ = await sessions.fresh(phone)
    assert fresh.workspace_id not in (None, laptop.workspace_id)
    assert (fresh.session_id, fresh.csrf_token) == (phone.session_id, phone.csrf_token)
    with pytest.raises(NotFoundError):
        await persistence.runs.get(run_id, fresh.viewer)
    assert (await persistence.workspace.list_runs(fresh.workspace_id)).total == 0
    assert (await sessions.prune()).workspaces == 0  # the laptop still uses the old one

    alone, _ = await sessions.fresh(laptop)  # nobody can reach the old workspace now
    report = await sessions.prune()
    assert report.workspaces == 1
    assert await count(persistence, select(func.count()).select_from(RunRow)) == 0
    assert (await persistence.workspace.list_runs(alone.workspace_id)).total == 0


# Lifetimes ------------------------------------------------------------------------------------


async def test_a_workspace_goes_30_days_after_its_last_use_with_everything_in_it(
    persistence: Persistence, runner: ViewingRunner, database_url: str
) -> None:
    old = await engineer(persistence, "Old")
    recent = await engineer(persistence, "Recent")
    old_run = await run_of(persistence, old.workspace_id)
    await upload_of(persistence, old.workspace_id)
    nobodys_run = await run_of(persistence, None)
    recent_run = await run_of(persistence, recent.workspace_id)
    investigation = await persistence.investigations.create(
        InvestigationTrigger(kind="unit", ref="1043"), session=old
    )
    await drain(persistence, investigation.investigation_id)
    await persistence.investigations.decide(
        investigation.investigation_id, DecisionCreate(verdict="approve", actions=[0]), session=old
    )
    await drain(persistence, investigation.investigation_id, after=9)
    assert await count(persistence, select(func.count()).select_from(WorkOrderRow)) == 1
    mine = investigation.investigation_id
    await pause(database_url, mine, SOMEONE_ELSE)
    for table in CHECKPOINT_TABLES:
        assert {mine, SOMEONE_ELSE} <= await threads_in(persistence, table), table
    async with persistence.database.sessionmaker() as db, db.begin():
        # Thirty days and a second since anyone used the old workspace.
        gone = datetime.now(UTC) - WORKSPACE_LIFE - timedelta(seconds=1)
        await db.execute(
            update(WorkspaceRow)
            .where(WorkspaceRow.workspace_id == old.workspace_id)
            .values(last_seen_at=gone)
        )
        await db.execute(
            update(SessionRow)
            .where(SessionRow.workspace_id == old.workspace_id)
            .values(last_seen_at=gone, expires_at=gone + WORKSPACE_LIFE)
        )
    try:
        report = await persistence.sessions.prune()
        assert (report.sessions, report.workspaces, report.investigations) == (1, 1, 1)
        for model in (RunRow, UploadRow, InvestigationRow, AuditEntryRow):
            query = select(func.count()).select_from(model)
            assert (
                await count(persistence, query.where(model.workspace_id == old.workspace_id)) == 0
            )
        assert await count(persistence, select(func.count()).select_from(WorkOrderRow)) == 0
        for table in CHECKPOINT_TABLES:
            left = await threads_in(persistence, table)
            assert mine not in left, table
            assert SOMEONE_ELSE in left, table
        with pytest.raises((NotFoundError, GoneError)):
            await persistence.runs.get(old_run)
        assert (await persistence.runs.get(nobodys_run)).run_id == nobodys_run
        assert (await persistence.runs.get(recent_run, recent.viewer)).run_id == recent_run
        assert (await persistence.workspace.list_runs(recent.workspace_id)).total == 1
    finally:
        async with persistence.database.sessionmaker() as db, db.begin():
            for table in CHECKPOINT_TABLES:
                await db.execute(
                    text(f"DELETE FROM {table} WHERE thread_id = ANY(:ids)"),
                    {"ids": [mine, SOMEONE_ELSE]},
                )


async def test_a_workspaces_runs_and_uploads_outlive_the_24_hours_of_runs_of_nobody(
    persistence: Persistence,
) -> None:
    mine, _ = await visitor(persistence)
    owned_run = await run_of(persistence, mine.workspace_id)
    owned_upload = await upload_of(persistence, mine.workspace_id)
    nobodys_run = await run_of(persistence, None)
    nobodys_upload = await upload_of(persistence, None)
    run = await persistence.runs.get(owned_run, mine.viewer)
    assert run.expires_at is not None
    assert run.expires_at - run.created_at > RUN_TTL
    other = await persistence.runs.get(nobodys_run)
    assert other.expires_at is not None
    assert other.expires_at - other.created_at == RUN_TTL
    async with persistence.database.sessionmaker() as db, db.begin():
        day_ago = datetime.now(UTC) - RUN_TTL - timedelta(seconds=1)
        await db.execute(update(RunRow).values(created_at=day_ago))
        await db.execute(
            update(RunRow).where(RunRow.workspace_id.is_(None)).values(expires_at=day_ago)
        )
        await db.execute(
            update(UploadRow).where(UploadRow.workspace_id.is_(None)).values(expires_at=day_ago)
        )
    report = await persistence.runs.prune()
    assert (report.runs, report.uploads) == (1, 1)
    assert (await persistence.runs.get(owned_run, mine.viewer)).run_id == owned_run
    summary, _ = await persistence.runs.get_upload(owned_upload, mine.viewer)
    assert summary.expires_at > datetime.now(UTC) + WORKSPACE_LIFE - timedelta(minutes=1)
    with pytest.raises(NotFoundError):  # pruned; its ID is too young to say "expired"
        await persistence.runs.get_upload(nobodys_upload)


# What another workspace gets -------------------------------------------------------------------


async def test_another_workspaces_run_and_upload_answer_as_missing_ones(
    persistence: Persistence,
) -> None:
    mine, _ = await visitor(persistence)
    theirs, _ = await visitor(persistence)
    run_id = await run_of(persistence, mine.workspace_id)
    upload_id = await upload_of(persistence, mine.workspace_id)
    missing_run = run_id[:-6] + "zzzzzz"  # the same time inside the ID, never made
    missing_upload = upload_id[:-6] + "zzzzzz"
    for viewer in (theirs.viewer, NOBODY):
        with pytest.raises(NotFoundError) as hidden:
            await persistence.runs.get(run_id, viewer)
        with pytest.raises(NotFoundError) as missing:
            await persistence.runs.get(missing_run, viewer)
        assert str(hidden.value).replace(run_id, "?") == str(missing.value).replace(
            missing_run, "?"
        )
        with pytest.raises(NotFoundError) as hidden:
            await persistence.runs.get_upload(upload_id, viewer)
        with pytest.raises(NotFoundError) as missing:
            await persistence.runs.get_upload(missing_upload, viewer)
        assert str(hidden.value).replace(upload_id, "?") == str(missing.value).replace(
            missing_upload, "?"
        )
        with pytest.raises(NotFoundError):
            await persistence.runs.unit_chart(run_id, 0, viewer)
        with pytest.raises(NotFoundError):
            await persistence.runs.get_input(run_id, viewer)
        with pytest.raises(NotFoundError):
            await persistence.workspace.update_run(
                viewer.workspace_id, run_id, WorkRunUpdate(label="Mine")
            )
    assert (await persistence.workspace.list_runs(theirs.workspace_id)).total == 0
    assert (await persistence.workspace.list_uploads(theirs.workspace_id)).total == 0
    # A run of no workspace opens for anyone by its ID and is in nobody's list.
    nobodys = await run_of(persistence, None)
    assert (await persistence.runs.get(nobodys, theirs.viewer)).run_id == nobodys
    assert [r.run_id for r in (await persistence.workspace.list_runs(mine.workspace_id)).items] == [
        run_id
    ]
    with pytest.raises(NotFoundError, match="not in this workspace"):
        await persistence.workspace.update_run(
            mine.workspace_id, nobodys, WorkRunUpdate(label="Mine")
        )


async def test_an_investigation_job_reads_only_its_own_workspace(
    persistence: Persistence, runner: ViewingRunner
) -> None:
    mine = await engineer(persistence, "Mine")
    theirs = await engineer(persistence, "Theirs")
    my_run = await run_of(persistence, mine.workspace_id)
    their_run = await run_of(persistence, theirs.workspace_id)
    nobodys_run = await run_of(persistence, None)
    runner.reader = persistence.runs
    runner.probe = [my_run, their_run, nobodys_run]
    created = await persistence.investigations.create(
        InvestigationTrigger(kind="unit", ref="1043"), session=mine
    )
    await drain(persistence, created.investigation_id)
    assert runner.viewers == [mine.viewer]
    assert runner.readable == [[my_run, nobodys_run]]


# Admin ----------------------------------------------------------------------------------------


async def test_the_admin_sees_sessions_and_counts_never_a_token(persistence: Persistence) -> None:
    sessions = persistence.sessions
    opened = [await visitor(persistence) for _ in range(3)]
    await run_of(persistence, opened[0][0].workspace_id)
    await upload_of(persistence, opened[0][0].workspace_id)
    admin, _ = await sessions.login(
        LoginRequest(username=ADMIN_USERNAME, password=SecretStr(ADMIN_PASSWORD)), client="test"
    )
    page = await sessions.list_sessions(current=admin, limit=2)
    rest = await sessions.list_sessions(current=admin, cursor=page.next_cursor, limit=10)
    listed = page.items + rest.items
    assert (page.total, page.workspaces, len(listed)) == (4, 4, 4)
    assert [s.current for s in listed].count(True) == 1
    first = next(s for s in listed if s.session_id == opened[0][0].session_id)
    assert (first.runs, first.uploads, first.investigations, first.devices) == (1, 1, 0, 1)
    dumped = page.model_dump_json() + rest.model_dump_json()
    for session, token in opened:
        assert token not in dumped
        assert session.csrf_token is not None
        assert session.csrf_token not in dumped
    assert admin.csrf_token is not None
    assert admin.csrf_token not in dumped

    target, token = opened[1]
    await sessions.revoke(target.session_id, by=admin)
    assert await sessions.resolve(token) is VISITOR
    with pytest.raises(NotFoundError):
        await sessions.revoke(target.session_id, by=admin)
    revoked = await persistence.audit.list(action="session.revoked", viewer=admin.viewer)
    assert [e.target_id for e in revoked.items] == [target.session_id]
    assert (await sessions.prune()).workspaces == 1  # nobody can reach its workspace now
