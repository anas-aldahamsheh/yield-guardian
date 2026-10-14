"""Errors of the language-model layer, and parsing of Token Factory error bodies.

Token Factory returns errors in two shapes (``docs/vendor/token-factory.md``, "Errors"):
the gateway uses the OpenAI shape ``{"error": {...}}`` and the platform wraps it as
``{"detail": {"error": {...}}}``. FastAPI-style ``{"detail": "..."}`` and
``{"detail": [{"msg": ...}]}`` bodies (typical of 422 validation errors) are parsed too.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

ErrorShape = Literal["gateway", "platform", "detail_string", "detail_list", "unknown"]

_MAX_MESSAGE = 500


class ApiErrorBody(BaseModel):
    """The useful part of an error body, whatever its shape."""

    model_config = ConfigDict(frozen=True)

    message: str
    type: str | None = None
    code: str | None = None
    param: str | None = None
    shape: ErrorShape = "unknown"


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, int | float | bool):
        return str(value)
    return None


def _from_object(obj: Mapping[str, Any], shape: ErrorShape) -> ApiErrorBody:
    message = _as_text(obj.get("message")) or _as_text(obj.get("msg")) or "unspecified error"
    return ApiErrorBody(
        message=message[:_MAX_MESSAGE],
        type=_as_text(obj.get("type")),
        code=_as_text(obj.get("code")),
        param=_as_text(obj.get("param")),
        shape=shape,
    )


def _from_detail_list(items: Sequence[Any]) -> ApiErrorBody:
    parts: list[str] = []
    for item in items:
        if isinstance(item, Mapping):
            msg = _as_text(item.get("msg")) or _as_text(item.get("message")) or ""
            loc = item.get("loc")
            where = ".".join(str(p) for p in loc) if isinstance(loc, list | tuple) else ""
            parts.append(f"{where}: {msg}" if where else msg)
        elif isinstance(item, str):
            parts.append(item)
    message = "; ".join(p for p in parts if p) or "validation error"
    return ApiErrorBody(message=message[:_MAX_MESSAGE], shape="detail_list")


def parse_error_body(payload: object, raw_text: str = "") -> ApiErrorBody:
    """Extract the error from any of the documented shapes, falling back to raw text."""
    if isinstance(payload, Mapping):
        error = payload.get("error")
        if isinstance(error, Mapping):
            return _from_object(error, "gateway")
        if isinstance(error, str):
            return ApiErrorBody(message=error[:_MAX_MESSAGE], shape="gateway")
        detail = payload.get("detail")
        if isinstance(detail, Mapping):
            inner = detail.get("error")
            if isinstance(inner, Mapping):
                return _from_object(inner, "platform")
            if isinstance(inner, str):
                return ApiErrorBody(message=inner[:_MAX_MESSAGE], shape="platform")
            return _from_object(detail, "platform")
        if isinstance(detail, str):
            return ApiErrorBody(message=detail[:_MAX_MESSAGE], shape="detail_string")
        if isinstance(detail, list):
            return _from_detail_list(detail)
        if "message" in payload:
            return _from_object(payload, "unknown")
    text = raw_text.strip()
    return ApiErrorBody(message=(text or "empty error body")[:_MAX_MESSAGE], shape="unknown")


class ErrorKind(StrEnum):
    BAD_REQUEST = "bad_request"
    UNKNOWN_MODEL = "unknown_model"
    INSUFFICIENT_CREDITS = "insufficient_credits"
    UNAUTHORIZED = "unauthorized"
    ACCOUNT_NOT_VERIFIED = "account_not_verified"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    UNPROCESSABLE = "unprocessable"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    SERVER_ERROR = "server_error"
    OTHER = "other"


def classify(status: int, error: ApiErrorBody) -> ErrorKind:
    """Map a status and body to the documented meanings (token-factory.md, "Errors")."""
    text = " ".join(filter(None, (error.message, error.type, error.code))).lower()
    if status == 400:
        if "not supported" in text and "model" in text:
            return ErrorKind.UNKNOWN_MODEL
        if "credit" in text:
            return ErrorKind.INSUFFICIENT_CREDITS
        return ErrorKind.BAD_REQUEST
    if status == 401:
        return ErrorKind.UNAUTHORIZED
    if status == 403:
        if "account_not_verified" in text:
            return ErrorKind.ACCOUNT_NOT_VERIFIED
        return ErrorKind.FORBIDDEN
    if status == 404:
        return ErrorKind.NOT_FOUND
    if status == 422:
        return ErrorKind.UNPROCESSABLE
    if status == 429:
        return ErrorKind.RATE_LIMITED
    if status in (502, 503):
        return ErrorKind.UNAVAILABLE
    if status >= 500:
        return ErrorKind.SERVER_ERROR
    return ErrorKind.OTHER


class LlmError(Exception):
    """Base class of every error raised by this package."""


class ProfileViolationError(LlmError):
    """A request would break a model's documented rules; it was refused before sending."""

    def __init__(self, model: str, rule: str, detail: str) -> None:
        super().__init__(f"{model}: {detail} [{rule}]")
        self.model = model
        self.rule = rule
        self.detail = detail


