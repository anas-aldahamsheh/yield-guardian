"""Budget guard: keep the shared daily quota for essential calls (PLAN section 7.2).

Sources, in order of authority:

1. ``GET /v1/usage`` ("quota, used, remaining, reset time, RPM limit and recent requests"),
   fetched at most once per ``ttl`` seconds (60 by default). Its field names are not
   documented, so :func:`parse_usage_snapshot` looks for the usual names and keeps the raw
   payload for inspection.
2. Points this process spent since the last snapshot (estimated from usage and pricing), so
   the guard does not wait a minute to notice its own spend.
3. ``X-RateLimit-*`` headers. Their names are not documented either: every one seen is
   recorded verbatim; only the common request-rate names are interpreted.

Below ``threshold`` (30%) of the daily budget, non-essential calls are refused. When the
remaining budget cannot be determined, non-essential calls are refused too unless the guard
is configured with ``unknown_policy="allow"`` (for example against a fab's own endpoint,
which has no quota). Essential calls are refused only when a fresh server snapshot says the
budget is exhausted.
"""

from __future__ import annotations

import asyncio
import math
import re
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field

from yield_guardian.llm.errors import BudgetRefusedError, LlmError
from yield_guardian.llm.limits import Clock

log = structlog.get_logger(__name__)

UnknownPolicy = Literal["refuse", "allow"]

DEFAULT_THRESHOLD = 0.30
DEFAULT_TTL_SECONDS = 60.0
MAX_HEADER_PAUSE_SECONDS = 60.0

_QUOTA_KEYS = ("quota", "daily_quota", "spend_cap", "limit", "cap", "budget", "total")
_USED_KEYS = ("used", "spent", "consumed", "usage")
_REMAINING_KEYS = ("remaining", "left", "balance", "available")
_RESET_KEYS = ("reset_at", "resets_at", "reset_time", "next_reset", "reset")
_RPM_KEYS = ("rpm_limit", "requests_per_minute", "rpm")


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None


def _datetime(value: object) -> datetime | None:
    if isinstance(value, str):
        text = value.strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            number = _number(text)
            return _datetime(number) if number is not None else None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    number = _number(value)
    if number is not None and number > 1e9:
        seconds = number / 1000.0 if number > 1e12 else number
        return datetime.fromtimestamp(seconds, UTC)
    return None


_RATE_PATH_MARKERS = ("rpm", "rate", "request", "minute", "concurren", "token")


@dataclass(frozen=True, slots=True)
class _Leaf:
    depth: int
    path: tuple[str, ...]
    value: object

    @property
    def key(self) -> str:
        return self.path[-1]

    @property
    def about_rate(self) -> bool:
        """True when an enclosing object is about request rates or tokens, not spend."""
        return any(marker in part for part in self.path[:-1] for marker in _RATE_PATH_MARKERS)


def _leaves(payload: Mapping[str, Any], path: tuple[str, ...] = ()) -> list[_Leaf]:
    """Scalar leaves of nested objects (two levels deep). Lists are not entered, so
    per-request records under ``recent`` are never mistaken for totals."""
    out: list[_Leaf] = []
    for key, value in payload.items():
        here = (*path, str(key).lower())
        if isinstance(value, Mapping):
            if len(path) < 2:
                out.extend(_leaves(value, here))
        elif not isinstance(value, list):
            out.append(_Leaf(depth=len(path), path=here, value=value))
    return out


def _find(
    leaves: list[_Leaf],
    keys: tuple[str, ...],
    convert: Callable[[object], Any],
    *,
    spend_only: bool,
) -> Any:
    """First convertible leaf named like ``keys`` (in preference order), shallowest first."""
    ordered = sorted(leaves, key=lambda leaf: leaf.depth)
    for wanted in keys:
        for leaf in ordered:
            if leaf.key != wanted or (spend_only and leaf.about_rate):
                continue
            converted = convert(leaf.value)
            if converted is not None:
                return converted
    return None


class UsageSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    quota: float | None = None
    used: float | None = None
    remaining: float | None = None
    reset_at: datetime | None = None
    rpm_limit: int | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @property
    def remaining_points(self) -> float | None:
        if self.remaining is not None:
            return self.remaining
        if self.quota is not None and self.used is not None:
            return self.quota - self.used
        return None

    @property
    def remaining_fraction(self) -> float | None:
        remaining = self.remaining_points
        if self.quota is None or self.quota <= 0 or remaining is None:
            return None
        return min(1.0, max(0.0, remaining / self.quota))


def parse_usage_snapshot(payload: object) -> UsageSnapshot:
    if not isinstance(payload, Mapping):
        return UsageSnapshot()
    leaves = _leaves(payload)
    rpm = _find(leaves, _RPM_KEYS, _number, spend_only=False)
    return UsageSnapshot(
        quota=_find(leaves, _QUOTA_KEYS, _number, spend_only=True),
        used=_find(leaves, _USED_KEYS, _number, spend_only=True),
        remaining=_find(leaves, _REMAINING_KEYS, _number, spend_only=True),
        reset_at=_find(leaves, _RESET_KEYS, _datetime, spend_only=True),
        rpm_limit=int(rpm) if rpm is not None else None,
        raw=dict(payload),
    )


_DURATION = re.compile(r"(?P<value>\d+(?:\.\d+)?)(?P<unit>ms|s|m|h)")


def parse_reset_seconds(value: str, *, now: datetime | None = None) -> float | None:
    """Seconds until a rate-limit reset: ``"60"``, ``"1.5s"``, ``"6m0s"``, ``"500ms"`` or an
    epoch timestamp."""
    text = value.strip().lower()
    number = _number(text)
    if number is not None:
        if number > 1e9:
            reset = _datetime(number)
            reference = now or datetime.now(UTC)
            return max(0.0, (reset - reference).total_seconds()) if reset else None
        return number if number >= 0 else None
    total = 0.0
    position = 0
    for match in _DURATION.finditer(text):
        if match.start() != position:
            return None
        amount = float(match.group("value"))
        total += amount * {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}[match.group("unit")]
        position = match.end()
    return total if position == len(text) and position > 0 else None


@dataclass
class HeaderObservation:
    seen: dict[str, str] = field(default_factory=dict)
    names_ever_seen: set[str] = field(default_factory=set)
    observed_at: datetime | None = None
    requests_limit: float | None = None
    requests_remaining: float | None = None
    requests_reset_seconds: float | None = None


class BudgetState(BaseModel):
    """What the Models page shows about the budget."""

    model_config = ConfigDict(frozen=True)

    threshold: float
    remaining_fraction: float | None
    quota: float | None
    remaining_points: float | None
    local_spend_since_snapshot: float
    reset_at: datetime | None
    snapshot_at: datetime | None
    last_error: str | None
    headers_seen: dict[str, str]
    header_names_ever_seen: list[str]


