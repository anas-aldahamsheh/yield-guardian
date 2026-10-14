"""Retry policy: only 429, 502 and 503, at most 3 retries, full jitter, Retry-After honoured."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest

from yield_guardian.llm.retry import RetryPolicy, parse_retry_after


@pytest.mark.parametrize(
    ("value", "seconds"),
    [("1", 1.0), (" 60 ", 60.0), ("0", 0.0), ("2.5", 2.5)],
)
def test_retry_after_delta_seconds(value: str, seconds: float) -> None:
    assert parse_retry_after(value) == seconds


@pytest.mark.parametrize("value", [None, "", "   ", "-1", "inf", "nan", "soon", "1e999"])
def test_retry_after_unusable_values_are_none(value: str | None) -> None:
    assert parse_retry_after(value) is None


def test_retry_after_http_date_is_relative_to_now() -> None:
    now = datetime(2026, 10, 14, 12, 0, 0, tzinfo=UTC)
    later = (now + timedelta(seconds=90)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    assert parse_retry_after(later, now=now) == pytest.approx(90.0)
    earlier = (now - timedelta(seconds=90)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    assert parse_retry_after(earlier, now=now) == 0.0


@pytest.mark.parametrize("status", [429, 502, 503])
def test_busy_statuses_are_retried_three_times_at_most(status: int) -> None:
    policy = RetryPolicy()
    assert [policy.should_retry(status, done) for done in range(5)] == [
        True,
        True,
        True,
        False,
        False,
    ]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 408, 422, 500, 504])
def test_other_statuses_are_never_retried(status: int) -> None:
    assert not RetryPolicy().should_retry(status, 0)


def test_full_jitter_stays_within_the_exponential_ceiling() -> None:
    policy = RetryPolicy(base_delay=1.0, max_backoff=30.0)
    rng = random.Random(1)
    for retries_done, ceiling in [(0, 1.0), (1, 2.0), (2, 4.0), (5, 30.0), (9, 30.0)]:
        delays = [policy.delay(retries_done, None, rng) for _ in range(200)]
        assert all(d is not None and 0.0 <= d <= ceiling for d in delays)
        # Full jitter spreads the delays over the whole interval.
        assert min(d for d in delays if d is not None) < ceiling * 0.1
        assert max(d for d in delays if d is not None) > ceiling * 0.9


def test_a_retry_never_comes_sooner_than_retry_after() -> None:
    policy = RetryPolicy()
    rng = random.Random(2)
    for _ in range(100):
        delay = policy.delay(0, 5.0, rng)
        assert delay == 5.0  # the jitter ceiling (1 s) is below Retry-After
    long_backoff = [policy.delay(4, 1.0, rng) for _ in range(100)]
    assert all(d is not None and d >= 1.0 for d in long_backoff)


def test_a_retry_after_beyond_the_wait_bound_stops_waiting() -> None:
    policy = RetryPolicy(max_retry_after=120.0)
    rng = random.Random(3)
    assert policy.delay(0, 120.0, rng) == 120.0
    assert policy.delay(0, 120.5, rng) is None
    assert policy.delay(0, 9 * 3600.0, rng) is None
