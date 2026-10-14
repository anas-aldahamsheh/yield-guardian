"""The audit log: one entry per state change, written in the same transaction as the change."""

from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import JsonValue
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from yield_guardian.contracts.workorders import ActorRole, AuditAction, AuditEntry, AuditPage
from yield_guardian.db.tables import AuditEntryRow
from yield_guardian.services import cursors
from yield_guardian.services.protocols import ActiveSession

CURSOR_KIND = "audit"

ROLE_LABELS: dict[ActorRole, str] = {
    "system": "System",
    "visitor": "Visitor",
    "engineer": "Guest engineer",
    "admin": "Administrator",
}


@dataclass(frozen=True, slots=True)
class Actor:
    role: ActorRole
    name: str | None

    @classmethod
    def of(cls, session: ActiveSession) -> "Actor":
        return cls(role=session.role, name=session.display_name)

    @property
    def label(self) -> str:
        """The name shown on decisions and work orders."""
        return self.name or ROLE_LABELS[self.role]


SYSTEM = Actor(role="system", name=None)


def record(
    db: AsyncSession,
    actor: Actor,
    action: AuditAction,
    target_kind: str,
    target_id: str,
    details: dict[str, JsonValue] | None = None,
) -> None:
    """Add an audit entry to the caller's transaction."""
    db.add(
        AuditEntryRow(
            at=datetime.now(UTC),
            actor_role=actor.role,
            actor_name=actor.name,
            action=action,
            target_kind=target_kind,
            target_id=target_id,
            details=details or {},
        )
    )


def to_entry(row: AuditEntryRow) -> AuditEntry:
    return AuditEntry.model_validate(
        {
            "audit_id": row.audit_id,
            "at": row.at,
            "actor_role": row.actor_role,
            "actor_name": row.actor_name,
            "action": row.action,
            "target_kind": row.target_kind,
            "target_id": row.target_id,
            "details": row.details,
        }
    )


class DbAuditLog:
    """Audit entries, newest first; cursors carry the last audit ID."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def list(
        self, *, action: AuditAction | None = None, cursor: str | None = None, limit: int = 50
    ) -> AuditPage:
        query = select(AuditEntryRow)
        count = select(func.count()).select_from(AuditEntryRow)
        if action is not None:
            query = query.where(AuditEntryRow.action == action)
            count = count.where(AuditEntryRow.action == action)
        if cursor is not None:
            (last_id,) = cursors.decode(CURSOR_KIND, cursor, int)
            query = query.where(AuditEntryRow.audit_id < last_id)
        query = query.order_by(AuditEntryRow.audit_id.desc()).limit(limit + 1)
        async with self._sessionmaker() as db:
            rows = list((await db.scalars(query)).all())
            total = (await db.scalar(count)) or 0
        more = len(rows) > limit
        rows = rows[:limit]
        return AuditPage(
            items=[to_entry(row) for row in rows],
            next_cursor=cursors.encode(CURSOR_KIND, rows[-1].audit_id) if more else None,
            total=total,
        )