class BudgetGuard:
    def __init__(
        self,
        fetch_usage: Callable[[], Awaitable[object]] | None,
        *,
        threshold: float = DEFAULT_THRESHOLD,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        unknown_policy: UnknownPolicy = "refuse",
        clock: Clock = time.monotonic,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be within [0, 1]")
        self._fetch = fetch_usage
        self.threshold = threshold
        self.ttl_seconds = ttl_seconds
        self.unknown_policy: UnknownPolicy = unknown_policy
        self._clock = clock
        self._wall_clock = wall_clock
        self._snapshot: UsageSnapshot | None = None
        self._snapshot_at: datetime | None = None
        self._fetched_monotonic: float | None = None
        self._attempted_monotonic: float | None = None
        self._local_spend = 0.0
        self._last_error: str | None = None
        self._lock = asyncio.Lock()
        self.headers = HeaderObservation()

    async def refresh(self, *, force: bool = False) -> UsageSnapshot | None:
        """Fetch ``/v1/usage`` unless the last attempt is younger than the TTL."""
        if self._fetch is None:
            return None
        async with self._lock:
            now = self._clock()
            if (
                not force
                and self._attempted_monotonic is not None
                and now - self._attempted_monotonic < self.ttl_seconds
            ):
                return self._snapshot
            self._attempted_monotonic = now
            try:
                payload = await self._fetch()
            except LlmError as exc:
                self._last_error = f"usage endpoint failed: {exc}"
                log.warning("llm.budget.usage_failed", error=str(exc))
                return self._snapshot
            snapshot = parse_usage_snapshot(payload)
            self._snapshot = snapshot
            self._snapshot_at = self._wall_clock()
            self._fetched_monotonic = now
            self._local_spend = 0.0
            self._last_error = (
                None
                if snapshot.remaining_fraction is not None
                else "usage payload has no recognisable quota and remaining fields"
            )
            return snapshot

    def remaining_fraction(self) -> float | None:
        snapshot = self._snapshot
        if snapshot is None or snapshot.quota is None or snapshot.quota <= 0:
            return None
        remaining = snapshot.remaining_points
        if remaining is None:
            return None
        return min(1.0, max(0.0, (remaining - self._local_spend) / snapshot.quota))

    async def check(self, *, essential: bool) -> float | None:
        """Raise :class:`BudgetRefusedError` if the call may not be sent; return the remaining
        fraction used for the decision (None when unknown)."""
        await self.refresh()
        fraction = self.remaining_fraction()
        server_remaining = self._snapshot.remaining_points if self._snapshot else None
        if server_remaining is not None and server_remaining <= 0:
            raise BudgetRefusedError("the daily budget is exhausted (usage endpoint)", 0.0)
        if essential:
            return fraction
        if fraction is None:
            if self.unknown_policy == "allow":
                return None
            raise BudgetRefusedError(
                "the remaining daily budget is unknown, so non-essential calls are refused"
                + (f" ({self._last_error})" if self._last_error else ""),
                None,
            )
        if fraction < self.threshold:
            raise BudgetRefusedError(
                f"{fraction:.0%} of the daily budget remains, below the {self.threshold:.0%} "
                "reserved for essential calls",
                fraction,
            )
        return fraction

    def record_spend(self, points: float | None) -> None:
        if points is not None and points > 0:
            self._local_spend += points

    def observe_headers(self, headers: Mapping[str, str]) -> float | None:
        """Record every ``X-RateLimit-*`` header. Returns a pause in seconds (capped at 60)
        when the headers say no request is left in the current window."""
        seen = {k.lower(): v for k, v in headers.items() if k.lower().startswith("x-ratelimit-")}
        if not seen:
            return None
        obs = self.headers
        obs.seen = seen
        obs.names_ever_seen.update(seen)
        obs.observed_at = self._wall_clock()
        limit = seen.get("x-ratelimit-limit-requests", seen.get("x-ratelimit-limit"))
        remaining = seen.get("x-ratelimit-remaining-requests", seen.get("x-ratelimit-remaining"))
        reset = seen.get("x-ratelimit-reset-requests", seen.get("x-ratelimit-reset"))
        obs.requests_limit = _number(limit) if limit is not None else None
        obs.requests_remaining = _number(remaining) if remaining is not None else None
        obs.requests_reset_seconds = parse_reset_seconds(reset) if reset is not None else None
        if obs.requests_remaining is not None and obs.requests_remaining <= 0:
            wait = obs.requests_reset_seconds
            return min(wait, MAX_HEADER_PAUSE_SECONDS) if wait is not None else None
        return None

    def state(self) -> BudgetState:
        snapshot = self._snapshot
        return BudgetState(
            threshold=self.threshold,
            remaining_fraction=self.remaining_fraction(),
            quota=snapshot.quota if snapshot else None,
            remaining_points=(
                snapshot.remaining_points - self._local_spend
                if snapshot and snapshot.remaining_points is not None
                else None
            ),
            local_spend_since_snapshot=self._local_spend,
            reset_at=snapshot.reset_at if snapshot else None,
            snapshot_at=self._snapshot_at,
            last_error=self._last_error,
            headers_seen=dict(self.headers.seen),
            header_names_ever_seen=sorted(self.headers.names_ever_seen),
        )
