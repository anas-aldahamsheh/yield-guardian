"""Call records in the contract: unknown usage stays null and is counted, never shown as zero."""

from __future__ import annotations

from datetime import UTC, datetime

from yield_guardian.agent.chat import total_usage as chat_usage
from yield_guardian.llm.calllog import (
    CallStatus,
    LlmCallRecord,
    to_call_usage,
    to_llm_call,
    total_usage,
)

AT = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


def record(
    tokens: tuple[int, int] | None, *, cache_hit: bool = False, points: float | None = 0.001
) -> LlmCallRecord:
    return LlmCallRecord(
        started_at=AT,
        role="chat",
        model="Qwen3.8-Flash-Next",
        status=CallStatus.OK,
        cache_hit=cache_hit,
        stream=True,
        tokens_in=tokens[0] if tokens else None,
        tokens_out=tokens[1] if tokens else None,
        tokens_reasoning=0 if tokens else None,
        tokens_cached=None,
        points=points if tokens else None,
        latency_ms=12.4,
        attempts=1,
    )


def test_unreported_usage_is_null_in_the_contract() -> None:
    usage = to_call_usage(record(None))
    assert (usage.tokens_in, usage.tokens_out, usage.tokens_reasoning, usage.points) == (
        None,
        None,
        None,
        None,
    )
    call = to_llm_call(record(None))
    assert call.tokens_in is None
    assert call.error == "usage not reported by the endpoint"


def test_reported_usage_is_kept() -> None:
    usage = to_call_usage(record((100, 20)))
    assert (usage.tokens_in, usage.tokens_out, usage.points, usage.latency_ms) == (
        100,
        20,
        0.001,
        12,
    )


def test_totals_count_unknown_usage_instead_of_guessing() -> None:
    total = total_usage([record((100, 20)), record(None), record((5, 1), cache_hit=True)])
    assert (total.requests, total.tokens_in, total.tokens_out) == (2, 100, 20)
    assert total.requests_without_usage == 1
    assert total.cache_hits == 1


def test_a_chat_total_is_null_when_any_part_is_unknown() -> None:
    known = chat_usage([record((100, 20)), record((30, 5))])
    assert known is not None
    assert (known.tokens_in, known.tokens_out) == (130, 25)
    partial = chat_usage([record((100, 20)), record(None)])
    assert partial is not None
    assert (partial.tokens_in, partial.points) == (None, None)
    assert chat_usage([]) is None
