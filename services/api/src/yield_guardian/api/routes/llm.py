from fastapi import APIRouter

from yield_guardian.api.deps import AdminSession, Llm
from yield_guardian.api.problems import problem_responses
from yield_guardian.contracts.models import (
    CatalogModel,
    Evaluations,
    RoleAssignment,
    RoleAssignmentUpdate,
    RoleName,
    UsageReport,
)

router = APIRouter(tags=["language models"])


@router.get("/llm/catalog", operation_id="get_model_catalog", responses=problem_responses(503))
async def get_model_catalog(llm: Llm) -> list[CatalogModel]:
    """Models available on AMD Token Factory with their capability profiles."""
    return await llm.catalog()


@router.get("/llm/roles", operation_id="get_role_assignments", responses=problem_responses(503))
async def get_role_assignments(llm: Llm) -> list[RoleAssignment]:
    return await llm.roles()


@router.put(
    "/llm/roles/{role}",
    operation_id="update_role_assignment",
    responses=problem_responses(400, 401, 403, 503),
)
async def update_role_assignment(
    session: AdminSession, role: RoleName, body: RoleAssignmentUpdate, llm: Llm
) -> RoleAssignment:
    """Assign a model to a role (admins). Takes effect on the next call, without a restart."""
    return await llm.set_role(role, body, actor=session.display_name or "admin")


@router.get("/llm/usage", operation_id="get_llm_usage", responses=problem_responses(503))
async def get_llm_usage(llm: Llm) -> UsageReport:
    """Tokens and points used today, the quota and the budget guard."""
    return await llm.usage()


@router.get(
    "/llm/evaluations", operation_id="get_llm_evaluations", responses=problem_responses(503)
)
async def get_llm_evaluations(llm: Llm) -> Evaluations:
    return await llm.evaluations()
