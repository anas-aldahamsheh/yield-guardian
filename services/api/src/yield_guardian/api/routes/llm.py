from fastapi import APIRouter

from yield_guardian.api.deps import AdminSession, Llm, WorkspaceSession
from yield_guardian.api.problems import problem_responses
from yield_guardian.contracts.models import (
    CatalogModel,
    Evaluations,
    LlmProviderState,
    LlmProviderUpdate,
    RoleAssignment,
    RoleAssignmentUpdate,
    RoleName,
    UsageReport,
)

router = APIRouter(tags=["language models"])


@router.get("/llm/provider", operation_id="get_llm_provider", responses=problem_responses(503))
async def get_llm_provider(llm: Llm) -> LlmProviderState:
    """The provider every role uses, for every user: Claude or AMD."""
    return await llm.provider()


@router.put(
    "/llm/provider",
    operation_id="update_llm_provider",
    responses=problem_responses(401, 403, 503),
)
async def update_llm_provider(
    session: WorkspaceSession, body: LlmProviderUpdate, llm: Llm
) -> LlmProviderState:
    """Switch every role to one provider, site-wide. Takes effect on the next call."""
    return await llm.set_provider(body.provider, actor=session.display_name or "visitor")


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
    """Tokens and points used today and the remaining quota (for information only)."""
    return await llm.usage()


@router.get(
    "/llm/evaluations", operation_id="get_llm_evaluations", responses=problem_responses(503)
)
async def get_llm_evaluations(llm: Llm) -> Evaluations:
    return await llm.evaluations()
