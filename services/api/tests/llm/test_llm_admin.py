"""Models page backend: catalog, roles, usage report for the quota day, live-call flag."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tests.llm.helpers import NOW, FakeClock
from yield_guardian.contracts.base import Estimate
from yield_guardian.contracts.models import EvaluationResult, RoleAssignmentUpdate, RoleName
from yield_guardian.llm.admin import (
    EVALUATIONS_NOTE,
    InMemoryEvaluationStore,
    InMemoryRouteLog,
    TokenFactoryAdmin,
    quota_day_start,
    to_catalog_model,
)
from yield_guardian.llm.calllog import CallStatus, InMemoryCallLog, LlmCallRecord
from yield_guardian.llm.profiles import (
    DOCUMENTED_PROFILES,
    Availability,
    CatalogEntry,
    ProfileCatalog,
)
from yield_guardian.llm.registry import (
    InMemoryRoleAssignmentStore,
    InvalidAssignmentError,
    ModelRegistry,
)
from yield_guardian.llm.usage import QuotaMonitor


def record(
    at: datetime, role: RoleName, model: str, *, cache_hit: bool = False, status: CallStatus = CallStatus.OK,
    tokens: int | None = 100, points: float | None = 0.001,
) -> LlmCallRecord:  # fmt: skip
    return LlmCallRecord(
        started_at=at,
        role=role,
        model=model,
        status=status,
        cache_hit=cache_hit,
        stream=False,
        tokens_in=tokens,
        tokens_out=tokens,
        tokens_reasoning=0 if tokens is not None else None,
        tokens_cached=0 if tokens is not None else None,
        points=points,
        latency_ms=12.4,
        attempts=1,
    )


def make_admin(
    *, fetch: object = None, key: bool = True, call_log: InMemoryCallLog | None = None
) -> TokenFactoryAdmin:
    async def fetch_usage() -> object:
        return fetch

    registry = ModelRegistry(
        ProfileCatalog(), InMemoryRoleAssignmentStore(), wall_clock=lambda: NOW
    )
    quota = QuotaMonitor(
        fetch_usage if fetch is not None else None, clock=FakeClock(), wall_clock=lambda: NOW
    )
    return TokenFactoryAdmin(
        registry=registry,
        quota=quota,
        call_log=call_log or InMemoryCallLog(),
        route_log=InMemoryRouteLog(),
        evaluations=InMemoryEvaluationStore(),
        key_configured=key,
        wall_clock=lambda: NOW,
    )


@pytest.mark.parametrize(
    ("now", "start"),
    [
        # 12:00 UTC is 20:00 in Shanghai, after the 19:00 reset: the day began at 11:00 UTC.
        (datetime(2026, 10, 14, 12, 0, tzinfo=UTC), datetime(2026, 10, 14, 11, 0, tzinfo=UTC)),
        # 10:00 UTC is 18:00 in Shanghai, before the reset: the day began the previous evening.
        (datetime(2026, 10, 14, 10, 0, tzinfo=UTC), datetime(2026, 10, 13, 11, 0, tzinfo=UTC)),
        (datetime(2026, 10, 14, 11, 0, tzinfo=UTC), datetime(2026, 10, 14, 11, 0, tzinfo=UTC)),
    ],
)
def test_quota_day_starts_at_the_documented_reset(now: datetime, start: datetime) -> None:
    assert quota_day_start(now) == start


def test_quota_day_follows_the_reset_time_the_endpoint_reports() -> None:
    reset_at = datetime(2026, 10, 15, 6, 30, tzinfo=UTC)
    assert quota_day_start(NOW, reset_at) == datetime(2026, 10, 14, 6, 30, tzinfo=UTC)
    stale = reset_at - timedelta(days=3)  # an old reset time still gives today's window
    assert quota_day_start(NOW, stale) == datetime(2026, 10, 14, 6, 30, tzinfo=UTC)


def test_catalog_rows_describe_the_documented_profiles() -> None:
    qwen = to_catalog_model(DOCUMENTED_PROFILES["Qwen3.8-Flash-Next"], Availability.AVAILABLE)
    assert qwen.kind == "vlm"
    assert qwen.inputs == ["text", "image"]
    assert qwen.reasoning_efforts == ["none", "low", "medium", "xhigh"]
    assert qwen.system_message_rule == (
        "exactly one system message, first; developer messages are sent as system"
    )
    assert qwen.pricing is not None
    assert (qwen.pricing.input, qwen.pricing.output, qwen.pricing.cache_read) == (0.15, 0.47, 0.016)
    assert qwen.available
    assert qwen.profile == "documented"
    mineru = to_catalog_model(DOCUMENTED_PROFILES["MinerU2.5-Pro"], Availability.NOT_SYNCED)
    assert mineru.kind == "ocr"
    assert mineru.inputs == ["image", "document"]
    assert mineru.pricing is None
    assert not mineru.available  # not confirmed by a catalog read
    assert mineru.system_message_rule.startswith("not applicable")


async def test_catalog_lists_every_profile_with_its_availability() -> None:
    admin = make_admin()
    admin.registry.catalog.sync([CatalogEntry(id="GLM-5.3-Flash"), CatalogEntry(id="X-9")], NOW)
    rows = {row.model_id: row for row in await admin.catalog()}
    assert rows["GLM-5.3-Flash"].available
    assert not rows["Qwen3.8-27B"].available
    assert rows["X-9"].profile == "catalog_only"


async def test_roles_show_primary_effort_and_fallbacks() -> None:
    roles = {row.role: row for row in await make_admin().roles()}
    assert set(roles) == {"investigator", "writer", "verifier", "chat", "router", "ocr", "vision"}
    assert roles["writer"].model_id == "deepseek-v4.1-flash:free"  # TokenHarbor first
    assert roles["writer"].reasoning_effort is None
    assert roles["writer"].fallbacks == [
        "Qwen3.8-Flash-Next",
        "DeepSeek-V4.1-Flash",
        "MiMo-V2.6-Flash",
    ]
    assert roles["router"].reasoning_effort is None


async def test_set_role_adapts_effort_and_keeps_fallbacks_when_not_given() -> None:
    admin = make_admin()
    row = await admin.set_role(
        "chat", RoleAssignmentUpdate(model_id="DeepSeek-V4-Flash"), actor="engineer@fab"
    )
    assert row.model_id == "DeepSeek-V4-Flash"
    assert row.reasoning_effort == "none"  # the chat role's policy, accepted by DeepSeek
    # DeepSeek-V4-Flash was the last fallback and is now primary; the rest are kept.
    assert row.fallbacks == ["Qwen3.8-Flash-Next"]
    assert row.updated_by == "engineer@fab"
    row = await admin.set_role(
        "chat",
        RoleAssignmentUpdate(
            model_id="GLM-5.3-Flash", reasoning_effort="medium", fallbacks=["DeepSeek-V4-Flash"]
        ),
        actor="engineer@fab",
    )
    assert (row.model_id, row.reasoning_effort, row.fallbacks) == (
        "GLM-5.3-Flash",
        "medium",
        ["DeepSeek-V4-Flash"],
    )


@pytest.mark.parametrize(
    ("update", "problem"),
    [
        (RoleAssignmentUpdate(model_id="GLM-5.3-Flash", reasoning_effort="xhigh"), "xhigh"),
        (RoleAssignmentUpdate(model_id="Nope-1"), "unknown model"),
        (RoleAssignmentUpdate(model_id="GLM-5.3-Flash", fallbacks=["Nope-2"]), "unknown model"),
    ],
)
async def test_set_role_refuses_invalid_assignments(
    update: RoleAssignmentUpdate, problem: str
) -> None:
    with pytest.raises(InvalidAssignmentError) as caught:
        await make_admin().set_role("chat", update, actor="engineer@fab")
    assert any(problem in p for p in caught.value.problems)


async def test_usage_report_covers_the_quota_day_only() -> None:
    log = InMemoryCallLog()
    yesterday = NOW - timedelta(days=1)
    log.records = [
        record(yesterday, "chat", "Qwen3.8-Flash-Next"),
        record(NOW - timedelta(minutes=30), "writer", "MiMo-V2.6-Flash", points=0.002),
        record(NOW - timedelta(minutes=20), "writer", "MiMo-V2.6-Flash", cache_hit=True, tokens=0, points=0.0),
        record(NOW - timedelta(minutes=10), "verifier", "GLM-5.3-Flash", tokens=None, points=None),
        record(NOW - timedelta(minutes=5), "chat", "Qwen3.8-Flash-Next", status=CallStatus.REFUSED_PROFILE, tokens=0, points=0.0),
    ]  # fmt: skip
    admin = make_admin(
        fetch={"quota": 1.0, "used": 0.2, "remaining": 0.8, "reset_at": "2026-10-15T11:00:00Z"},
        call_log=log,
    )
    await admin.route_log.record("deterministic", "count_alarms", NOW - timedelta(minutes=1))
    await admin.route_log.record("model", "explain_unit", NOW - timedelta(minutes=1))
    await admin.route_log.record("deterministic", "count_alarms", yesterday)
    report = await admin.usage()
    assert report.since == datetime(2026, 10, 14, 11, 0, tzinfo=UTC)
    # Sent requests only: the cache hit and the refused request never reached the endpoint.
    assert report.total.requests == 2
    assert report.total.cache_hits == 1
    assert report.total.tokens_in == 100  # the unknown usage counts as 0 (see calllog)
    assert report.total.points == pytest.approx(0.002)
    assert [r.role for r in report.by_role] == ["chat", "verifier", "writer"]
    assert [m.model_id for m in report.by_model] == [
        "GLM-5.3-Flash",
        "MiMo-V2.6-Flash",
        "Qwen3.8-Flash-Next",
    ]
    assert (report.deterministic_answers, report.model_answers) == (1, 1)
    assert [c.status for c in report.recent] == ["refused", "ok", "cached", "ok"]
    assert report.recent[1].error == "usage not reported by the endpoint"
    assert report.quota.source == "usage_endpoint"
    assert (report.quota.limit, report.quota.used, report.quota.remaining) == (1.0, 0.2, 0.8)
    assert report.quota.checked_at == NOW


async def test_usage_without_a_reading_says_the_quota_is_unknown() -> None:
    report = await make_admin(key=False).usage()
    assert report.quota.source == "unknown"
    assert report.quota.remaining is None
    assert report.total.requests == 0


async def test_live_calls_need_only_a_key() -> None:
    assert await make_admin(key=True).live_calls_available()
    assert not await make_admin(key=False).live_calls_available()


async def test_evaluations_are_returned_with_their_note() -> None:
    admin = make_admin()
    result = EvaluationResult(
        role="router",
        model_id="MiniCPM5-2B",
        task_set="router-v1 (synthetic test value)",
        tasks=10,
        success_rate=Estimate(value=0.9, ci_low=0.6, ci_high=0.98, n=10),
        violations=0,
        latency_ms_p50=None,
        tokens_in=0,
        tokens_out=0,
        points=0.0,
        run_at=NOW,
    )
    await admin.evaluation_store.save(result)
    evaluations = await admin.evaluations()
    assert evaluations.results == [result]
    assert evaluations.note == EVALUATIONS_NOTE
