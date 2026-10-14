"""Quota display: /v1/usage parsing, X-RateLimit headers, local spend. Never a limiter."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tests.llm.helpers import NOW, FakeClock, load_cassette
from yield_guardian.llm.errors import TransportError
from yield_guardian.llm.usage import (
    QuotaMonitor,
    parse_reset_seconds,
    parse_usage_snapshot,
)


def usage_fixture() -> object:
    return load_cassette("catalog_and_usage").interactions[1].response.json_body


def test_flat_usage_payload_is_read_and_recent_records_are_ignored() -> None:
    snapshot = parse_usage_snapshot(usage_fixture())
    assert snapshot.quota == 1.0
    assert snapshot.used == 0.25
    assert snapshot.remaining == 0.75  # not the 0.1 inside the 'recent' list
    assert snapshot.reset_at == datetime(2026, 10, 14, 11, 0, tzinfo=UTC)
    assert snapshot.rpm_limit == 20
    assert snapshot.raw["recent"][0]["model"] == "DeepSeek-V4-Flash"


def test_nested_payload_prefers_spend_fields_over_rate_fields() -> None:
    payload = {
        "rate_limits": {"limit": 20, "remaining": 3, "reset": "60"},
        "spend": {"daily_quota": "1.0", "spent": 0.4, "resets_at": 1792058400},
    }
    snapshot = parse_usage_snapshot(payload)
    assert snapshot.quota == 1.0
    assert snapshot.used == 0.4
    assert snapshot.remaining is None
    assert snapshot.remaining_points == pytest.approx(0.6)
    assert snapshot.reset_at == datetime.fromtimestamp(1792058400, UTC)


def test_derived_values_when_one_field_is_missing() -> None:
    snapshot = parse_usage_snapshot({"limit": 2, "remaining": 0.5})
    assert snapshot.used_points == 1.5
    assert parse_usage_snapshot({"used": 1}).remaining_points is None
    assert parse_usage_snapshot(["not", "a", "mapping"]).quota is None


@pytest.mark.parametrize(
    ("value", "seconds"),
    [("60", 60.0), ("1.5s", 1.5), ("6m0s", 360.0), ("500ms", 0.5), ("1h", 3600.0)],
)
def test_reset_header_durations(value: str, seconds: float) -> None:
    assert parse_reset_seconds(value) == pytest.approx(seconds)


@pytest.mark.parametrize("value", ["", "soon", "-5", "5x", "s"])
def test_unparseable_reset_headers_are_none(value: str) -> None:
    assert parse_reset_seconds(value) is None


def test_epoch_reset_header_is_relative_to_now() -> None:
    now = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
    assert parse_reset_seconds(str(int(now.timestamp()) + 30), now=now) == pytest.approx(30.0)


async def test_refresh_reads_the_endpoint_once_per_ttl_and_tracks_local_spend() -> None:
    calls = 0

    async def fetch() -> object:
        nonlocal calls
        calls += 1
        return {"quota": 1.0, "used": 0.25, "remaining": 0.75}

    clock = FakeClock()
    monitor = QuotaMonitor(fetch, ttl_seconds=60, clock=clock, wall_clock=lambda: NOW)
    await monitor.refresh()
    await monitor.refresh()
    assert calls == 1
    monitor.record_spend(0.05)
    monitor.record_spend(None)
    monitor.record_spend(-1.0)
    state = monitor.state()
    assert state.used_points == pytest.approx(0.30)
    assert state.remaining_points == pytest.approx(0.70)
    assert state.local_spend_since_snapshot == pytest.approx(0.05)
    assert state.snapshot_at == NOW
    assert state.last_error is None
    clock.advance(61)
    await monitor.refresh()
    assert calls == 2
    assert monitor.state().local_spend_since_snapshot == 0.0  # the new reading includes it
    await monitor.refresh(force=True)
    assert calls == 3


async def test_a_failed_reading_keeps_the_last_snapshot_and_reports_the_error() -> None:
    answers: list[object] = [{"quota": 1.0, "remaining": 0.5}]

    async def fetch() -> object:
        if answers:
            return answers.pop()
        raise TransportError("usage endpoint unreachable")

    monitor = QuotaMonitor(fetch, ttl_seconds=0, clock=FakeClock(), wall_clock=lambda: NOW)
    await monitor.refresh()
    await monitor.refresh()
    state = monitor.state()
    assert state.remaining_points == 0.5
    assert state.last_error is not None
    assert "unreachable" in state.last_error


async def test_an_unrecognisable_payload_is_reported_not_guessed() -> None:
    async def fetch() -> object:
        return {"something": "else"}

    monitor = QuotaMonitor(fetch, clock=FakeClock(), wall_clock=lambda: NOW)
    await monitor.refresh()
    state = monitor.state()
    assert state.quota is None
    assert state.remaining_points is None
    assert state.last_error == "usage payload has no recognisable quota and remaining fields"


async def test_without_a_key_nothing_is_fetched() -> None:
    monitor = QuotaMonitor(None, clock=FakeClock(), wall_clock=lambda: NOW)
    assert await monitor.refresh() is None
    assert monitor.state().snapshot_at is None


def test_rate_limit_headers_are_recorded_verbatim_for_display() -> None:
    monitor = QuotaMonitor(None, clock=FakeClock(), wall_clock=lambda: NOW)
    monitor.observe_headers(
        {
            "X-RateLimit-Limit-Requests": "20",
            "X-RateLimit-Remaining-Requests": "0",
            "X-RateLimit-Reset-Requests": "6m0s",
            "X-RateLimit-Vendor-Specific": "abc",
            "content-type": "application/json",
        }
    )
    state = monitor.state()
    assert state.headers_seen == {
        "x-ratelimit-limit-requests": "20",
        "x-ratelimit-remaining-requests": "0",
        "x-ratelimit-reset-requests": "6m0s",
        "x-ratelimit-vendor-specific": "abc",
    }
    assert state.requests_remaining == 0.0
    assert monitor.headers.requests_reset_seconds == 360.0
    monitor.observe_headers({"content-type": "text/plain"})  # no rate headers: kept as is
    assert monitor.state().requests_remaining == 0.0
    monitor.observe_headers({"x-ratelimit-remaining": "7"})
    assert monitor.state().requests_remaining == 7.0
    assert "x-ratelimit-vendor-specific" in monitor.state().header_names_ever_seen


def test_the_monitor_offers_no_way_to_refuse_or_delay_a_call() -> None:
    """Owner decision: quota readings are for display only."""
    public = {name for name in dir(QuotaMonitor) if not name.startswith("_")}
    assert public == {"refresh", "record_spend", "observe_headers", "state"}