MAX_ERROR_BODY = 2000
_SECRETS = (
    re.compile(r"rc-[0-9A-Fa-f]{16,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(
        r"(?i)(\"?(?:api[_-]?key|authorization|token|secret|password)\"?\s*[:=]\s*)\"?[^\s\",}]+"
    ),
)


def mask_secrets(text: str) -> str:
    """``text`` with API keys, bearer tokens and key-like fields replaced by ``[redacted]``."""
    for pattern in _SECRETS:
        text = pattern.sub(lambda m: (m.group(1) if m.lastindex else "") + "[redacted]", text)
    return text


def error_body_excerpt(text: str, limit: int = MAX_ERROR_BODY) -> str | None:
    """The provider's error body for logs and call records: secrets masked, cut to ``limit``."""
    body = mask_secrets(text.strip())
    if not body:
        return None
    return body if len(body) <= limit else body[:limit] + "…"


class TokenFactoryHttpError(LlmError):
    """The server answered with a non-success status (after any retries)."""

    def __init__(
        self,
        status: int,
        error: ApiErrorBody,
        *,
        retry_after: float | None = None,
        attempts: int = 1,
        headers: Mapping[str, str] | None = None,
        body: str | None = None,
    ) -> None:
        self.status = status
        self.error = error
        self.body = body
        """The raw error body, secrets masked and truncated (:func:`error_body_excerpt`)."""
        self.kind = classify(status, error)
        self.retry_after = retry_after
        self.attempts = attempts
        self.headers = dict(headers or {})
        super().__init__(f"HTTP {status} ({self.kind}): {error.message}")


class TransportError(LlmError):
    """No HTTP answer: connection failure or timeout. Never retried (the request may have
    been processed, and only 429, 502 and 503 are retried by policy)."""


class ResponseShapeError(LlmError):
    """A success response whose body does not have the documented shape."""


class StreamProtocolError(LlmError):
    """A stream that is malformed or ended without ``data: [DONE]``."""


class StreamReportedError(LlmError):
    """The server reported an error inside an open stream."""

    def __init__(self, error: ApiErrorBody) -> None:
        super().__init__(f"error in stream: {error.message}")
        self.error = error


class EmptyCompletionError(LlmError):
    """The model returned neither content nor tool calls, typically ``finish_reason: length``
    because thinking tokens used up ``max_tokens``."""

    def __init__(self, model: str, finish_reason: str | None) -> None:
        super().__init__(f"{model} returned no content (finish_reason={finish_reason})")
        self.model = model
        self.finish_reason = finish_reason


class InvalidStructuredOutputError(LlmError):
    """A structured (JSON) answer that does not parse or does not validate."""

    def __init__(self, model: str, detail: str) -> None:
        super().__init__(f"{model}: invalid structured output: {detail}")
        self.model = model
        self.detail = detail


class NoModelAvailableError(LlmError):
    """Every model in a role's fallback chain failed or was skipped."""

    def __init__(self, role: str, failures: Sequence[tuple[str, str]]) -> None:
        listed = "; ".join(f"{model}: {why}" for model, why in failures) or "empty chain"
        super().__init__(f"no model could serve role {role!r} ({listed})")
        self.role = role
        self.failures = list(failures)


class CassetteError(LlmError):
    """A recorded-fixture mismatch or a misuse of record mode."""
