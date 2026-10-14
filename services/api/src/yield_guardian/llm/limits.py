"""Client-side rate limiting and the retry policy (PLAN section 7.2).

Token Factory allows 20 requests per minute per account (60 s sliding window) and 8
concurrent requests per key. The client stays below both: a token bucket refilled at 15
requests per minute and at most 4 requests in flight.

A token bucket of capacity C refilled at r per second admits at most ``C + r * T`` requests in
any window of T seconds. With r = 15/60 and T = 60 that is C + 15, so the burst capacity is 4:
at most 19 requests in any 60-second window, under the gateway's 20. (A capacity of 15 would
admit 30.) ``tests/llm/test_llm_limits.py`` checks this bound on a simulated clock.

Retries happen only on 429, 502 and 503, at most 3 times, with exponential backoff and full
jitter (delay drawn uniformly from ``[0, min(cap, base * 2**attempt)]``), and never sooner than
the server's ``Retry-After``. A ``Retry-After`` longer than ``max_retry_after`` is not waited
for: the error goes back to the caller, who can serve a recorded run instead of blocking.
"""

from __future__ import annotations

import asyncio
import math
import random
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]

DEFAULT_RPM = 15
DEFAULT_BURST = 4
DEFAULT_MAX_IN_FLIGHT = 4


class TokenBucket:
    """Async token bucket. Waiters are served first come, first served."""

    def __init__(
        self,
        rate_per_minute: float = DEFAULT_RPM,
        capacity: int = DEFAULT_BURST,
        *,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        if rate_per_minute <= 0 or capacity < 1:
            raise ValueError("rate_per_minute must be > 0 and capacity >= 1")
        self.rate_per_second = rate_per_minute / 60.0
        self.capacity = float(capacity)
        self._tokens = float(capacity)
        self._clock = clock
        self._sleep = sleep
        self._updated = clock()
        self._paused_until = -math.inf
        self._lock = asyncio.Lock()

    def max_in_window(self, seconds: float) -> float:
        """Upper bound on admissions in any window of ``seconds``."""
        return self.capacity + self.rate_per_second * seconds

    def pause_until(self, monotonic_deadline: float) -> None:
        """Admit nothing before ``monotonic_deadline`` (used after a 429 with Retry-After)."""
        self._paused_until = max(self._paused_until, monotonic_deadline)

    def _refill(self, now: float) -> None:
        elapsed = max(0.0, now - self._updated)
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate_per_second)
        self._updated = now

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = self._clock()
                if now < self._paused_until:
                    await self._sleep(self._paused_until - now)
                    continue
                self._refill(now)
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                await self._sleep((1.0 - self._tokens) / self.rate_per_second)


class RateLimiter:
    """Concurrency cap plus token bucket. The slot is taken first, then the token, so the
    request is sent right after its token is granted and the bucket bound holds for send
    times, not just for grant times."""

    def __init__(
        self, bucket: TokenBucket | None = None, *, max_in_flight: int = DEFAULT_MAX_IN_FLIGHT
    ) -> None:
        if max_in_flight < 1:
            raise ValueError("max_in_flight must be >= 1")
        self.bucket = bucket or TokenBucket()
        self.max_in_flight = max_in_flight
        self._slots = asyncio.Semaphore(max_in_flight)
        self._in_flight = 0

    @property
    def in_flight(self) -> int:
        return self._in_flight

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        async with self._slots:
            await self.bucket.acquire()
            self._in_flight += 1
            try:
                yield
            finally:
                self._in_flight -= 1


def parse_retry_after(value: str | None, *, now: datetime | None = None) -> float | None:
    """Seconds to wait from a ``Retry-After`` header: delta-seconds or an HTTP-date
    (RFC 9110, section 10.2.3). Returns None when absent or unparseable."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        seconds = float(text)
    except ValueError:
        seconds = math.nan
    if not math.isnan(seconds):
        return seconds if seconds >= 0 and math.isfinite(seconds) else None
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    reference = now or datetime.now(UTC)
    return max(0.0, (when - reference).total_seconds())


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 3
    base_delay: float = 1.0
    max_backoff: float = 30.0
    max_retry_after: float = 120.0
    retry_statuses: frozenset[int] = field(default_factory=lambda: frozenset({429, 502, 503}))

    def should_retry(self, status: int, retries_done: int) -> bool:
        return status in self.retry_statuses and retries_done < self.max_retries

    def delay(
        self, retries_done: int, retry_after: float | None, rng: random.Random
    ) -> float | None:
        """Delay before retry number ``retries_done + 1``, or None to give up because the
        server asked for a longer wait than ``max_retry_after``."""
        ceiling = min(self.max_backoff, self.base_delay * (2.0**retries_done))
        backoff = rng.uniform(0.0, ceiling)
        if retry_after is None:
            return backoff
        if retry_after > self.max_retry_after:
            return None
        return max(retry_after, backoff)
