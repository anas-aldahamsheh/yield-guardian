"""Every model call is reported to an :class:`LlmCallLog` (the Models page reads it).

One record per attempt on one model: a cache hit, a refusal by the budget guard or by a
profile rule, an HTTP error after retries, an empty or invalid answer, or a success. Token
and point fields are None when unknown and 0 when known to be zero (a cache hit or a call
refused before sending).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict


class CallStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    REFUSED_BUDGET = "refused_budget"
    REFUSED_PROFILE = "refused_profile"
    EMPTY = "empty"
    INVALID_OUTPUT = "invalid_output"


class LlmCallRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    started_at: datetime
    role: str
    model: str
    status: CallStatus
    cache_hit: bool
    essential: bool
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
    request_key: str | None = None
    correlation_id: str | None = None


@runtime_checkable
class LlmCallLog(Protocol):
    async def record(self, record: LlmCallRecord) -> None: ...


class CallSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    calls: int
    ok: int
    cache_hits: int
    refused: int
    errors: int
    tokens_in: int
    tokens_out: int
    tokens_reasoning: int
    points: float
    unknown_points_calls: int


def summarize(records: Sequence[LlmCallRecord]) -> CallSummary:
    sent = [r for r in records if not r.cache_hit]
    return CallSummary(
        calls=len(records),
        ok=sum(r.status is CallStatus.OK for r in records),
        cache_hits=sum(r.cache_hit for r in records),
        refused=sum(
            r.status in (CallStatus.REFUSED_BUDGET, CallStatus.REFUSED_PROFILE) for r in records
        ),
        errors=sum(r.status is CallStatus.ERROR for r in records),
        tokens_in=sum(r.tokens_in or 0 for r in sent),
        tokens_out=sum(r.tokens_out or 0 for r in sent),
        tokens_reasoning=sum(r.tokens_reasoning or 0 for r in sent),
        points=sum(r.points or 0.0 for r in sent),
        unknown_points_calls=sum(r.points is None and r.status not in _NOT_SENT for r in sent),
    )


_NOT_SENT = frozenset({CallStatus.REFUSED_BUDGET, CallStatus.REFUSED_PROFILE})


class InMemoryCallLog:
    def __init__(self) -> None:
        self.records: list[LlmCallRecord] = []

    async def record(self, record: LlmCallRecord) -> None:
        self.records.append(record)

    def summary(self) -> CallSummary:
        return summarize(self.records)
