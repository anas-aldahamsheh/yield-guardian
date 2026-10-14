"""Recorded investigations: export to JSON and an idempotent import (PLAN A3).

A recorded run is a normal investigation made once on the server by
``scripts/record_investigations.py`` (``recorded = true``), through the job queue and the
investigator like any other run. It is exported with its event log and, when it waits for the
engineer's decision, the investigator's paused state, so that on any host it can be imported,
shown as recorded, replayed event by event, and still be approved or rejected (deciding resumes
the graph from that state; no model is called).

Only runs waiting for a decision are exported: a decided run carries a work order and audit
entries that belong to the host where it was decided. Import never overwrites: an investigation
whose ID exists is skipped, so seeding at every start is safe.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import structlog
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from yield_guardian.agent.graph import paused_values, restore_paused
from yield_guardian.contracts.investigation import Investigation, InvestigationEventPayload
from yield_guardian.db.tables import InvestigationEventRow, InvestigationRow
from yield_guardian.services import alarms
from yield_guardian.services.investigations import to_investigation

log = structlog.get_logger(__name__)

FORMAT: Literal["yield-guardian-recorded-runs-v1"] = "yield-guardian-recorded-runs-v1"
EXPORTED_STATUS = "awaiting_decision"
_EVENTS: TypeAdapter[InvestigationEventPayload] = TypeAdapter(InvestigationEventPayload)

Sessions = async_sessionmaker[AsyncSession]


class RecordedRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    investigation: Investigation
    created_by: str | None
    events: list[dict[str, Any]] = Field(min_length=1)
    """The stored event payloads, in ``seq`` order."""
    paused_state: dict[str, Any] | None
    """The investigator's state at the decision interrupt (JSON); None if it was not saved."""


class RecordedRuns(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["yield-guardian-recorded-runs-v1"] = FORMAT
    exported_at: datetime
    runs: list[RecordedRun]


class ImportReport(BaseModel):
    imported: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    """Already present on this host."""
    without_state: list[str] = Field(default_factory=list)
    """Imported, but the paused state could not be restored: deciding records the decision and
    the step shows an error instead of the graph's completion."""


async def export_recorded(
    sessions: Sessions,
    checkpointer: BaseCheckpointSaver[Any] | None,
    *,
    now: datetime | None = None,
) -> tuple[RecordedRuns, list[str]]:
    """Every recorded run waiting for a decision (none taken yet), oldest first; also the IDs
    of the recorded runs left out."""
    async with sessions() as db:
        rows = list(
            (
                await db.scalars(
                    select(InvestigationRow)
                    .where(InvestigationRow.recorded.is_(True))
                    .order_by(InvestigationRow.created_at, InvestigationRow.investigation_id)
                )
            ).all()
        )
        runs: list[RecordedRun] = []
        left_out: list[str] = []
        for row in rows:
            if row.status != EXPORTED_STATUS or row.decision is not None:
                left_out.append(row.investigation_id)
                continue
            events = (
                await db.scalars(
                    select(InvestigationEventRow.payload)
                    .where(InvestigationEventRow.investigation_id == row.investigation_id)
                    .order_by(InvestigationEventRow.seq)
                )
            ).all()
            state = (
                await paused_values(checkpointer, row.investigation_id)
                if checkpointer is not None
                else None
            )
            runs.append(
                RecordedRun(
                    investigation=to_investigation(row),
                    created_by=row.created_by,
                    events=list(events),
                    paused_state=state,
                )
            )
    return RecordedRuns(exported_at=now or datetime.now(UTC), runs=runs), left_out


def check_run(run: RecordedRun) -> None:
    """The run is a recorded run waiting for a decision, and its events are its own, in order."""
    inv = run.investigation
    if not inv.recorded:
        raise ValueError(f"{inv.investigation_id} is not a recorded run")
    if inv.status != EXPORTED_STATUS or inv.decision is not None:
        raise ValueError(f"{inv.investigation_id} is not waiting for a decision")
    seqs = [_EVENTS.validate_python(e).seq for e in run.events]
    if seqs != list(range(1, len(seqs) + 1)):
        raise ValueError(f"{inv.investigation_id}: event seq must run 1, 2, ... without gaps")


async def import_recorded(
    sessions: Sessions,
    runs: RecordedRuns,
    checkpointer: BaseCheckpointSaver[Any] | None,
) -> ImportReport:
    """Insert each run that is not on this host yet; never changes an existing investigation."""
    for run in runs.runs:
        check_run(run)
    report = ImportReport()
    for run in runs.runs:
        inv = run.investigation
        async with sessions() as db, db.begin():
            if await db.get(InvestigationRow, inv.investigation_id) is not None:
                report.skipped.append(inv.investigation_id)
                continue
            db.add(_row(run))
            await db.flush()
            for payload in run.events:
                event = _EVENTS.validate_python(payload)
                db.add(
                    InvestigationEventRow(
                        investigation_id=inv.investigation_id,
                        seq=event.seq,
                        type=event.type,
                        at=event.at,
                        payload=event.model_dump(mode="json"),
                    )
                )
            if inv.trigger.kind == "alarm":
                alarm = await alarms.lock(db, inv.trigger.ref)
                if alarm.investigation_id is None:
                    await alarms.set_state(db, inv.trigger.ref, "investigating", inv.investigation_id)  # fmt: skip
        report.imported.append(inv.investigation_id)
        restored = False
        if checkpointer is not None and run.paused_state is not None:
            try:
                await restore_paused(checkpointer, inv.investigation_id, run.paused_state)
                restored = True
            except Exception:
                log.warning("recorded_state_not_restored", investigation_id=inv.investigation_id, exc_info=True)  # fmt: skip
        if not restored:
            report.without_state.append(inv.investigation_id)
    return report


def _row(run: RecordedRun) -> InvestigationRow:
    inv = run.investigation

    def dump(value: BaseModel | None) -> dict[str, Any] | None:
        return value.model_dump(mode="json") if value is not None else None

    return InvestigationRow(
        investigation_id=inv.investigation_id,
        title=inv.title,
        status=inv.status,
        trigger_kind=inv.trigger.kind,
        trigger_ref=inv.trigger.ref,
        trigger_question=inv.trigger.question,
        recorded=True,
        created_by=run.created_by,
        created_at=inv.created_at,
        updated_at=inv.updated_at,
        last_seq=len(run.events),
        steps=[s.model_dump(mode="json") for s in inv.steps],
        evidence=[e.model_dump(mode="json") for e in inv.evidence],
        models=[m.model_dump(mode="json") for m in inv.models],
        usage=dump(inv.usage),
        report=dump(inv.report),
        verification=dump(inv.verification),
        decision=None,
        error=dump(inv.error),
        work_order_id=None,
    )


def write_runs(path: Path, runs: RecordedRuns) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(runs.model_dump_json(indent=2) + "\n", encoding="utf-8")


def read_runs(path: Path) -> RecordedRuns:
    return RecordedRuns.model_validate_json(path.read_text(encoding="utf-8"))
