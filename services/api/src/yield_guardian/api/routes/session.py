from fastapi import APIRouter, Request, Response, status

from yield_guardian.api.deps import SESSION_COOKIE, CurrentSession, Registry, Sessions
from yield_guardian.api.problems import problem_responses
from yield_guardian.contracts.session import GuestSessionCreate, LoginRequest, SessionInfo

router = APIRouter(tags=["session"])


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _set_cookie(response: Response, token: str, registry: Registry) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=registry.settings.session_ttl_minutes * 60,
        httponly=True,
        secure=registry.settings.environment == "production",
        samesite="lax",
        path="/",
    )


@router.get("/session", operation_id="get_session")
async def get_session(session: CurrentSession) -> SessionInfo:
    """The current session; role "visitor" when signed out."""
    return session.info()


@router.post(
    "/session/guest", operation_id="start_guest_session", responses=problem_responses(429, 503)
)
async def start_guest_session(
    body: GuestSessionCreate,
    request: Request,
    response: Response,
    sessions: Sessions,
    registry: Registry,
) -> SessionInfo:
    """ "Try as engineer": an engineer session that can approve, reject and ask."""
    session, token = await sessions.guest(body, client=_client(request))
    _set_cookie(response, token, registry)
    return session.info()


@router.post("/session/login", operation_id="login", responses=problem_responses(401, 429, 503))
async def login(
    body: LoginRequest, request: Request, response: Response, sessions: Sessions, registry: Registry
) -> SessionInfo:
    session, token = await sessions.login(body, client=_client(request))
    _set_cookie(response, token, registry)
    return session.info()


@router.post("/session/logout", operation_id="logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(session: CurrentSession, response: Response, registry: Registry) -> None:
    if registry.sessions is not None and session.role != "visitor":
        await registry.sessions.logout(session)
    response.delete_cookie(SESSION_COOKIE, path="/")
