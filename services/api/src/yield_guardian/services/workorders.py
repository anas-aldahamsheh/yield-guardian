"""Work orders opened by approved investigations. Every change is written to the audit log."""

from datetime import UTC, datetime

from pydantic import JsonValue
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from yield_guardian.contracts.investigation import Action
from yield_guardian.contracts.services import InvalidArgumentError, NotFoundError
from yield_guardian.contracts.workorders import WorkOrder, WorkOrderPage, WorkOrderUpdate
from yield_guardian.db.tables import WORK_ORDER_NUMBER, WorkOrderRow
from yield_guardian.services import audit, cursors
from yield_guardian.services.protocols import ActiveSession

CURSOR_KIND = "wo"


def to_work_order(row: WorkOrderRow) -> WorkOrder:
    return WorkOrder.model_validate(
        {
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


class DbWorkOrderStore:
    """Work orders, newest first; cursors carry the last work order ID."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def list(self, *, cursor: str | None = None, limit: int = 50) -> WorkOrderPage:
        query = select(WorkOrderRow)
        if cursor is not None:
            (last_id,) = cursors.decode(CURSOR_KIND, cursor, str)
            query = query.where(WorkOrderRow.work_order_id < last_id)
        query = query.order_by(WorkOrderRow.work_order_id.desc()).limit(limit + 1)
        async with self._sessionmaker() as db:
            rows = list((await db.scalars(query)).all())
            total = (await db.scalar(select(func.count()).select_from(WorkOrderRow))) or 0
        more = len(rows) > limit
        rows = rows[:limit]
        return WorkOrderPage(
            items=[to_work_order(row) for row in rows],
            next_cursor=cursors.encode(CURSOR_KIND, rows[-1].work_order_id) if more else None,
            total=total,
        )

    async def get(self, work_order_id: str) -> WorkOrder:
        async with self._sessionmaker() as db:
            row = await db.get(WorkOrderRow, work_order_id)
        if row is None:
            raise NotFoundError(f"Work order {work_order_id} does not exist.")
        return to_work_order(row)

    async def update(
        self, work_order_id: str, update: WorkOrderUpdate, *, session: ActiveSession
    ) -> WorkOrder:
        """Apply the fields sent (an explicit null clears note or outcome).

        Changing the outcome withdraws its confirmation unless the same update confirms it again.
        """
        sent = update.model_fields_set
        async with self._sessionmaker() as db, db.begin():
            row = await db.scalar(
                select(WorkOrderRow)
                .where(WorkOrderRow.work_order_id == work_order_id)
                .with_for_update()
            )
            if row is None:
                raise NotFoundError(f"Work order {work_order_id} does not exist.")
            target: dict[str, JsonValue] = {
                "status": row.status,
                "note": row.note,
                "outcome": row.outcome,
                "outcome_confirmed": row.outcome_confirmed,
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
