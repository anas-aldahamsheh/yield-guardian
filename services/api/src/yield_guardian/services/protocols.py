"""Interfaces of the API's own services (stores, sessions, replay). Implementations live next to
this module; the science and AI interfaces are in yield_guardian.contracts.services."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from yield_guardian.contracts.investigation import (
    DecisionCreate,
    Evidence,
    Investigation,
    InvestigationEventPayload,
    InvestigationPage,
    InvestigationStatus,
    InvestigationTrigger,
)
from yield_guardian.contracts.line import (
    AlarmKind,
    AlarmPage,
    AlarmStatus,
    LineAlarmMessage,
    LineCycle,
    LineFinalTestMessage,
    LineHeartbeat,
    LineHello,
    LineState,
    LineUnitMessage,
    PlantClock,
)
from yield_guardian.contracts.methods import MeasuredResults, MethodsOverview, ModelCard
from yield_guardian.contracts.session import (
    GuestSessionCreate,
    LoginRequest,
    SessionInfo,
    SessionRole,
)
from yield_guardian.contracts.workorders import (
    AuditAction,
    AuditPage,
    WorkOrder,
    WorkOrderPage,
    WorkOrderUpdate,
)

LineMessage = (
    LineHello
    | LineUnitMessage
    | LineAlarmMessage
    | LineFinalTestMessage
    | LineHeartbeat
    | LineCycle
)


@dataclass(frozen=True, slots=True)
class ActiveSession:
    """A signed-in session as the server sees it. Only `info()` leaves the server."""

    session_id: str
    role: SessionRole
    display_name: str | None
    csrf_token: str | None
    expires_at: datetime | None

    def info(self) -> SessionInfo:
        return SessionInfo(
            role=self.role,
            display_name=self.display_name,
            expires_at=self.expires_at,
            csrf_token=self.csrf_token,
        )


VISITOR = ActiveSession(
    session_id="", role="visitor", display_name=None, csrf_token=None, expires_at=None
)


class LineService(Protocol):
    def clock(self) -> PlantClock: ...

    async def state(self, *, window: int = 120) -> LineState: ...

    def stream(self) -> AsyncIterator[LineMessage]:
        """Hello first, then units, alarms, final-test results, heartbeats and cycles."""
        ...

    async def list_alarms(
        self,
        *,
        status: AlarmStatus | None = None,
        kind: AlarmKind | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> AlarmPage: ...


class InvestigationStore(Protocol):
    async def create(
        self, trigger: InvestigationTrigger, *, session: ActiveSession
    ) -> Investigation: ...

    async def get(self, investigation_id: str) -> Investigation: ...

    async def list(
        self,
        *,
        status: InvestigationStatus | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> InvestigationPage: ...

    async def get_evidence(self, investigation_id: str, evidence_id: str) -> Evidence: ...

    def events(
        self, investigation_id: str, *, after_seq: int | None = None
    ) -> AsyncIterator[InvestigationEventPayload]:
        """Stored events after `after_seq`, then live ones until the end event."""
        ...

    async def decide(
        self, investigation_id: str, decision: DecisionCreate, *, session: ActiveSession
    ) -> Investigation: ...


class WorkOrderStore(Protocol):
    async def list(self, *, cursor: str | None = None, limit: int = 50) -> WorkOrderPage: ...

    async def get(self, work_order_id: str) -> WorkOrder: ...

    async def update(
        self, work_order_id: str, update: WorkOrderUpdate, *, session: ActiveSession
    ) -> WorkOrder: ...


class AuditLog(Protocol):
    async def list(
        self, *, action: AuditAction | None = None, cursor: str | None = None, limit: int = 50
    ) -> AuditPage: ...


class SessionManager(Protocol):
    async def resolve(self, token: str | None) -> ActiveSession:
        """The session for a cookie token; VISITOR when missing, expired or unknown."""
        ...

    async def guest(self, body: GuestSessionCreate, *, client: str) -> tuple[ActiveSession, str]:
        """Start a "Try as engineer" session; returns it and the cookie token."""
        ...

    async def login(self, body: LoginRequest, *, client: str) -> tuple[ActiveSession, str]: ...

    async def logout(self, session: ActiveSession) -> None: ...


class MethodsService(Protocol):
    async def overview(self) -> MethodsOverview: ...

    async def model_card(self, name: str) -> ModelCard: ...

    async def results(self) -> MeasuredResults: ...
