"""Work orders opened by approved investigations. Every change is written to the audit log."""

import uuid
from datetime import UTC, datetime

from pydantic import JsonValue
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from yield_guardian.contracts.investigation import Action, Report
from yield_guardian.contracts.services import InvalidArgumentError, NotFoundError
from yield_guardian.contracts.workorders import (
    ConfirmedCause,
    WorkOrder,
    WorkOrderPage,
    WorkOrderUpdate,
)
from yield_guardian.db.tables import WORK_ORDER_NUMBER, InvestigationRow, WorkOrderRow
from yield_guardian.services import audit, cursors
from yield_guardian.services.access import Viewer, examples, is_example, owned
from yield_guardian.services.errors import ReadOnlyError
from yield_guardian.services.protocols import ActiveSession

CURSOR_KIND = "wo"


def example_investigations() -> Select[str]:
    """SQL: the IDs of the product's examples (``access.is_example``)."""
    return select(InvestigationRow.investigation_id).where(examples())


def to_work_order(row: WorkOrderRow, *, example: bool = False) -> WorkOrder:
    return WorkOrder.model_validate(
        {
            "example": example,
            "work_order_id": row.work_order_id,
            "investigation_id": row.investigation_id,
            "title": row.title,
            "status": row.status,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "created_by": row.created_by,
            "actions": row.actions,
            "note": row.note,
            "outcome": row.outcome,
            "outcome_confirmed": row.outcome_confirmed,
            "confirmed_cause": row.confirmed_cause,
        }
    )


async def open_work_order(
    db: AsyncSession,
    *,
    investigation_id: str,
    title: str,
    actions: list[Action],
    note: str | None,
    actor: audit.Actor,
) -> str:
    """Open the investigation's work order in the caller's transaction; idempotent."""
    existing = await db.scalar(
        select(WorkOrderRow.work_order_id).where(WorkOrderRow.investigation_id == investigation_id)
    )
    if existing is not None:
        return existing
    number = await db.scalar(select(WORK_ORDER_NUMBER.next_value()))
    work_order_id = f"WO-{number:06d}"
    now = datetime.now(UTC)
    db.add(
        WorkOrderRow(
            work_order_id=work_order_id,
            investigation_id=investigation_id,
            title=title,
            status="open",
            created_at=now,
            updated_at=now,
            created_by=actor.label,
            actions=[a.model_dump(mode="json") for a in actions],
            note=note,
            outcome=None,
            outcome_confirmed=False,
            confirmed_cause=None,
        )
    )
    audit.record(
        db,
        actor,
        "work_order.created",
        "work_order",
        work_order_id,
        {"investigation_id": investigation_id, "actions": len(actions)},
    )
    return work_order_id


async def _check_hypothesis(db: AsyncSession, investigation_id: str, cause: ConfirmedCause) -> None:
    if cause.hypothesis_index is None:
        return
    stored = await db.scalar(
        select(InvestigationRow.report).where(InvestigationRow.investigation_id == investigation_id)
    )
    count = len(Report.model_validate(stored).hypotheses) if stored is not None else 0
    if cause.hypothesis_index >= count:
        raise InvalidArgumentError(
            f"The report of {investigation_id} has {count} hypotheses; "
            f"hypothesis_index must be below {count}."
            if count
            else f"The report of {investigation_id} has no hypotheses; send hypothesis_index null."
        )


async def _owner(db: AsyncSession, row: WorkOrderRow) -> tuple[uuid.UUID | None, bool]:
    """The workspace of the work order's investigation, and whether it is the product's example."""
    found = (
        await db.execute(
            select(InvestigationRow.workspace_id, InvestigationRow.recorded).where(
                InvestigationRow.investigation_id == row.investigation_id
            )
        )
    ).one()
    return found.workspace_id, is_example(found.recorded, found.workspace_id)


