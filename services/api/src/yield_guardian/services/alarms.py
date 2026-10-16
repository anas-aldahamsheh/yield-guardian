"""Alarm states. SECOM unit alarms are computed by rule (science/secom/alarms.py); their status
lives here, keyed by alarm ID.

An alarm without a stored state is open. Creating an investigation from an alarm makes it
investigating; deciding that investigation closes it; a failed investigation reopens it. Every
change sends `pg_notify('yg_alarm_states', alarm_id)` so each API process can push the update.

The stored state is the alarm's state across every workspace (it serialises investigations of one
alarm). What a workspace is shown is :meth:`DbAlarmStateStore.of_workspace`: the same rules over
its own investigations only, so one visitor never sees another's activity on an alarm.
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, cast

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on, insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from yield_guardian.contracts.line import AlarmStatus
from yield_guardian.db.notify import ALARMS_CHANNEL
from yield_guardian.db.tables import AlarmStateRow, InvestigationRow
from yield_guardian.services.access import Viewer, owned

DECIDED = frozenset({"approved", "rejected"})


@dataclass(frozen=True, slots=True)
class AlarmState:
    alarm_id: str
    status: AlarmStatus
    investigation_id: str | None
    updated_at: datetime | None


class AlarmStateStore(Protocol):
    async def get(self, alarm_id: str) -> AlarmState:
        """The alarm's state; open with no investigation when nothing is stored."""
        ...

    async def states(self, alarm_ids: Collection[str] | None = None) -> dict[str, AlarmState]:
        """Stored states of these alarms (every stored state when None); missing ones are open."""
        ...


def _state(row: AlarmStateRow) -> AlarmState:
    return AlarmState(
        alarm_id=row.alarm_id,
        status=cast(AlarmStatus, row.status),
        investigation_id=row.investigation_id,
        updated_at=row.updated_at,
    )


async def lock(db: AsyncSession, alarm_id: str) -> AlarmStateRow:
    """The alarm's row, created as open if missing, locked until the transaction ends."""
    await db.execute(
        insert(AlarmStateRow)
        .values(alarm_id=alarm_id, status="open", updated_at=datetime.now(UTC))
        .on_conflict_do_nothing()
    )
    row = await db.scalar(
        select(AlarmStateRow)
        .where(AlarmStateRow.alarm_id == alarm_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert row is not None
    return row


async def set_state(
    db: AsyncSession, alarm_id: str, status: AlarmStatus, investigation_id: str | None
) -> None:
    """Change the alarm's state in the caller's transaction and notify every process."""
    row = await lock(db, alarm_id)
    row.status = status
    row.investigation_id = investigation_id
    row.updated_at = datetime.now(UTC)
    await db.execute(select(func.pg_notify(ALARMS_CHANNEL, alarm_id)))


class DbAlarmStateStore:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get(self, alarm_id: str) -> AlarmState:
        async with self._sessionmaker() as db:
            row = await db.get(AlarmStateRow, alarm_id)
        if row is None:
            return AlarmState(
                alarm_id=alarm_id, status="open", investigation_id=None, updated_at=None
            )
        return _state(row)

    async def states(self, alarm_ids: Collection[str] | None = None) -> dict[str, AlarmState]:
        query = select(AlarmStateRow)
        if alarm_ids is not None:
            query = query.where(AlarmStateRow.alarm_id.in_(list(alarm_ids)))
        async with self._sessionmaker() as db:
            rows = (await db.scalars(query)).all()
        return {row.alarm_id: _state(row) for row in rows}

    async def of_workspace(self, viewer: Viewer) -> dict[str, AlarmState]:
        """The alarms `viewer`'s workspace took over, from its newest investigation of each:
        investigating while it runs or waits for a decision, closed once decided; one whose
        newest investigation failed is open again, so it is left out like every open one."""
        newest = (
            select(
                InvestigationRow.trigger_ref,
                InvestigationRow.investigation_id,
                InvestigationRow.status,
                InvestigationRow.updated_at,
            )
            .where(
                InvestigationRow.trigger_kind == "alarm",
                owned(InvestigationRow.workspace_id, viewer),
            )
            .ext(distinct_on(InvestigationRow.trigger_ref))
            .order_by(
                InvestigationRow.trigger_ref,
                InvestigationRow.created_at.desc(),
                InvestigationRow.investigation_id.desc(),
            )
        )
        async with self._sessionmaker() as db:
            rows = (await db.execute(newest)).all()
        return {
            ref: AlarmState(
                alarm_id=ref,
                status="closed" if status in DECIDED else "investigating",
                investigation_id=investigation_id,
                updated_at=updated_at,
            )
            for ref, investigation_id, status, updated_at in rows
            if status != "failed"
        }
