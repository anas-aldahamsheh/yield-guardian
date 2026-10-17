"""GET /investigations/{id}/calls: the investigation's model calls oldest first, with the sent and
returned text; another workspace's investigation answers 404 and the shared example opens for
everyone. The rows are written directly: no model is called."""

import asyncio
from datetime import UTC, datetime, timedelta

from tests.db.browsers import Stack, open_browser, stack
from tests.db.test_isolation import investigate_unit, seed_the_example
from yield_guardian.db.tables import LlmCallRow
from yield_guardian.llm.calllog import CallStatus, LlmCallRecord

__all__ = ["stack"]  # the fixture


def _record(
    at: datetime, role: str, model: str, status: CallStatus, correlation_id: str
) -> LlmCallRecord:
    failed = status is not CallStatus.OK
    return LlmCallRecord.model_validate(
        {
            "started_at": at,
            "role": role,
            "model": model,
            "status": status,
            "cache_hit": False,
            "stream": False,
            "tokens_in": 100,
            "tokens_out": 0 if failed else 50,
            "tokens_reasoning": None,
            "tokens_cached": None,
            "points": None,
            "latency_ms": 1234.4,
            "attempts": 1,
            "error_kind": "empty" if failed else None,
            "error_message": "empty answer" if failed else None,
            "correlation_id": correlation_id,
            "sent_text": f"ask {role}",
            "returned_text": None if failed else f"answer {role}",
        }
    )


async def test_calls_are_listed_in_order_and_scoped_to_the_workspace(stack: Stack) -> None:
    example, _ = await seed_the_example(stack)
    a, b = await asyncio.gather(open_browser(stack, "Ana"), open_browser(stack, "Ben"))
    await investigate_unit(a, "1304")
    mine = a.investigation_id
    t0 = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
    records = [
        _record(
            t0 + timedelta(seconds=2), "writer", "deepseek-v4.1-flash:free", CallStatus.EMPTY, mine
        ),
        _record(t0, "investigator", "qwen3-235b", CallStatus.OK, mine),
        _record(t0 + timedelta(seconds=3), "writer", "qwen3-235b", CallStatus.OK, mine),
        _record(t0, "chat", "qwen3-235b", CallStatus.OK, "chat_other"),
    ]
    async with stack.persistence.database.sessionmaker.begin() as db:
        db.add_all(
            LlmCallRow(
                started_at=r.started_at,
                role=r.role,
                model=r.model,
                status=str(r.status),
                correlation_id=r.correlation_id,
                record=r.model_dump(mode="json"),
            )
            for r in records
        )

    listed = await a.client.get(f"/api/v1/investigations/{mine}/calls")
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert [(r["role"], r["status"], r["provider"]) for r in rows] == [
        ("investigator", "ok", "token_factory"),
        ("writer", "empty", "anthropic"),
        ("writer", "ok", "token_factory"),
    ]
    assert (rows[0]["sent"], rows[0]["returned"], rows[0]["latency_ms"]) == (
        "ask investigator",
        "answer investigator",
        1234,
    )
    assert (rows[1]["error"], rows[1]["returned"]) == ("empty answer", None)

    hidden = await b.client.get(f"/api/v1/investigations/{mine}/calls")
    assert hidden.status_code == 404, hidden.text
    shared = await b.client.get(f"/api/v1/investigations/{example}/calls")
    assert shared.status_code == 200, shared.text