class DbWorkOrderStore:
    """Work orders, newest first; cursors carry the last work order ID."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def list(
        self, *, cursor: str | None = None, limit: int = 50, viewer: Viewer | None = None
    ) -> WorkOrderPage:
        """Newest first; with a `viewer`, the work orders of its own investigations and those
        of the product's examples (marked `example`), which every viewer sees."""
        example = WorkOrderRow.investigation_id.in_(example_investigations())
        query = select(WorkOrderRow, example.label("example"))
        count = select(func.count()).select_from(WorkOrderRow)
        if viewer is not None:
            mine = WorkOrderRow.investigation_id.in_(
                select(InvestigationRow.investigation_id).where(
                    owned(InvestigationRow.workspace_id, viewer)
                )
            )
            listed = or_(mine, example)
            query, count = query.where(listed), count.where(listed)
        if cursor is not None:
            (last_id,) = cursors.decode(CURSOR_KIND, cursor, str)
            query = query.where(WorkOrderRow.work_order_id < last_id)
        query = query.order_by(WorkOrderRow.work_order_id.desc()).limit(limit + 1)
        async with self._sessionmaker() as db:
            rows = list((await db.execute(query)).all())
            total = (await db.scalar(count)) or 0
        more = len(rows) > limit
        rows = rows[:limit]
        return WorkOrderPage(
            items=[to_work_order(order, example=flag) for order, flag in rows],
            next_cursor=cursors.encode(CURSOR_KIND, rows[-1][0].work_order_id) if more else None,
            total=total,
        )

    async def get(self, work_order_id: str, viewer: Viewer | None = None) -> WorkOrder:
        """The work order; NotFoundError when it does not exist or its investigation belongs to
        a workspace other than `viewer`'s (None: any)."""
        example = False
        async with self._sessionmaker() as db:
            row = await db.get(WorkOrderRow, work_order_id)
            if row is not None:
                owner, example = await _owner(db, row)
                if viewer is not None and not viewer.sees(owner):
                    row = None
        if row is None:
            raise NotFoundError(f"Work order {work_order_id} does not exist.")
        return to_work_order(row, example=example)

    async def update(
        self, work_order_id: str, update: WorkOrderUpdate, *, session: ActiveSession
    ) -> WorkOrder:
        """Apply the fields sent (an explicit null clears note or outcome).

        Changing the outcome withdraws its confirmation unless the same update confirms it again.
        A confirmed cause is recorded only on a closed (done) work order, its hypothesis index
        must name a hypothesis of the investigation's report, and reopening withdraws it.
        ReadOnlyError for the work order of the product's example, which nobody changes.
        """
        sent = update.model_fields_set
        async with self._sessionmaker() as db, db.begin():
            row = await db.scalar(
                select(WorkOrderRow)
                .where(WorkOrderRow.work_order_id == work_order_id)
                .with_for_update()
            )
            owner, example = await _owner(db, row) if row is not None else (None, False)
            if row is None or not session.viewer.sees(owner):
                raise NotFoundError(f"Work order {work_order_id} does not exist.")
            if example:
                raise ReadOnlyError(
                    f"Work order {work_order_id} belongs to the recorded example every visitor "
                    "sees, so nobody changes it."
                )
            target: dict[str, JsonValue] = {
                "status": row.status,
                "note": row.note,
                "outcome": row.outcome,
                "outcome_confirmed": row.outcome_confirmed,
                "confirmed_cause": row.confirmed_cause,
            }
            if update.status is not None:
                target["status"] = update.status
            if "note" in sent:
                target["note"] = update.note
            if "outcome" in sent:
                target["outcome"] = update.outcome
                if update.outcome != row.outcome:
                    target["outcome_confirmed"] = False
            if update.outcome_confirmed is not None:
                target["outcome_confirmed"] = update.outcome_confirmed
            if target["outcome_confirmed"] and not target["outcome"]:
                raise InvalidArgumentError("Record the outcome before confirming it.")
            if "confirmed_cause" in sent and update.confirmed_cause is not None:
                if target["status"] != "done":
                    raise InvalidArgumentError(
                        "A confirmed cause is recorded when the work order is closed: send it "
                        'with status "done".'
                    )
                await _check_hypothesis(db, row.investigation_id, update.confirmed_cause)
                target["confirmed_cause"] = update.confirmed_cause.model_dump(mode="json")
            elif "confirmed_cause" in sent:
                target["confirmed_cause"] = None
            if target["status"] != "done":
                target["confirmed_cause"] = None
            changes: dict[str, JsonValue] = {
                field: {"from": getattr(row, field), "to": value}
                for field, value in target.items()
                if getattr(row, field) != value
            }
            if changes:
                for field, value in target.items():
                    setattr(row, field, value)
                row.updated_at = datetime.now(UTC)
                audit.record(
                    db,
                    audit.Actor.of(session),
                    "work_order.updated",
                    "work_order",
                    work_order_id,
                    {"changes": changes},
                )
        return to_work_order(row)
