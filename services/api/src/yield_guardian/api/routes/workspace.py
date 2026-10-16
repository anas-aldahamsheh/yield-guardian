"""Your work: this workspace's runs, uploads and investigations, newest first (PLAN_V2 §3, the
owner's "keep the full context" ask). Lists are per workspace; without a session they are empty."""

from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from yield_guardian.api.deps import CurrentSession, Workspace, WorkspaceSession
from yield_guardian.api.problems import problem_responses
from yield_guardian.contracts.workspace import (
    WorkInvestigationPage,
    WorkRun,
    WorkRunPage,
    WorkRunUpdate,
    WorkUploadPage,
)

router = APIRouter(tags=["workspace"])

RunPath = Annotated[str, Path(pattern=r"^run_[0-9a-z]{8,40}$")]
Cursor = Annotated[str | None, Query(max_length=300)]
Limit = Annotated[int, Query(ge=1, le=100)]


@router.get(
    "/workspace/runs", operation_id="list_workspace_runs", responses=problem_responses(400, 503)
)
async def list_workspace_runs(
    session: CurrentSession,
    workspace: Workspace,
    archived: bool = False,
    cursor: Cursor = None,
    limit: Limit = 20,
) -> WorkRunPage:
    """This workspace's runs that can still be opened, newest first, each with its live status,
    alarms, the investigations started from them and what it still needs. `archived=true` lists
    the archived ones instead."""
    return await workspace.list_runs(
        session.workspace_id, archived=archived, cursor=cursor, limit=limit
    )


@router.patch(
    "/workspace/runs/{run_id}",
    operation_id="update_workspace_run",
    responses=problem_responses(400, 401, 403, 404, 503),
)
async def update_workspace_run(
    body: WorkRunUpdate, session: WorkspaceSession, workspace: Workspace, run_id: RunPath
) -> WorkRun:
    """Name a run, note on it, archive or restore it, or save the view to reopen it on. Only
    runs of this workspace."""
    return await workspace.update_run(session.workspace_id, run_id, body)


@router.delete(
    "/workspace/runs/{run_id}",
    operation_id="delete_workspace_run",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=problem_responses(400, 401, 403, 404, 503),
)
async def delete_workspace_run(
    session: WorkspaceSession, workspace: Workspace, run_id: RunPath
) -> None:
    """Delete a run of this workspace for good: its results, alarms and the investigations this
    workspace started from it, with their work orders and audit entries. Only runs of this
    workspace; the product's example is never deleted (403)."""
    await workspace.delete_run(session.workspace_id, run_id)


@router.get(
    "/workspace/uploads",
    operation_id="list_workspace_uploads",
    responses=problem_responses(400, 503),
)
async def list_workspace_uploads(
    session: CurrentSession, workspace: Workspace, cursor: Cursor = None, limit: Limit = 20
) -> WorkUploadPage:
    """Files this workspace uploaded, newest first, with the runs started from each."""
    return await workspace.list_uploads(session.workspace_id, cursor=cursor, limit=limit)


@router.get(
    "/workspace/investigations",
    operation_id="list_workspace_investigations",
    responses=problem_responses(400, 503),
)
async def list_workspace_investigations(
    session: CurrentSession, workspace: Workspace, cursor: Cursor = None, limit: Limit = 20
) -> WorkInvestigationPage:
    """Investigations this workspace started, newest first, with their live status and the run
    and alarm each came from."""
    return await workspace.list_investigations(session.workspace_id, cursor=cursor, limit=limit)
