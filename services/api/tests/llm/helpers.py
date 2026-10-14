"""Test helpers for the language-model layer: no real sleeping, fixed jitter, offline stack.

The API key below is a placeholder of the documented format, not a key.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx

from yield_guardian.llm.cache import InMemoryLruCache
from yield_guardian.llm.calllog import InMemoryCallLog
from yield_guardian.llm.cassette import Cassette, CassettePlayer
from yield_guardian.llm.client import DEFAULT_BASE_URL, TokenFactoryClient
from yield_guardian.llm.gateway import LlmGateway
from yield_guardian.llm.profiles import ProfileCatalog
from yield_guardian.llm.registry import InMemoryRoleAssignmentStore, ModelRegistry
from yield_guardian.llm.retry import RetryPolicy
from yield_guardian.llm.usage import QuotaMonitor

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "llm"
PLACEHOLDER_KEY = "rc-" + "0" * 48
HOST = httpx.URL(DEFAULT_BASE_URL).host
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


def load_cassette(name: str) -> Cassette:
    return Cassette.load(FIXTURES / f"{name}.json")


def mount(router: respx.Router, name: str) -> CassettePlayer:
    """Serve the named cassette for every request to the Token Factory host."""
    player = CassettePlayer(load_cassette(name))
    router.route(host=HOST).mock(side_effect=player)
    return player


@dataclass
class SleepRecorder:
    """Stands in for asyncio.sleep: records the delays, never waits."""

    delays: list[float] = field(default_factory=list)

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


@dataclass
class FakeClock:
    now: float = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_client(
    *,
    sleep: SleepRecorder | None = None,
    retry: RetryPolicy | None = None,
    api_key: str | None = PLACEHOLDER_KEY,
    seed: int = 7,
) -> TokenFactoryClient:
    return TokenFactoryClient(
        api_key=api_key,
        sleep=sleep or SleepRecorder(),
        rng=random.Random(seed),
        retry=retry,
    )


@dataclass
class Stack:
    client: TokenFactoryClient
    catalog: ProfileCatalog
    registry: ModelRegistry
    quota: QuotaMonitor
    cache: InMemoryLruCache
    call_log: InMemoryCallLog
    gateway: LlmGateway
    sleep: SleepRecorder
    clock: FakeClock


def make_stack(*, seed: int = 7) -> Stack:
    """An offline gateway with in-memory stores and the default role chains."""
    sleep = SleepRecorder()
    clock = FakeClock()
    client = make_client(sleep=sleep, seed=seed)
    catalog = ProfileCatalog()
    registry = ModelRegistry(catalog, InMemoryRoleAssignmentStore(), wall_clock=lambda: NOW)
    quota = QuotaMonitor(client.get_usage, clock=clock, wall_clock=lambda: NOW)
    cache = InMemoryLruCache()
    call_log = InMemoryCallLog()
    gateway = LlmGateway(
        client=client,
        registry=registry,
        cache=cache,
        call_log=call_log,
        quota=quota,
        clock=clock,
        wall_clock=lambda: NOW,
    )
    return Stack(client, catalog, registry, quota, cache, call_log, gateway, sleep, clock)
