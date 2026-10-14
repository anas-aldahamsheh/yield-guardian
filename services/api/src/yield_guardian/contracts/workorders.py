"""Work orders opened by approved investigations, and the audit log of every action."""

from datetime import datetime
from typing import Literal

from pydantic import Field, JsonValue

from yield_guardian.contracts.base import Contract, Count, InvestigationId, WorkOrderId
from yield_guardian.contracts.investigation import Action

WorkOrderStatus = Literal["open", "in_progress", "done", "cancelled"]
ActorRole = Literal["system", "visitor", "engineer", "admin"]
AuditAction = Literal[
    "session.guest",
    "session.login",
    "session.login_failed",
    "session.logout",
    "investigation.created",
    "investigation.approved",
    "investigation.rejected",
    "work_order.created",
    "work_order.updated",
    "role.updated",
]


class WorkOrder(Contract):
    work_order_id: WorkOrderId
    investigation_id: InvestigationId
    title: str
    status: WorkOrderStatus
    created_at: datetime
    updated_at: datetime
    created_by: str
    actions: list[Action] = Field(description="The report actions the engineer approved.")
    note: str | None
    outcome: str | None = Field(description="What was found when the work was done.")
    outcome_confirmed: bool = Field(
        description="An engineer confirmed the outcome; only then may later reports use causal wording."
    )


class WorkOrderUpdate(Contract):
    status: WorkOrderStatus | None = None
    note: str | None = Field(None, max_length=2000)
    outcome: str | None = Field(None, max_length=2000)
    outcome_confirmed: bool | None = None


class WorkOrderPage(Contract):
    items: list[WorkOrder]
    next_cursor: str | None = None
    total: Count


class AuditEntry(Contract):
    audit_id: int = Field(ge=1)
    at: datetime
    actor_role: ActorRole
    actor_name: str | None
    action: AuditAction
    target_kind: str
    target_id: str
    details: dict[str, JsonValue]


class AuditPage(Contract):
    items: list[AuditEntry]
    next_cursor: str | None = None
    total: Count
