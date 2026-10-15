"""RFC 9457 problem+json for every error the API returns."""

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from yield_guardian.contracts.base import FieldError, Problem, ProblemCode
from yield_guardian.contracts.services import ServiceError

log = structlog.get_logger(__name__)

PROBLEM_MEDIA_TYPE = "application/problem+json"

_STATUS_CODES: dict[int, tuple[ProblemCode, str]] = {
    400: ("bad_request", "Bad request"),
    401: ("unauthorized", "Sign-in required"),
    403: ("forbidden", "Not allowed"),
    404: ("not_found", "Not found"),
    405: ("bad_request", "Method not allowed"),
    409: ("conflict", "Conflict"),
    410: ("gone", "Gone"),
    503: ("not_ready", "Not ready"),
}


class ProblemResponse(JSONResponse):
    media_type = PROBLEM_MEDIA_TYPE


class ProblemError(Exception):
    """Raise from a route to answer with a specific problem."""

    def __init__(
        self, status: int, code: ProblemCode, title: str, detail: str | None = None
    ) -> None:
        super().__init__(detail or title)
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail


def problem_response(problem: Problem) -> ProblemResponse:
    headers = (
        {"Retry-After": str(problem.retry_after_s)} if problem.retry_after_s is not None else None
    )
    return ProblemResponse(
        problem.model_dump(mode="json", exclude_none=True),
        status_code=problem.status,
        headers=headers,
    )


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses` entries for the given error statuses."""
    return {
        status: {
            "content": {PROBLEM_MEDIA_TYPE: {"schema": {"$ref": "#/components/schemas/Problem"}}},
            "description": _STATUS_CODES.get(status, ("internal_error", "Error"))[1],
        }
        for status in statuses
    }


async def _service_error(request: Request, exc: Exception) -> ProblemResponse:
    assert isinstance(exc, ServiceError)
    return problem_response(exc.problem(instance=request.url.path))


async def _api_problem(request: Request, exc: Exception) -> ProblemResponse:
    assert isinstance(exc, ProblemError)
    return problem_response(
        Problem(
            title=exc.title,
            status=exc.status,
            detail=exc.detail,
            code=exc.code,
            instance=request.url.path,
        )
    )


async def _validation_error(request: Request, exc: Exception) -> ProblemResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [
        FieldError(
            loc=[str(p) if not isinstance(p, int) else p for p in e.get("loc", ())],
            msg=e["msg"],
            type=e["type"],
        )
        for e in exc.errors()
    ]
    return problem_response(
        Problem(
            title="Invalid request",
            status=422,
            detail="One or more fields are invalid.",
            code="validation_error",
            instance=request.url.path,
            errors=errors,
        )
    )


async def _http_error(request: Request, exc: Exception) -> ProblemResponse:
    assert isinstance(exc, StarletteHTTPException)
    code, title = _STATUS_CODES.get(exc.status_code, ("internal_error", "Error"))
    detail = exc.detail if isinstance(exc.detail, str) and exc.detail != title else None
    return problem_response(
        Problem(
            title=title, status=exc.status_code, detail=detail, code=code, instance=request.url.path
        )
    )


async def _unhandled(request: Request, exc: Exception) -> ProblemResponse:
    log.exception("unhandled_error", path=request.url.path)
    return problem_response(
        Problem(
            title="Internal error",
            status=500,
            detail="The server could not complete the request. It has been logged.",
            code="internal_error",
            instance=request.url.path,
        )
    )


def install_problem_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ServiceError, _service_error)
    app.add_exception_handler(ProblemError, _api_problem)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unhandled)
