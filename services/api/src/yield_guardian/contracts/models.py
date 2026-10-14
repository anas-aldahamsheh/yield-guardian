"""Language-model roles, the model catalog, usage and evaluation results (AMD Token Factory)."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from yield_guardian.contracts.base import Contract, Count, Estimate

RoleName = Literal["investigator", "writer", "verifier", "chat", "router", "ocr", "vision"]
ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]
ModelKind = Literal["llm", "vlm", "ocr"]
InputType = Literal["text", "image", "audio", "document"]
ProfileSource = Literal["documented", "catalog_only"]
CallStatus = Literal["ok", "cached", "error", "refused"]
QuotaSource = Literal["usage_endpoint", "headers", "unknown"]


class Pricing(Contract):
    """Points per 1M tokens."""

    input: float = Field(ge=0)
    output: float = Field(ge=0)
    cache_read: float | None = Field(None, ge=0)


class CatalogModel(Contract):
    """A model the product can assign to a role, with the capability profile requests are built from."""

    model_id: str = Field(examples=["DeepSeek-V4.1-Flash"])
    kind: ModelKind
    context_length: int | None = Field(ge=1)
    inputs: list[InputType]
    thinks_by_default: bool | None
    reasoning_efforts: list[ReasoningEffort] = Field(
        description="Accepted values; empty if not applicable."
    )
    system_message_rule: str = Field(examples=["exactly one system message, first"])
    json_schema: bool = Field(description="Accepts strict json_schema response format.")
    tools: bool
    pricing: Pricing | None
    available: bool = Field(
        description="Reported by the live catalog (GET /v1/models) at the last sync."
    )
    profile: ProfileSource


class RoleAssignment(Contract):
    role: RoleName
    model_id: str
    reasoning_effort: ReasoningEffort | None
    fallbacks: list[str] = Field(description="Tried in order when the model is unavailable.")
    updated_at: datetime | None
    updated_by: str | None


class RoleAssignmentUpdate(Contract):
    model_id: str
    reasoning_effort: ReasoningEffort | None = None
    fallbacks: list[str] | None = Field(None, description="Null keeps the current chain.")


class Usage(Contract):
    """Totals over model calls. Token counts and points add up the calls whose usage the
    endpoint reported; `requests_without_usage` counts the others (their usage is unknown)."""

    requests: Count
    tokens_in: Count
    tokens_out: Count
    tokens_reasoning: Count
    points: float = Field(ge=0)
    cache_hits: Count
    requests_without_usage: Count = Field(
        description="Requests the endpoint answered without reporting usage; not in the sums."
    )


class CallUsage(Contract):
    """One model call. Token counts and points are null when the endpoint did not report
    usage (never shown as zero)."""

    role: RoleName
    model_id: str
    tokens_in: Count | None
    tokens_out: Count | None
    tokens_reasoning: Count | None
    points: float | None = Field(ge=0)
    latency_ms: int = Field(ge=0)
    cached: bool


class LlmCall(Contract):
    at: datetime
    role: RoleName
    model_id: str
    status: CallStatus
    tokens_in: Count | None = Field(description="Null when the endpoint did not report usage.")
    tokens_out: Count | None
    tokens_reasoning: Count | None
    points: float | None = Field(ge=0)
    latency_ms: int = Field(ge=0)
    error: str | None


class Quota(Contract):
    limit: float | None
    used: float | None
    remaining: float | None
    resets_at: datetime | None
    rpm_limit: int | None
    source: QuotaSource
    checked_at: datetime | None


class RoleUsage(Contract):
    role: RoleName
    usage: Usage


class ModelUsage(Contract):
    model_id: str
    usage: Usage


class UsageReport(Contract):
    since: datetime = Field(description="Start of the current quota day.")
    total: Usage
    by_role: list[RoleUsage]
    by_model: list[ModelUsage]
    quota: Quota = Field(description="Shown for information; the product never limits calls.")
    deterministic_answers: Count = Field(
        description="Chat questions answered by rules, without a model."
    )
    model_answers: Count
    recent: list[LlmCall] = Field(description="Newest first.")


class EvaluationResult(Contract):
    role: RoleName
    model_id: str
    task_set: str
    tasks: Count
    success_rate: Estimate
    violations: Count
    latency_ms_p50: float | None
    tokens_in: Count
    tokens_out: Count
    points: float = Field(ge=0)
    run_at: datetime


class Evaluations(Contract):
    results: list[EvaluationResult]
    note: str
