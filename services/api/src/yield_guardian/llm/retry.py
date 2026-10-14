"""Retry policy for a busy or unreachable server (PLAN section 7.2, owner decision of 2026-10-14).

The product sets no request limits of its own: no client-side rate limiter, no cap on
requests in flight, no refusal to protect the quota. When the AMD server answers 429, 502 or
503, the request is retried, at most 3 times, with exponential backoff and full jitter (delay
drawn uniformly from ``[0, min(cap, base * 2**attempt)]``), and never sooner than the server's
``Retry-After``. That is error handling of the server's answer, not a limiter.

One bound remains, and it only concerns waiting: when ``Retry-After`` asks for longer than
``max_retry_after`` (120 s by default), the client stops waiting and returns the server's
error with its ``retry_after`` value, instead of holding the caller's request open (a spend
cap answered with "retry in 9 hours" must not hang an HTTP request for 9 hours).
"""

from __future__ import annotations

import math
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]


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
        """Delay before retry number ``retries_done + 1``, or None to stop waiting because the
        server asked for a longer wait than ``max_retry_after``."""
        ceiling = min(self.max_backoff, self.base_delay * (2.0**retries_done))
        backoff = rng.uniform(0.0, ceiling)
        if retry_after is None:
            return backoff
        if retry_after > self.max_retry_after:
            return None
        return max(retry_after, backoff)
