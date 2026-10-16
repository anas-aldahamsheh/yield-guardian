"""Interfaces of the API's own services (stores, sessions, alarms). Implementations live next to
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
from yield_guardian.contracts.line import AlarmKind, AlarmPage, AlarmStatus
from yield_guardian.contracts.methods import MeasuredResults, MethodsOverview, ModelCard
from yield_guardian.contracts.session import (
    GuestSessionCreate,
    LoginRequest,
    SessionInfo,
    SessionRole,
    WorkspaceInfo,
)
from yield_guardian.contracts.workorders import (
    AuditAction,
    AuditPage,
    WorkOrder,
    WorkOrderPage,
    WorkOrderUpdate,
)
from yield_guardian.contracts.workspace import (
    AdminSessionPage,
    HandoffCreated,
    WorkInvestigationPage,
    WorkRun,
    WorkRunPage,
    WorkRunUpdate,
    WorkspaceSummary,
    WorkUploadPage,
)
from yield_guardian.services.access import Viewer


@dataclass(frozen=True, slots=True)
class ActiveSession:
    """A device session as the server sees it. Only `info()` leaves the server.

    `session_id` is empty for a request without a session (``VISITOR``); a visitor session that
    has a workspace has an ID, a CSRF token and a `workspace_id`. `expires_at` is when the
    engineer or admin role ends, `session_expires_at` when the device session itself ends.
    """

    session_id: str
    role: SessionRole
    display_name: str | None
    csrf_token: str | None
    expires_at: datetime | None
    workspace_id: str | None = None
    session_expires_at: datetime | None = None

    def info(self) -> SessionInfo:
        workspace = (
            WorkspaceInfo(
                workspace_id=self.workspace_id, session_expires_at=self.session_expires_at
            )
            if self.workspace_id is not None and self.session_expires_at is not None
            else None
        )
        return SessionInfo(
            role=self.role,
            display_name=self.display_name,
            expires_at=self.expires_at,
            csrf_token=self.csrf_token,
            workspace=workspace,
        )

    @property
    def exists(self) -> bool:
        """A stored session (with a cookie), whatever its role."""
        return bool(self.session_id)

    @property
    def viewer(self) -> Viewer:
        """What this session may see: its workspace's rows, and rows with no workspace."""
        return Viewer(self.workspace_id)


VISITOR = ActiveSession(
    session_id="", role="visitor", display_name=None, csrf_token=None, expires_at=None
)


class AlarmService(Protocol):
    """The SECOM unit alarms (``AL-<unit>-<kind>``) over every unit, newest first."""

    async def list_alarms(
        self,
        *,
        status: AlarmStatus | None = None,
        kind: AlarmKind | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> AlarmPage: ...


class InvestigationStore(Protocol):
    """A `viewer` limits what is found to what that workspace may open (None: anything); another
    workspace's investigation answers as a missing one."""

    async def create(
        self, trigger: InvestigationTrigger, *, session: ActiveSession, title: str | None = None
    ) -> Investigation: ...

    async def get(self, investigation_id: str, viewer: Viewer | None = None) -> Investigation: ...

    async def list(
        self,
        *,
        status: InvestigationStatus | None = None,
        cursor: str | None = None,
        limit: int = 50,
        viewer: Viewer | None = None,
    ) -> InvestigationPage: ...

    async def get_evidence(
        self, investigation_id: str, evidence_id: str, viewer: Viewer | None = None
    ) -> Evidence: ...

    def events(
        self, investigation_id: str, *, after_seq: int | None = None
    ) -> AsyncIterator[InvestigationEventPayload]:
        """Stored events after `after_seq`, then live ones until the end event."""
        ...

    async def decide(
        self, investigation_id: str, decision: DecisionCreate, *, session: ActiveSession
    ) -> Investigation: ...


class WorkOrderStore(Protocol):
    async def list(
        self, *, cursor: str | None = None, limit: int = 50, viewer: Viewer | None = None
    ) -> WorkOrderPage: ...

    async def get(self, work_order_id: str, viewer: Viewer | None = None) -> WorkOrder: ...

    async def update(
        self, work_order_id: str, update: WorkOrderUpdate, *, session: ActiveSession
    ) -> WorkOrder: ...


class AuditLog(Protocol):
    async def list(
        self,
        *,
        action: AuditAction | None = None,
        cursor: str | None = None,
        limit: int = 50,
        viewer: Viewer | None = None,
    ) -> AuditPage: ...


class SessionManager(Protocol):
    """Device sessions and their workspaces. Every method that returns a token returns the
    cookie value to set (a new one whenever the role or the workspace changes)."""

    async def resolve(self, token: str | None) -> ActiveSession:
        """The session for a cookie token; VISITOR when missing, expired or unknown."""
        ...

    async def open_visitor(self, *, client: str) -> tuple[ActiveSession, str]:
        """A new visitor session with its own new workspace (a browser's first visit)."""
        ...

    async def guest(
        self, body: GuestSessionCreate, *, client: str, current: ActiveSession = ...
    ) -> tuple[ActiveSession, str]:
        """ "Try as engineer": raise the current session to engineer (keeping its workspace),
        or start one; returns it and the cookie token."""
        ...

    async def login(
        self, body: LoginRequest, *, client: str, current: ActiveSession = ...
    ) -> tuple[ActiveSession, str]: ...

    async def logout(self, session: ActiveSession) -> tuple[ActiveSession, str] | None:
        """Back to visitor in the same workspace; None when there was nothing to sign out."""
        ...

    async def workspace(self, session: ActiveSession) -> WorkspaceSummary: ...

    async def create_handoff(self, session: ActiveSession) -> HandoffCreated: ...

    async def join(self, session: ActiveSession, code: str) -> tuple[ActiveSession, str]: ...

    async def fresh(self, session: ActiveSession) -> tuple[ActiveSession, str]: ...

    async def list_sessions(
        self, *, current: ActiveSession, cursor: str | None = None, limit: int = 50
    ) -> AdminSessionPage: ...

    async def revoke(self, session_id: str, *, by: ActiveSession) -> None: ...

    async def prune(self) -> object:
        """Delete ended sessions and codes, and every workspace last used 30 days ago or that
        no device can reach, with everything in it."""
        ...


class WorkspaceStore(Protocol):
    """What one workspace started: its runs, uploads and investigations, newest first."""

    async def list_runs(
        self,
        workspace_id: str | None,
        *,
        archived: bool = False,
        cursor: str | None = None,
        limit: int = 20,
    ) -> WorkRunPage: ...

    async def update_run(
        self, workspace_id: str | None, run_id: str, update: WorkRunUpdate
    ) -> WorkRun: ...

    async def delete_run(self, workspace_id: str | None, run_id: str) -> None: ...

    async def list_uploads(
        self, workspace_id: str | None, *, cursor: str | None = None, limit: int = 20
    ) -> WorkUploadPage: ...

    async def list_investigations(
        self, workspace_id: str | None, *, cursor: str | None = None, limit: int = 20
    ) -> WorkInvestigationPage: ...


class MethodsService(Protocol):
    async def overview(self) -> MethodsOverview: ...

    async def model_card(self, name: str) -> ModelCard: ...

    async def results(self) -> MeasuredResults: ...
