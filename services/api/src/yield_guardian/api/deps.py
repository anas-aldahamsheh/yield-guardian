"""Dependencies shared by the routes: services, the current session and CSRF checks."""

import secrets
from typing import Annotated

from fastapi import Depends, Header, Request

from yield_guardian.api.problems import ProblemError
from yield_guardian.contracts.services import (
    ChatResponder,
    InvestigationRunner,
    KnowledgeService,
    LlmAdmin,
    NotReadyError,
    SecomService,
    WaferService,
)
from yield_guardian.services.jobs import NO_RUNNER_DETAIL
from yield_guardian.services.protocols import (
    VISITOR,
    ActiveSession,
    AuditLog,
    InvestigationStore,
    LineService,
    MethodsService,
    SessionManager,
    WorkOrderStore,
)
from yield_guardian.services.registry import ServiceRegistry

SESSION_COOKIE = "yg_session"
CSRF_HEADER = "X-CSRF-Token"


def get_registry(request: Request) -> ServiceRegistry:
    registry = request.app.state.registry
    assert isinstance(registry, ServiceRegistry)
    return registry


Registry = Annotated[ServiceRegistry, Depends(get_registry)]


def _need[T](service: T | None, what: str) -> T:
    if service is None:
        raise NotReadyError(f"The {what} is not available yet.")
    return service


def secom_service(registry: Registry) -> SecomService:
    return _need(registry.secom, "SECOM data and model bundle")


def wafer_service(registry: Registry) -> WaferService:
    return _need(registry.wafer, "wafer-map model bundle")


def knowledge_service(registry: Registry) -> KnowledgeService:
    return _need(registry.knowledge, "knowledge base")


def line_service(registry: Registry) -> LineService:
    return _need(registry.line, "line replay")


def investigation_store(registry: Registry) -> InvestigationStore:
    return _need(registry.investigations, "investigation store")


def investigation_runner(registry: Registry) -> InvestigationRunner:
    return _need(registry.runner, "investigator")


def live_investigator(registry: Registry) -> InvestigationRunner:
    """The investigator, checked before a live run is created: without it the create route
    answers 503 and leaves no run behind (the job worker would only fail it at once)."""
    if registry.runner is None:
        raise NotReadyError(NO_RUNNER_DETAIL)
    return registry.runner


def work_order_store(registry: Registry) -> WorkOrderStore:
    return _need(registry.work_orders, "work order store")


def audit_log(registry: Registry) -> AuditLog:
    return _need(registry.audit, "audit log")


def session_manager(registry: Registry) -> SessionManager:
    return _need(registry.sessions, "session service")


def methods_service(registry: Registry) -> MethodsService:
    return _need(registry.methods, "methods data")


def chat_responder(registry: Registry) -> ChatResponder:
    return _need(registry.chat, "engineer chat")


def llm_admin(registry: Registry) -> LlmAdmin:
    return _need(registry.llm, "model registry")


Secom = Annotated[SecomService, Depends(secom_service)]
Wafers = Annotated[WaferService, Depends(wafer_service)]
Knowledge = Annotated[KnowledgeService, Depends(knowledge_service)]
Line = Annotated[LineService, Depends(line_service)]
Investigations = Annotated[InvestigationStore, Depends(investigation_store)]
WorkOrders = Annotated[WorkOrderStore, Depends(work_order_store)]
Audit = Annotated[AuditLog, Depends(audit_log)]
Sessions = Annotated[SessionManager, Depends(session_manager)]
Methods = Annotated[MethodsService, Depends(methods_service)]
Chat = Annotated[ChatResponder, Depends(chat_responder)]
Llm = Annotated[LlmAdmin, Depends(llm_admin)]
LiveInvestigator = Annotated[InvestigationRunner, Depends(live_investigator)]


async def current_session(request: Request, registry: Registry) -> ActiveSession:
    if registry.sessions is None:
        return VISITOR
    return await registry.sessions.resolve(request.cookies.get(SESSION_COOKIE))


CurrentSession = Annotated[ActiveSession, Depends(current_session)]


def _check_csrf(session: ActiveSession, token: str | None) -> None:
    expected = session.csrf_token
    if expected is None or token is None or not secrets.compare_digest(expected, token):
        raise ProblemError(
            403,
            "csrf_failed",
            "Request not verified",
            "Send the session's CSRF token in X-CSRF-Token.",
        )


async def engineer_session(
    session: CurrentSession,
    x_csrf_token: Annotated[str | None, Header(alias=CSRF_HEADER)] = None,
) -> ActiveSession:
    """An engineer or admin session with a valid CSRF token (for actions)."""
    if session.role == "visitor":
        raise ProblemError(
            401, "unauthorized", "Sign-in required", 'Choose "Try as engineer" to take actions.'
        )
    _check_csrf(session, x_csrf_token)
    return session


async def admin_session(
    session: CurrentSession,
    x_csrf_token: Annotated[str | None, Header(alias=CSRF_HEADER)] = None,
) -> ActiveSession:
    if session.role != "admin":
        raise ProblemError(
            403, "forbidden", "Admins only", "Sign in as an administrator to change settings."
        )
    _check_csrf(session, x_csrf_token)
    return session


EngineerSession = Annotated[ActiveSession, Depends(engineer_session)]
AdminSession = Annotated[ActiveSession, Depends(admin_session)]
