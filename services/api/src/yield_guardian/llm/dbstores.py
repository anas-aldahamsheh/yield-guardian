"""PostgreSQL implementations of the language-model stores (tables of migration 0002).

They implement the same protocols as the in-memory stores and are chosen at startup when
DATABASE_URL is set (``agent.wiring``), so usage records, cached answers, role choices, chat
routes and evaluations survive a restart.

What happens when the database fails mid-request:

* the call log keeps the record in memory and writes it with the next record that succeeds
  (the call was made and its points spent, so its record must not be lost or fail the answer);
* the response cache reads as a miss and skips the write (a cache never decides an answer);
* the route log keeps the entry in memory the same way as the call log;
* role assignments and evaluations raise: an administrator's change must not look saved when
  it is not.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime

import structlog
from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from yield_guardian.contracts.chat import RouteKind
from yield_guardian.contracts.models import EvaluationResult
from yield_guardian.db.tables import (
    ChatRouteRow,
    LlmCallRow,
    LlmEvaluationRow,
    LlmResponseCacheRow,
    LlmRoleAssignmentRow,
)
from yield_guardian.llm.calllog import LlmCallRecord
from yield_guardian.llm.registry import RoleAssignment
from yield_guardian.llm.results import ChatResult

log = structlog.get_logger(__name__)

Sessions = async_sessionmaker[AsyncSession]
_DB_ERRORS = (SQLAlchemyError, OSError)


def _now() -> datetime:
    return datetime.now(UTC)


class DbCallLog:
    """Implements :class:`~yield_guardian.llm.calllog.LlmCallLog`."""

    def __init__(self, sessions: Sessions) -> None:
        self._sessions = sessions
        self.pending: list[LlmCallRecord] = []
        """Records not yet written because the database failed; written with the next one."""

    async def record(self, record: LlmCallRecord) -> None:
        batch, self.pending = [*self.pending, record], []  # taken before any await
        try:
            async with self._sessions.begin() as db:
                db.add_all(
                    LlmCallRow(
                        started_at=r.started_at,
                        role=r.role,
                        model=r.model,
                        status=str(r.status),
                        correlation_id=r.correlation_id,
                        record=r.model_dump(mode="json"),
                    )
                    for r in batch
                )
        except _DB_ERRORS:
            self.pending = [*batch, *self.pending]
            log.warning("llm_call_not_saved", pending=len(self.pending), exc_info=True)

    async def since(self, start: datetime) -> Sequence[LlmCallRecord]:
        async with self._sessions() as db:
            rows = await db.scalars(
                select(LlmCallRow.record)
                .where(LlmCallRow.started_at >= start)
                .order_by(LlmCallRow.started_at, LlmCallRow.call_id)
            )
            saved = [LlmCallRecord.model_validate(r) for r in rows]
        waiting = [r for r in self.pending if r.started_at >= start]
        return sorted([*saved, *waiting], key=lambda r: r.started_at)


class DbResponseCache:
    """Implements :class:`~yield_guardian.llm.cache.ResponseCache`; entries do not expire
    (the key covers the model and the whole request, so an entry stays correct)."""

    def __init__(self, sessions: Sessions, *, wall_clock: Callable[[], datetime] = _now) -> None:
        self._sessions = sessions
        self._wall_clock = wall_clock

    async def get(self, key: str) -> ChatResult | None:
        try:
            async with self._sessions.begin() as db:
                row = await db.get(LlmResponseCacheRow, key, with_for_update=True)
                if row is None:
                    return None
                row.hits += 1
                row.last_used_at = self._wall_clock()
                return ChatResult.model_validate(row.result)
        except _DB_ERRORS:
            log.warning("llm_cache_read_failed", exc_info=True)
            return None

    async def put(self, key: str, result: ChatResult) -> None:
        now = self._wall_clock()
        statement = insert(LlmResponseCacheRow).values(
            cache_key=key, result=result.model_dump(mode="json"), created_at=now, last_used_at=now
        )
        statement = statement.on_conflict_do_update(
            index_elements=[LlmResponseCacheRow.cache_key],
            set_={"result": statement.excluded.result, "last_used_at": now},
        )
        try:
            async with self._sessions.begin() as db:
                await db.execute(statement)
        except _DB_ERRORS:
            log.warning("llm_cache_write_failed", exc_info=True)


class DbRoleAssignmentStore:
    """Implements :class:`~yield_guardian.llm.registry.RoleAssignmentStore`."""

    def __init__(self, sessions: Sessions) -> None:
        self._sessions = sessions

    async def load(self) -> Sequence[RoleAssignment]:
        async with self._sessions() as db:
            rows = (await db.scalars(select(LlmRoleAssignmentRow))).all()
        return [
            RoleAssignment.model_validate(
                {
                    "role": row.role,
                    "chain": row.chain,
                    "updated_at": row.updated_at,
                    "updated_by": row.updated_by,
                }
            )
            for row in rows
        ]

    async def save(self, assignment: RoleAssignment) -> None:
        values = {
            "chain": [c.model_dump(mode="json") for c in assignment.chain],
            "updated_at": assignment.updated_at,
            "updated_by": assignment.updated_by,
        }
        statement = insert(LlmRoleAssignmentRow).values(role=str(assignment.role), **values)
        statement = statement.on_conflict_do_update(
            index_elements=[LlmRoleAssignmentRow.role], set_=values
        )
        async with self._sessions.begin() as db:
            await db.execute(statement)


class DbRouteLog:
    """Implements :class:`~yield_guardian.llm.admin.RouteLog`."""

    def __init__(self, sessions: Sessions) -> None:
        self._sessions = sessions
        self.pending: list[tuple[datetime, RouteKind, str]] = []

    async def record(self, route: RouteKind, intent: str, at: datetime) -> None:
        batch, self.pending = [*self.pending, (at, route, intent)], []
        try:
            async with self._sessions.begin() as db:
                db.add_all(ChatRouteRow(at=a, kind=k, intent=i) for a, k, i in batch)
        except _DB_ERRORS:
            self.pending = [*batch, *self.pending]
            log.warning("chat_route_not_saved", pending=len(self.pending), exc_info=True)

    async def counts(self, since: datetime) -> tuple[int, int]:
        deterministic = func.count(case((ChatRouteRow.kind == "deterministic", 1)))
        model = func.count(case((ChatRouteRow.kind == "model", 1)))
        async with self._sessions() as db:
            row = (
                await db.execute(select(deterministic, model).where(ChatRouteRow.at >= since))
            ).one()
        waiting = [kind for at, kind, _ in self.pending if at >= since]
        return (
            int(row[0]) + waiting.count("deterministic"),
            int(row[1]) + waiting.count("model"),
        )


class DbEvaluationStore:
    """Implements :class:`~yield_guardian.llm.admin.EvaluationStore`."""

    def __init__(self, sessions: Sessions) -> None:
        self._sessions = sessions

    async def save(self, result: EvaluationResult) -> None:
        async with self._sessions.begin() as db:
            db.add(
                LlmEvaluationRow(
                    role=result.role,
                    model_id=result.model_id,
                    task_set=result.task_set,
                    run_at=result.run_at,
                    result=result.model_dump(mode="json"),
                )
            )

    async def all(self) -> Sequence[EvaluationResult]:
        async with self._sessions() as db:
            rows = await db.scalars(
                select(LlmEvaluationRow.result).order_by(
                    LlmEvaluationRow.run_at, LlmEvaluationRow.evaluation_id
                )
            )
            return [EvaluationResult.model_validate(r) for r in rows]
