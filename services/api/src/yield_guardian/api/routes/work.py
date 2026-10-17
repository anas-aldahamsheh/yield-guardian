from typing import Annotated

from fastapi import APIRouter, Path, Query

from yield_guardian.api.deps import Audit, CurrentSession, EngineerSession, WorkOrders
from yield_guardian.api.problems import problem_responses
from yield_guardian.contracts.workorders import (
    AuditAction,
    AuditPage,
    WorkOrder,
    WorkOrderPage,
    WorkOrderUpdate,
)

router = APIRouter(tags=["work orders"])

WorkOrderPath = Annotated[str, Path(pattern=r"^WO-\d{6}$")]


@router.get("/work-orders", operation_id="list_work_orders", responses=problem_responses(503))
async def list_work_orders(
    store: WorkOrders,
    session: CurrentSession,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> WorkOrderPage:
    """The work orders of this workspace's investigations and of the product's example (marked
    `example`), newest first."""
    return await store.list(cursor=cursor, limit=limit, viewer=session.viewer)


@router.get(
    "/work-orders/{work_order_id}",
    operation_id="get_work_order",
    responses=problem_responses(404, 503),
)
async def get_work_order(
    store: WorkOrders, session: CurrentSession, work_order_id: WorkOrderPath
) -> WorkOrder:
    """Another workspace's work order answers 404, as a missing one does."""
    return await store.get(work_order_id, session.viewer)


@router.patch(
    "/work-orders/{work_order_id}",
    operation_id="update_work_order",
    responses=problem_responses(401, 403, 404, 503),
)
async def update_work_order(
    session: EngineerSession, body: WorkOrderUpdate, store: WorkOrders, work_order_id: WorkOrderPath
) -> WorkOrder:
    """The example's work order is read-only (403)."""
    return await store.update(work_order_id, body, session=session)


@router.delete(
    "/work-orders/{work_order_id}",
    operation_id="delete_work_order",
    status_code=204,
    responses=problem_responses(401, 403, 404, 503),
)
async def delete_work_order(
    session: EngineerSession, store: WorkOrders, work_order_id: WorkOrderPath
) -> None:
    """Deletes the work order; its investigation stays. The example's is read-only (403)."""
    await store.delete(work_order_id, session=session)


@router.get("/audit", operation_id="list_audit_entries", responses=problem_responses(503))
async def list_audit_entries(
    log: Audit,
    session: CurrentSession,
    action: AuditAction | None = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditPage:
    """Every action taken in this workspace, and those about the product's example (marked
    `example`), newest first."""
    return await log.list(action=action, cursor=cursor, limit=limit, viewer=session.viewer)
