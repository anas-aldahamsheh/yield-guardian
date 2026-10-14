"""Cache keys: SHA-256 of model, messages, tools and parameters; LRU behaviour."""

from __future__ import annotations

from typing import Any

import pytest

from yield_guardian.llm.cache import CACHE_KEY_VERSION, InMemoryLruCache, cache_key, canonical_json
from yield_guardian.llm.results import ChatResult

BODY: dict[str, Any] = {
    "model": "GLM-5.3-Flash",
    "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
    "max_tokens": 256,
    "reasoning_effort": "low",
    "tools": [{"type": "function", "function": {"name": "get_risk", "parameters": {}}}],
}


def test_key_is_a_sha256_hex_digest_and_stable() -> None:
    key = cache_key(BODY, namespace="ns")
    assert len(key) == 64
    assert int(key, 16) >= 0
    assert key == cache_key(dict(reversed(list(BODY.items()))), namespace="ns")


@pytest.mark.parametrize(
    "change",
    [
        {"model": "DeepSeek-V4-Flash"},
        {"messages": [{"role": "user", "content": "u"}]},
        {"max_tokens": 257},
        {"reasoning_effort": "medium"},
        {"tools": []},
        {"temperature": 0.0},
        {"response_format": {"type": "json_object"}},
    ],
)
def test_any_change_to_model_messages_tools_or_parameters_changes_the_key(
    change: dict[str, Any],
) -> None:
    assert cache_key({**BODY, **change}) != cache_key(BODY)


def test_stream_flag_and_namespace() -> None:
    assert cache_key({**BODY, "stream": True}) == cache_key(BODY)
    assert cache_key(BODY, namespace="a") != cache_key(BODY, namespace="b")


def test_canonical_json_is_compact_sorted_and_refuses_nan() -> None:
    assert canonical_json({"b": 1, "a": "é"}) == '{"a":"é","b":1}'
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})
    assert CACHE_KEY_VERSION in canonical_json({"v": CACHE_KEY_VERSION})


async def test_lru_evicts_the_least_recently_used_entry() -> None:
    cache = InMemoryLruCache(max_entries=2)
    a, b, c = (ChatResult(model="m", content=x) for x in "abc")
    await cache.put("a", a)
    await cache.put("b", b)
    assert await cache.get("a") == a  # "a" is now the most recent
    await cache.put("c", c)
    assert await cache.get("b") is None
    assert await cache.get("a") == a
    assert await cache.get("c") == c
    assert (cache.hits, cache.misses) == (3, 1)
    assert len(cache) == 2


def test_cache_size_must_be_positive() -> None:
    with pytest.raises(ValueError):
        InMemoryLruCache(max_entries=0)
