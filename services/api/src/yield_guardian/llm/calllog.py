"""Every model call is reported to an :class:`LlmCallLog` (the Models page reads it).

One record per attempt on one model: a cache hit, a refusal by a profile rule (an invalid
request that is never sent), an HTTP error after retries, an empty or invalid answer, or a
success. Token and point fields are None when unknown (the endpoint did not report usage)
and 0 when known to be zero (a cache hit, or a request refused by its profile).

The in-memory log serves tests and single-process runs; the database layer implements the
same protocol (see the requests to the lead for the table).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from yield_guardian.contracts.models import CallStatus as ContractCallStatus
from yield_guardian.contracts.models import CallUsage, LlmCall, RoleName, Usage


class CallStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    REFUSED_PROFILE = "refused_profile"
    EMPTY = "empty"
    INVALID_OUTPUT = "invalid_output"


NOT_SENT = frozenset({CallStatus.REFUSED_PROFILE})


class LlmCallRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    started_at: datetime
    role: RoleName
    model: str
    status: CallStatus
    cache_hit: bool
    stream: bool
    tokens_in: int | None
    tokens_out: int | None
    tokens_reasoning: int | None
    tokens_cached: int | None
    points: float | None
    latency_ms: float
    attempts: int
    http_status: int | None = None
    error_kind: str | None = None
    error_message: str | None = None
    error_body: str | None = None
    """The provider's error body on an HTTP error, secrets masked, at most 2000 characters."""
    request_key: str | None = None
    correlation_id: str | None = None

    @property
    def sent(self) -> bool:
        """True when the request reached the endpoint (not a cache hit, not refused)."""
        return not self.cache_hit and self.status not in NOT_SENT

    @property
    def usage_known(self) -> bool:
        return self.tokens_in is not None and self.tokens_out is not None


@runtime_checkable
class LlmCallLog(Protocol):
    async def record(self, record: LlmCallRecord) -> None: ...

    async def since(self, start: datetime) -> Sequence[LlmCallRecord]:
        """Records with ``started_at >= start``, oldest first."""
        ...


class InMemoryCallLog:
    def __init__(self) -> None:
        self.records: list[LlmCallRecord] = []

    async def record(self, record: LlmCallRecord) -> None:
        self.records.append(record)

    async def since(self, start: datetime) -> Sequence[LlmCallRecord]:
        return [r for r in self.records if r.started_at >= start]


def contract_status(record: LlmCallRecord) -> ContractCallStatus:
    if record.cache_hit:
        return "cached"
    if record.status is CallStatus.OK:
        return "ok"
    if record.status in NOT_SENT:
        return "refused"
    return "error"


def to_call_usage(record: LlmCallRecord) -> CallUsage:
    """The contract's view of one call; a count the endpoint did not report stays null."""
    return CallUsage(
        role=record.role,
        model_id=record.model,
        tokens_in=record.tokens_in,
        tokens_out=record.tokens_out,
        tokens_reasoning=record.tokens_reasoning,
        points=_points(record),
        latency_ms=max(round(record.latency_ms), 0),
        cached=record.cache_hit,
    )


def to_llm_call(record: LlmCallRecord) -> LlmCall:
    error = None
    if record.status is not CallStatus.OK:
        error = record.error_message or str(record.status)
    elif not record.cache_hit and not record.usage_known:
        error = "usage not reported by the endpoint"
    return LlmCall(
        at=record.started_at,
        role=record.role,
        model_id=record.model,
        status=contract_status(record),
        tokens_in=record.tokens_in,
        tokens_out=record.tokens_out,
        tokens_reasoning=record.tokens_reasoning,
        points=_points(record),
        latency_ms=max(round(record.latency_ms), 0),
        error=error,
    )


def total_usage(records: Sequence[LlmCallRecord]) -> Usage:
    """Sums over the sent calls that reported usage; the others are counted, not guessed."""
    sent = [r for r in records if r.sent]
    known = [r for r in sent if r.usage_known]
    return Usage(
        requests=len(sent),
        tokens_in=sum(r.tokens_in or 0 for r in known),
        tokens_out=sum(r.tokens_out or 0 for r in known),
        tokens_reasoning=sum(r.tokens_reasoning or 0 for r in known),
        points=sum(max(r.points or 0.0, 0.0) for r in known),
        cache_hits=sum(r.cache_hit for r in records),
        requests_without_usage=len(sent) - len(known),
    )


def _points(record: LlmCallRecord) -> float | None:
    return None if record.points is None else max(record.points, 0.0)
