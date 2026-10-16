"""Your work: the runs, uploads and investigations one workspace started, newest first, with their
live status and what each still needs (PLAN_V2 §3, the owner's "keep the context" ask).

Every list is one workspace's own (:mod:`yield_guardian.services.access`): nothing of another
workspace, and nothing of no workspace, is ever in it. Lists read only the columns they show (a
run's stage statuses, never its stage results), so a page stays cheap however large the runs are.
Everything listed is kept as long as the workspace: until 30 days after it was last used, which
each item reports as its `expires_at`. Archived runs leave the list and come back with
``archived=True``.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import parse_qsl

from sqlalchemy import ColumnElement, Select, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import load_only

from yield_guardian.agent.run_results import parse_run_alarm_ref
from yield_guardian.contracts.investigation import InvestigationStatus
from yield_guardian.contracts.runs import RunOrigin, RunStatus, StageId, UploadKind
from yield_guardian.contracts.services import InvalidArgumentError, NotFoundError
from yield_guardian.contracts.workspace import (
    WorkInvestigation,
    WorkInvestigationPage,
    WorkNext,
    WorkRun,
    WorkRunInvestigation,
    WorkRunPage,
    WorkRunUpdate,
    WorkUpload,
    WorkUploadPage,
)
from yield_guardian.db.tables import (
    InvestigationRow,
    RunRow,
    RunStageRow,
    UploadRow,
    WorkspaceRow,
)
from yield_guardian.services import cursors
from yield_guardian.services.investigations import to_summary
from yield_guardian.services.run_export import turns_red
from yield_guardian.services.runs import (
    STAGES,
    WORKSPACE_LIFE,
    missing,
    used_by_investigation,
)

RUN_CURSOR = "wrun"
UPLOAD_CURSOR = "wupl"
INVESTIGATION_CURSOR = "winv"
VIEW_KEYS = frozenset({"run", "station", "unit", "wafer", "lot", "alarm"})
FINISHED_STAGES: frozenset[str] = frozenset({"done", "skipped", "failed"})
LIVE_INVESTIGATIONS: frozenset[str] = frozenset({"queued", "running"})
SUMMARY_COLUMNS = (
    InvestigationRow.investigation_id,
    InvestigationRow.title,
    InvestigationRow.status,
    InvestigationRow.trigger_kind,
    InvestigationRow.trigger_ref,
    InvestigationRow.trigger_question,
    InvestigationRow.recorded,
    InvestigationRow.created_at,
    InvestigationRow.updated_at,
    InvestigationRow.models,
    InvestigationRow.usage,
    InvestigationRow.work_order_id,
)


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}" if n == 1 else f"{n:,} {word}s"


def _stage_name(stage: str) -> str:
    return stage.replace("_", " ")


def run_next(
    status: str,
    *,
    current: str | None,
    finished: int,
    failed: Sequence[str],
    alarms: int,
    warnings: int,
    open_alarms: int,
    open_warnings: int,
    investigations: Sequence[WorkRunInvestigation],
) -> WorkNext:
    """What a run still needs, in one sentence: computing, a stage failed, a report waiting for a
    decision, an investigation running, alarms or warnings nobody looked into, or nothing.
    Alarms and warnings are counted as the alarms rail counts them."""
    if status == "queued":
        return WorkNext(kind="running", text="Waiting to start.")
    if status == "running":
        doing = f"Computing {_stage_name(current)}" if current else "Computing"
        return WorkNext(kind="running", text=f"{doing}: {finished} of {len(STAGES)} stages done.")
    waiting = sum(i.status == "awaiting_decision" for i in investigations)
    running = sum(i.status in LIVE_INVESTIGATIONS for i in investigations)
    if waiting:
        text = "A report is" if waiting == 1 else f"{waiting} reports are"
        return WorkNext(kind="decide", text=f"{text} waiting for your decision.")
    if running:
        text = "An investigation is" if running == 1 else f"{running} investigations are"
        return WorkNext(kind="watch", text=f"{text} running.")
    if status == "failed":
        names = ", ".join(_stage_name(s) for s in failed) or "the run"
        return WorkNext(kind="failed", text=f"Stopped at {names}: open it to see why.")
    if open_alarms or open_warnings:
        untouched = [
            _plural(n, what)
            for n, what in ((open_alarms, "alarm"), (open_warnings, "warning"))
            if n
        ]
        return WorkNext(kind="investigate", text=f"{' and '.join(untouched)} not investigated.")
    if alarms or warnings:
        every = "alarm and warning" if alarms and warnings else "alarm" if alarms else "warning"
        return WorkNext(kind="none", text=f"Every {every} has an investigation.")
    return WorkNext(kind="none", text="No alarms: nothing to follow up.")


def investigation_next(status: str, work_order_id: str | None) -> WorkNext:
    if status in LIVE_INVESTIGATIONS:
        return WorkNext(kind="watch", text="Gathering evidence and writing the report.")
    if status == "awaiting_decision":
        return WorkNext(kind="decide", text="The report is ready: approve or reject it.")
    if status == "approved":
        text = f"Approved: work order {work_order_id}." if work_order_id else "Approved."
        return WorkNext(kind="none", text=text)
    if status == "rejected":
        return WorkNext(kind="none", text="Rejected.")
    return WorkNext(kind="failed", text="Stopped before a report: start a new one from the alarm.")


def check_view(run_id: str, view: str) -> str | None:
    """The Line page's query string for this run, kept only with the keys the page reads; the
    `run` must be this run. Empty means no saved view."""
    if not view:
        return None
    pairs = parse_qsl(view, keep_blank_values=False, strict_parsing=False)
    if any(key not in VIEW_KEYS for key, _ in pairs) or dict(pairs).get("run") != run_id:
        raise InvalidArgumentError(
            "The view must be the Line page's query string for this run "
            "(run, station, unit, wafer, lot, alarm)."
        )
    return view


def _ws(workspace_id: str | None) -> uuid.UUID | None:
    try:
        return uuid.UUID(workspace_id) if workspace_id else None
    except ValueError:
        return None


def _page_after(
    query: Select[Any], cursor: str | None, kind: str, created: Any, key: Any
) -> Select[Any]:
    if not cursor:
        return query
    at, identifier = cursors.decode(kind, cursor, str, str)
    try:
        when = datetime.fromisoformat(str(at))
    except ValueError as error:
        raise InvalidArgumentError("The cursor is not valid.") from error
    return query.where(tuple_(created, key) < tuple_(when, identifier))


class DbWorkspaceStore:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        workspace_life: timedelta = WORKSPACE_LIFE,
    ) -> None:
        self._sessionmaker = sessionmaker
        self.workspace_life = workspace_life

    async def _kept_until(self, db: AsyncSession, owner: uuid.UUID) -> datetime:
        """When the workspace goes, and everything in it: `workspace_life` after its last use."""
        seen = await db.scalar(
            select(WorkspaceRow.last_seen_at).where(WorkspaceRow.workspace_id == owner)
        )
        return (seen or datetime.now(UTC)) + self.workspace_life

    # Runs -------------------------------------------------------------------------------------

    @staticmethod
    def _openable(now: datetime) -> ColumnElement[bool]:
        return or_(
            RunRow.expires_at.is_(None),
            RunRow.expires_at > now,
            used_by_investigation(RunRow.run_id),
        )

    async def list_runs(
        self,
        workspace_id: str | None,
        *,
        archived: bool = False,
        cursor: str | None = None,
        limit: int = 20,
    ) -> WorkRunPage:
        owner = _ws(workspace_id)
        if owner is None:
            return WorkRunPage(items=[], total=0)
        where = [
            RunRow.workspace_id == owner,
            RunRow.archived_at.is_not(None) if archived else RunRow.archived_at.is_(None),
        ]
        query = _page_after(
            select(RunRow).where(*where), cursor, RUN_CURSOR, RunRow.created_at, RunRow.run_id
        )
        async with self._sessionmaker() as db:
            rows = (
                await db.scalars(
                    query.options(load_only(*self._run_columns()))
                    .order_by(RunRow.created_at.desc(), RunRow.run_id.desc())
                    .limit(limit + 1)
                )
            ).all()
            total = await db.scalar(select(func.count()).select_from(RunRow).where(*where))
            page = list(rows[:limit])
            items = await self._work_runs(db, owner, page)
        next_cursor = (
            cursors.encode(RUN_CURSOR, page[-1].created_at.isoformat(), page[-1].run_id)
            if len(rows) > limit and page
            else None
        )
        return WorkRunPage(items=items, next_cursor=next_cursor, total=total or 0)

    async def update_run(
        self, workspace_id: str | None, run_id: str, update: WorkRunUpdate
    ) -> WorkRun:
        """Name, note, archive or the saved view of a run of this workspace. Another workspace's
        run gets what a missing one gets; a run of no workspace (started without a session) is
        nobody's to change."""
        owner = _ws(workspace_id)
        async with self._sessionmaker() as db, db.begin():
            row = await db.scalar(select(RunRow).where(RunRow.run_id == run_id).with_for_update())
            if row is not None and row.workspace_id is None:
                raise NotFoundError(f"Run {run_id} is not in this workspace.")
            if row is None or owner is None or row.workspace_id != owner:
                raise missing("Run", run_id, now=datetime.now(UTC))
            fields = update.model_fields_set
            if "label" in fields:
                row.label = (update.label or "").strip() or None
            if "note" in fields:
                row.note = (update.note or "").strip() or None
            if "archived" in fields and update.archived is not None:
                row.archived_at = (
                    (row.archived_at or datetime.now(UTC)) if update.archived else None
                )
            if "view" in fields:
                row.view = check_view(run_id, update.view or "")
            await db.flush()
            [item] = await self._work_runs(db, owner, [row])
        return item

    async def run_owner(self, run_id: str) -> str | None:
        async with self._sessionmaker() as db:
            owner = await db.scalar(select(RunRow.workspace_id).where(RunRow.run_id == run_id))
        return str(owner) if owner is not None else None

    @staticmethod
    def _run_columns() -> tuple[Any, ...]:
        return (
            RunRow.run_id,
            RunRow.created_at,
            RunRow.expires_at,
            RunRow.status,
            RunRow.origin,
            RunRow.units,
            RunRow.wafers,
            RunRow.alarms,
            RunRow.alarms_not_listed,
            RunRow.upload_id,
            RunRow.again_of,
            RunRow.label,
            RunRow.note,
            RunRow.archived_at,
            RunRow.view,
        )

    async def _work_runs(
        self, db: AsyncSession, owner: uuid.UUID, rows: Sequence[RunRow]
    ) -> list[WorkRun]:
        ids = [r.run_id for r in rows]
        if not ids:
            return []
        kept_until = await self._kept_until(db, owner)
        stages: dict[str, list[tuple[str, str]]] = {i: [] for i in ids}
        for run_id, stage, status in (
            await db.execute(
                select(RunStageRow.run_id, RunStageRow.stage, RunStageRow.state["status"].astext)
                .where(RunStageRow.run_id.in_(ids))
                .order_by(RunStageRow.run_id, RunStageRow.position)
            )
        ).all():
            stages[run_id].append((stage, status))
        investigations: dict[str, list[WorkRunInvestigation]] = {i: [] for i in ids}
        run_part = func.split_part(InvestigationRow.trigger_ref, ":", 1)
        for found in (
            await db.execute(
                select(*SUMMARY_COLUMNS)
                .where(
                    InvestigationRow.trigger_kind == "run_alarm",
                    run_part.in_(ids),
                    InvestigationRow.workspace_id == owner,
                )
                .order_by(InvestigationRow.created_at.desc(), InvestigationRow.investigation_id)
            )
        ).all():
            parsed = parse_run_alarm_ref(found.trigger_ref)
            if parsed is None or parsed[0] not in investigations:
                continue
            investigations[parsed[0]].append(
                WorkRunInvestigation(
                    investigation_id=found.investigation_id,
                    alarm_id=parsed[1],
                    title=found.title,
                    status=cast(InvestigationStatus, found.status),
                    updated_at=found.updated_at,
                    work_order_id=found.work_order_id,
                )
            )
        return [
            self._work_run(r, stages[r.run_id], investigations[r.run_id], kept_until) for r in rows
        ]

    @staticmethod
    def _work_run(
        row: RunRow,
        stages: list[tuple[str, str]],
        investigations: list[WorkRunInvestigation],
        kept_until: datetime,
    ) -> WorkRun:
        origin = RunOrigin.model_validate(row.origin)
        finished = sum(status in FINISHED_STAGES for _, status in stages)
        current = next((stage for stage, status in stages if status == "running"), None)
        failed = [cast(StageId, stage) for stage, status in stages if status == "failed"]
        looked_into = {i.alarm_id for i in investigations}
        red = [turns_red(str(a.get("severity")), str(a.get("kind"))) for a in row.alarms]
        waiting = [str(a.get("alarm_id")) not in looked_into for a in row.alarms]
        alarms, warnings = sum(red), len(red) - sum(red)
        open_alarms = sum(w and r for w, r in zip(waiting, red, strict=True))
        open_warnings = sum(waiting) - open_alarms
        status = cast(RunStatus, row.status)
        return WorkRun(
            run_id=row.run_id,
            created_at=row.created_at,
            expires_at=kept_until,
            status=status,
            source=origin.source,
            datasets=origin.datasets,
            title=origin.title,
            rule=origin.rule,
            filename=origin.filename,
            seed=origin.seed,
            upload_id=row.upload_id,
            again_of=row.again_of,
            units=row.units,
            wafers=row.wafers,
            stages_total=len(STAGES),
            stages_finished=finished,
            current_stage=cast(StageId | None, current),
            failed_stages=failed,
            alarms=alarms,
            warnings=warnings,
            alarms_not_listed=row.alarms_not_listed,
            alarms_open=open_alarms + open_warnings,
            investigations=investigations,
            label=row.label,
            note=row.note,
            archived=row.archived_at is not None,
            view=row.view,
            next=run_next(
                status,
                current=current,
                finished=finished,
                failed=failed,
                alarms=alarms,
                warnings=warnings,
                open_alarms=open_alarms,
                open_warnings=open_warnings,
                investigations=investigations,
            ),
        )

    # Uploads ----------------------------------------------------------------------------------

    async def list_uploads(
        self, workspace_id: str | None, *, cursor: str | None = None, limit: int = 20
    ) -> WorkUploadPage:
        owner = _ws(workspace_id)
        if owner is None:
            return WorkUploadPage(items=[], total=0)
        query = _page_after(
            select(UploadRow).where(UploadRow.workspace_id == owner),
            cursor,
            UPLOAD_CURSOR,
            UploadRow.created_at,
            UploadRow.upload_id,
        )
        async with self._sessionmaker() as db:
            rows = (
                await db.scalars(
                    query.options(
                        load_only(
                            UploadRow.upload_id,
                            UploadRow.created_at,
                            UploadRow.expires_at,
                            UploadRow.kind,
                            UploadRow.filename,
                            UploadRow.runnable,
                            UploadRow.summary,
                        )
                    )
                    .order_by(UploadRow.created_at.desc(), UploadRow.upload_id.desc())
                    .limit(limit + 1)
                )
            ).all()
            total = await db.scalar(
                select(func.count()).select_from(UploadRow).where(UploadRow.workspace_id == owner)
            )
            page = list(rows[:limit])
            kept_until = await self._kept_until(db, owner)
            runs: dict[str, list[str]] = {r.upload_id: [] for r in page}
            if page:
                for run_id, upload_id in (
                    await db.execute(
                        select(RunRow.run_id, RunRow.upload_id)
                        .where(RunRow.upload_id.in_(list(runs)), RunRow.workspace_id == owner)
                        .order_by(RunRow.created_at.desc())
                    )
                ).all():
                    if upload_id is not None:
                        runs[upload_id].append(run_id)
        items = []
        for r in page:
            issues = r.summary.get("issues", [])
            items.append(
                WorkUpload(
                    upload_id=r.upload_id,
                    created_at=r.created_at,
                    expires_at=kept_until,
                    kind=cast(UploadKind, r.kind),
                    filename=r.filename,
                    units=int(r.summary.get("units", 0)),
                    wafers=int(r.summary.get("wafers", 0)),
                    lots=int(r.summary.get("lots", 0)),
                    runnable=r.runnable,
                    errors=sum(i.get("severity") == "error" for i in issues),
                    warnings=sum(i.get("severity") == "warning" for i in issues),
                    runs=runs[r.upload_id],
                )
            )
        next_cursor = (
            cursors.encode(UPLOAD_CURSOR, page[-1].created_at.isoformat(), page[-1].upload_id)
            if len(rows) > limit and page
            else None
        )
        return WorkUploadPage(items=items, next_cursor=next_cursor, total=total or 0)

    # Investigations ---------------------------------------------------------------------------

    async def list_investigations(
        self, workspace_id: str | None, *, cursor: str | None = None, limit: int = 20
    ) -> WorkInvestigationPage:
        owner = _ws(workspace_id)
        if owner is None:
            return WorkInvestigationPage(items=[], total=0)
        now = datetime.now(UTC)
        query = _page_after(
            select(InvestigationRow).where(InvestigationRow.workspace_id == owner),
            cursor,
            INVESTIGATION_CURSOR,
            InvestigationRow.created_at,
            InvestigationRow.investigation_id,
        )
        async with self._sessionmaker() as db:
            rows = (
                await db.scalars(
                    query.options(load_only(*SUMMARY_COLUMNS))
                    .order_by(
                        InvestigationRow.created_at.desc(),
                        InvestigationRow.investigation_id.desc(),
                    )
                    .limit(limit + 1)
                )
            ).all()
            total = await db.scalar(
                select(func.count())
                .select_from(InvestigationRow)
                .where(InvestigationRow.workspace_id == owner)
            )
            page = list(rows[:limit])
            refs = {
                r.investigation_id: parse_run_alarm_ref(r.trigger_ref)
                for r in page
                if r.trigger_kind == "run_alarm"
            }
            run_ids = {p[0] for p in refs.values() if p is not None}
            kept = (
                set(
                    (
                        await db.scalars(
                            select(RunRow.run_id).where(
                                RunRow.run_id.in_(run_ids), self._openable(now)
                            )
                        )
                    ).all()
                )
                if run_ids
                else set()
            )
        items = []
        for r in page:
            parsed = refs.get(r.investigation_id)
            items.append(
                WorkInvestigation(
                    investigation=to_summary(r),
                    run_id=parsed[0] if parsed else None,
                    alarm_id=parsed[1] if parsed else None,
                    run_kept=bool(parsed and parsed[0] in kept),
                    next=investigation_next(r.status, r.work_order_id),
                )
            )
        next_cursor = (
            cursors.encode(
                INVESTIGATION_CURSOR, page[-1].created_at.isoformat(), page[-1].investigation_id
            )
            if len(rows) > limit and page
            else None
        )
        return WorkInvestigationPage(items=items, next_cursor=next_cursor, total=total or 0)
