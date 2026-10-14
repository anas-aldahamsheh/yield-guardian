"""The Models page backend: implements :class:`yield_guardian.contracts.services.LlmAdmin`.

It exposes the capability catalog, the role assignments (editable without a restart), the
usage report for the current quota day and the evaluation results, and tells the API whether
live model calls are possible (a key is configured; the product sets no request limits, by
owner decision of 2026-10-14). Quota readings are for display only.

The quota day starts at the reset time reported by ``GET /v1/usage`` minus 24 hours; when the
endpoint gives none, at the documented 19:00 Asia/Shanghai (UTC+8 all year, no daylight saving
since 1991, so a fixed offset is exact).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, time, timedelta, timezone
from typing import Protocol, runtime_checkable

import structlog

from yield_guardian.contracts.chat import RouteKind
from yield_guardian.contracts.models import (
    CatalogModel,
    EvaluationResult,
    Evaluations,
    InputType,
    ModelUsage,
    Quota,
    RoleAssignment,
    RoleAssignmentUpdate,
    RoleName,
    RoleUsage,
    UsageReport,
)
from yield_guardian.contracts.models import (
    ModelKind as ContractModelKind,
)
from yield_guardian.contracts.models import Pricing as ContractPricing
from yield_guardian.llm.calllog import LlmCallLog, to_llm_call, total_usage
from yield_guardian.llm.errors import LlmError
from yield_guardian.llm.profiles import (
    Availability,
    CatalogEntry,
    CatalogSyncReport,
    DeveloperRole,
    ModelKind,
    ModelProfile,
    SystemRule,
)
from yield_guardian.llm.registry import (
    InvalidAssignmentError,
    ModelChoice,
    ModelRegistry,
    Role,
    choice_for,
)
from yield_guardian.llm.usage import QuotaMonitor

log = structlog.get_logger(__name__)

SHANGHAI = timezone(timedelta(hours=8), "Asia/Shanghai")
QUOTA_RESET_LOCAL = time(19, 0)
RECENT_CALLS = 50

EVALUATIONS_NOTE = (
    "Measured by the evaluation harness on fixed task sets; each result names its task set, "
    "the number of tasks and a 95% confidence interval for the success rate."
)


@runtime_checkable
class RouteLog(Protocol):
    """Counts chat questions answered by rules versus by a model."""

    async def record(self, route: RouteKind, intent: str, at: datetime) -> None: ...

    async def counts(self, since: datetime) -> tuple[int, int]:
        """(deterministic, model) answers since ``since``."""
        ...


class InMemoryRouteLog:
    def __init__(self) -> None:
        self.entries: list[tuple[datetime, RouteKind, str]] = []

    async def record(self, route: RouteKind, intent: str, at: datetime) -> None:
        self.entries.append((at, route, intent))

    async def counts(self, since: datetime) -> tuple[int, int]:
        recent = [route for at, route, _ in self.entries if at >= since]
        return recent.count("deterministic"), recent.count("model")


@runtime_checkable
class EvaluationStore(Protocol):
    async def save(self, result: EvaluationResult) -> None: ...

    async def all(self) -> Sequence[EvaluationResult]: ...


class InMemoryEvaluationStore:
    def __init__(self) -> None:
        self.results: list[EvaluationResult] = []

    async def save(self, result: EvaluationResult) -> None:
        self.results.append(result)

    async def all(self) -> Sequence[EvaluationResult]:
        return list(self.results)


def quota_day_start(now: datetime, reset_at: datetime | None = None) -> datetime:
    """Start of the current quota day, in UTC."""
    if reset_at is not None:
        day = timedelta(days=1)
        start = reset_at - day
        while start > now:
            start -= day
        while start + day <= now:
            start += day
        return start.astimezone(UTC)
    local = now.astimezone(SHANGHAI)
    reset_today = datetime.combine(local.date(), QUOTA_RESET_LOCAL, tzinfo=SHANGHAI)
    start = reset_today if local >= reset_today else reset_today - timedelta(days=1)
    return start.astimezone(UTC)


_SYSTEM_RULE_TEXT = {
    SystemRule.ANY: "system messages anywhere, several allowed",
    SystemRule.EXACTLY_ONE_FIRST: "exactly one system message, first",
    SystemRule.AT_MOST_ONE_FIRST: "at most one system message, first",
}


def to_catalog_model(profile: ModelProfile, availability: Availability) -> CatalogModel:
    kind: ContractModelKind = (
        "ocr" if profile.kind is ModelKind.OCR else "vlm" if profile.accepts_images else "llm"
    )
    if profile.is_chat:
        rule = _SYSTEM_RULE_TEXT[profile.system_rule]
        if profile.developer_role is DeveloperRole.MAP_TO_SYSTEM:
            rule += "; developer messages are sent as system"
    else:
        rule = "not applicable (document OCR, no messages)"
    order: tuple[InputType, ...] = ("text", "image", "audio", "document")
    pricing = profile.pricing
    return CatalogModel(
        model_id=profile.id,
        kind=kind,
        context_length=profile.context_length,
        inputs=[m for m in order if m in profile.input_modalities],
        thinks_by_default=profile.thinks_by_default,
        reasoning_efforts=[
            e
            for e in ("none", "minimal", "low", "medium", "high", "xhigh", "max")
            if e in profile.reasoning_efforts
        ],
        system_message_rule=rule,
        json_schema=profile.supports_json_schema,
        tools=profile.supports_tools,
        pricing=(
            ContractPricing(
                input=pricing.input_per_mtok,
                output=pricing.output_per_mtok,
                cache_read=pricing.cache_read_per_mtok,
            )
            if pricing
            else None
        ),
        available=availability is Availability.AVAILABLE,
        profile=profile.source,
    )


def to_contract_assignment(registry: ModelRegistry, role: Role) -> RoleAssignment:
    assignment = registry.assignment(role)
    primary = assignment.primary
    return RoleAssignment(
        role=role.value,
        model_id=primary.model,
        reasoning_effort=primary.reasoning_effort,
        fallbacks=[choice.model for choice in assignment.chain[1:]],
        updated_at=assignment.updated_at,
        updated_by=assignment.updated_by,
    )


class TokenFactoryAdmin:
    def __init__(
        self,
        *,
        registry: ModelRegistry,
        quota: QuotaMonitor,
        call_log: LlmCallLog,
        route_log: RouteLog,
        evaluations: EvaluationStore,
        key_configured: bool,
        list_models: Callable[[], Awaitable[list[CatalogEntry]]] | None = None,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.registry = registry
        self.quota = quota
        self.call_log = call_log
        self.route_log = route_log
        self.evaluation_store = evaluations
        self.key_configured = key_configured
        self._list_models = list_models
        self._wall_clock = wall_clock

    async def sync_catalog(self) -> CatalogSyncReport | None:
        """Read ``GET /v1/models`` and merge it into the profiles (at startup)."""
        if self._list_models is None:
            return None
        try:
            entries = await self._list_models()
        except LlmError as exc:
            log.warning("llm.catalog.sync_failed", error=str(exc))
            return None
        report = self.registry.catalog.sync(entries, self._wall_clock())
        log.info(
            "llm.catalog.synced",
            listed=len(report.listed),
            undocumented=list(report.undocumented),
            withdrawn=list(report.withdrawn),
        )
        return report

    async def catalog(self) -> list[CatalogModel]:
        catalog = self.registry.catalog
        return [
            to_catalog_model(profile, catalog.availability(profile.id))
            for profile in catalog.profiles()
        ]

    async def roles(self) -> list[RoleAssignment]:
        return [to_contract_assignment(self.registry, role) for role in Role]

    async def set_role(
        self, role: RoleName, update: RoleAssignmentUpdate, *, actor: str
    ) -> RoleAssignment:
        """Raises :class:`InvalidAssignmentError` (listing every problem) when invalid."""
        target = Role(role)
        current = self.registry.assignment(target).chain
        by_model = {choice.model: choice for choice in current}
        profile = self.registry.catalog.get(update.model_id)
        if profile is None:
            raise InvalidAssignmentError(target, [f"{update.model_id}: unknown model"])
        primary = choice_for(target, profile, existing=by_model.get(update.model_id))
        if update.reasoning_effort is not None:
            primary = primary.model_copy(update={"reasoning_effort": update.reasoning_effort})
        fallback_ids = (
            [c.model for c in current[1:]] if update.fallbacks is None else update.fallbacks
        )
        chain: list[ModelChoice] = [primary]
        for model_id in fallback_ids:
            if model_id == update.model_id:
                continue
            fallback_profile = self.registry.catalog.get(model_id)
            if fallback_profile is None:
                raise InvalidAssignmentError(target, [f"{model_id}: unknown model"])
            chain.append(choice_for(target, fallback_profile, existing=by_model.get(model_id)))
        await self.registry.assign(target, chain, actor=actor)
        return to_contract_assignment(self.registry, target)

    async def usage(self) -> UsageReport:
        now = self._wall_clock()
        await self.quota.refresh()
        state = self.quota.state()
        since = quota_day_start(now, state.reset_at)
        records = list(await self.call_log.since(since))
        roles = sorted({r.role for r in records})
        models = sorted({r.model for r in records})
        deterministic, model_answers = await self.route_log.counts(since)
        return UsageReport(
            since=since,
            total=total_usage(records),
            by_role=[
                RoleUsage(role=role, usage=total_usage([r for r in records if r.role == role]))
                for role in roles
            ],
            by_model=[
                ModelUsage(
                    model_id=model, usage=total_usage([r for r in records if r.model == model])
                )
                for model in models
            ],
            quota=Quota(
                limit=state.quota,
                used=state.used_points,
                remaining=state.remaining_points,
                resets_at=state.reset_at,
                rpm_limit=state.rpm_limit,
                source="usage_endpoint" if state.snapshot_at is not None else "unknown",
                checked_at=state.snapshot_at,
            ),
            deterministic_answers=deterministic,
            model_answers=model_answers,
            recent=[to_llm_call(r) for r in reversed(records[-RECENT_CALLS:])],
        )

    async def evaluations(self) -> Evaluations:
        results = await self.evaluation_store.all()
        return Evaluations(results=list(results), note=EVALUATIONS_NOTE)

    async def live_calls_available(self) -> bool:
        """A key is configured. Nothing else gates live calls."""
        return self.key_configured
