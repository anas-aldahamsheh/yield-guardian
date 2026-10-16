"""The session of this device: its workspace, its role, and the workspace handoff."""

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request, Response, status

from yield_guardian.api.deps import (
    SESSION_COOKIE,
    AdminReader,
    AdminSession,
    CurrentSession,
    Registry,
    Sessions,
    WorkspaceSession,
    client_of,
    from_other_site,
    set_session_cookie,
)
from yield_guardian.api.problems import ProblemError, problem_responses
from yield_guardian.contracts.session import GuestSessionCreate, LoginRequest, SessionInfo
from yield_guardian.contracts.workspace import (
    AdminSessionPage,
    HandoffCreated,
    HandoffRedeem,
    WorkspaceSummary,
)

router = APIRouter(tags=["session"])

SessionPath = Annotated[
    str, Path(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
]


@router.get("/session", operation_id="get_session")
async def get_session(session: CurrentSession) -> SessionInfo:
    """The current session; role "visitor" and no workspace when there is none."""
    return session.info()


@router.post(
    "/session/workspace", operation_id="open_workspace", responses=problem_responses(403, 503)
)
async def open_workspace(
    request: Request,
    response: Response,
    session: CurrentSession,
    sessions: Sessions,
    registry: Registry,
) -> SessionInfo:
    """This device's session and workspace, made on its first visit (no sign-up). Called on every
    page load: it also renews the cookie, which lasts as long as the device session."""
    if session.exists:
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            set_session_cookie(response, token, registry)
        return session.info()
    if from_other_site(request):
        raise ProblemError(
            403, "forbidden", "Not allowed", "A workspace is opened from this site's own pages."
        )
    opened, token = await sessions.open_visitor(client=client_of(request))
    set_session_cookie(response, token, registry)
    return opened.info()


@router.post("/session/guest", operation_id="start_guest_session", responses=problem_responses(503))
async def start_guest_session(
    body: GuestSessionCreate,
    request: Request,
    response: Response,
    session: CurrentSession,
    sessions: Sessions,
    registry: Registry,
) -> SessionInfo:
    """ "Try as engineer": this device becomes an engineer (approve, reject, ask) and keeps its
    workspace."""
    started, token = await sessions.guest(body, client=client_of(request), current=session)
    set_session_cookie(response, token, registry)
    return started.info()


@router.post("/session/login", operation_id="login", responses=problem_responses(401, 503))
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: CurrentSession,
    sessions: Sessions,
    registry: Registry,
) -> SessionInfo:
    started, token = await sessions.login(body, client=client_of(request), current=session)
    set_session_cookie(response, token, registry)
    return started.info()


@router.post("/session/logout", operation_id="logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(session: CurrentSession, response: Response, registry: Registry) -> None:
    """Back to visitor: the engineer or admin role ends, this device keeps its workspace."""
    if registry.sessions is None or not session.exists:
        return
    ended = await registry.sessions.logout(session)
    if ended is not None:
        set_session_cookie(response, ended[1], registry)


# -- the workspace -----------------------------------------------------------------------------


@router.get(
    "/workspace",
    operation_id="get_workspace",
    tags=["workspace"],
    responses=problem_responses(404, 503),
)
async def get_workspace(session: CurrentSession, sessions: Sessions) -> WorkspaceSummary:
    """This device's workspace: the devices attached to it and how much it holds."""
    if not session.exists:
        raise ProblemError(
            404, "not_found", "No workspace", "This device has no workspace yet. Reload the page."
        )
    return await sessions.workspace(session)


@router.post(
    "/workspace/handoffs",
    operation_id="create_handoff",
    tags=["workspace"],
    status_code=status.HTTP_201_CREATED,
    responses=problem_responses(401, 403, 404, 503),
)
async def create_handoff(session: WorkspaceSession, sessions: Sessions) -> HandoffCreated:
    """A single-use code that attaches another device to this workspace, for 10 minutes. A new
    code replaces the last unused one."""
    return await sessions.create_handoff(session)


@router.post(
    "/workspace/join",
    operation_id="join_workspace",
    tags=["workspace"],
    responses=problem_responses(400, 401, 403, 404, 410, 503),
)
async def join_workspace(
    body: HandoffRedeem,
    response: Response,
    session: WorkspaceSession,
    sessions: Sessions,
    registry: Registry,
) -> SessionInfo:
    """Attach this device to the workspace that made the code. The code is then used up."""
    joined, token = await sessions.join(session, body.code)
    set_session_cookie(response, token, registry)
    return joined.info()


@router.post(
    "/workspace/fresh",
    operation_id="start_fresh_workspace",
    tags=["workspace"],
    responses=problem_responses(401, 403, 404, 503),
)
async def start_fresh_workspace(
    response: Response, session: WorkspaceSession, sessions: Sessions, registry: Registry
) -> SessionInfo:
    """Move this device to a new, empty workspace; other devices keep the old one."""
    moved, token = await sessions.fresh(session)
    set_session_cookie(response, token, registry)
    return moved.info()


# -- admin -------------------------------------------------------------------------------------


@router.get(
    "/admin/sessions",
    operation_id="list_sessions",
    tags=["admin"],
    responses=problem_responses(400, 403, 503),
)
async def list_sessions(
    session: AdminReader,
    sessions: Sessions,
    cursor: Annotated[str | None, Query(max_length=300)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AdminSessionPage:
    """Active device sessions, most recently seen first (admins only). No cookie value or token
    is ever shown."""
    return await sessions.list_sessions(current=session, cursor=cursor, limit=limit)


@router.delete(
    "/admin/sessions/{session_id}",
    operation_id="revoke_session",
    tags=["admin"],
    status_code=status.HTTP_204_NO_CONTENT,
    responses=problem_responses(403, 404, 503),
)
async def revoke_session(
    session: AdminSession, sessions: Sessions, session_id: SessionPath
) -> None:
    """End a device session now (admins only, with the CSRF token)."""
    await sessions.revoke(session_id, by=session)
