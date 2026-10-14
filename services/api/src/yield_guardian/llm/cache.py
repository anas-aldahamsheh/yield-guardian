"""Response cache keyed by SHA-256 of model, messages, tools and parameters (PLAN 7.2).

The key is computed from the *built* request body (after the profile rules are applied),
so two requests that send the same bytes to the same model share an entry. ``stream`` is
left out: a streamed and a non-streamed request for the same completion are the same
question. A namespace (the base URL) keeps entries of different endpoints apart, and a
version tag lets a change of canonical form invalidate old entries.

The in-memory LRU serves tests and single-process runs; the database layer implements the
same :class:`ResponseCache` protocol for production.
"""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from yield_guardian.llm.results import ChatResult

CACHE_KEY_VERSION = "yg-llm-cache-v1"
_EXCLUDED_PARAMS = frozenset({"model", "messages", "tools", "stream"})


def canonical_json(value: Any) -> str:
    """Deterministic JSON: sorted keys, no whitespace, UTF-8 text, NaN refused."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def cache_key(body: Mapping[str, Any], *, namespace: str = "") -> str:
    material = {
        "version": CACHE_KEY_VERSION,
        "namespace": namespace,
        "model": body.get("model"),
        "messages": body.get("messages"),
        "tools": body.get("tools"),
        "params": {k: v for k, v in body.items() if k not in _EXCLUDED_PARAMS},
    }
    return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()


@runtime_checkable
class ResponseCache(Protocol):
    async def get(self, key: str) -> ChatResult | None: ...

    async def put(self, key: str, result: ChatResult) -> None: ...


class InMemoryLruCache:
    """Least-recently-used cache of complete results."""

    def __init__(self, max_entries: int = 512) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self.max_entries = max_entries
        self._entries: OrderedDict[str, ChatResult] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def __len__(self) -> int:
        return len(self._entries)

    async def get(self, key: str) -> ChatResult | None:
        result = self._entries.get(key)
        if result is None:
            self.misses += 1
            return None
        self._entries.move_to_end(key)
        self.hits += 1
        return result

    async def put(self, key: str, result: ChatResult) -> None:
        self._entries[key] = result
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)
