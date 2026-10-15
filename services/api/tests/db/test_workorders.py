"""Work orders, the audit log and alarm states."""

import asyncio

import pytest

from tests.db.fakes import REPORT, FakeRunner
from yield_guardian.contracts.investigation import (
    DecisionCreate,
    Hypothesis,
    HypothesisEvidence,
    InvestigationTrigger,
)
from yield_guardian.contracts.services import InvalidArgumentError, NotFoundError
from yield_guardian.contracts.session import GuestSessionCreate
from yield_guardian.contracts.workorders import ConfirmedCause, WorkOrderUpdate
from yield_guardian.services.persistence import Persistence
from yield_guardian.services.protocols import ActiveSession, AuditLog, WorkOrderStore


async def _engineer(persistence: Persistence) -> ActiveSession:
    session, _ = await persistence.sessions.guest(
        GuestSessionCreate(display_name="Ali"), client="t"
    )
    return session


async def _drain(persistence: Persistence, investigation_id: str, after: int = 0) -> None:
    async with asyncio.timeout(15):
        async for _ in persistence.investigations.events(investigation_id, after_seq=after):
            pass


async def _work_orders(persistence: Persistence, count: int) -> list[str]:
    session = await _engineer(persistence)
    ids = []
    for unit in range(count):
        created = await persistence.investigations.create(
            InvestigationTrigger(kind="unit", ref=str(unit)), session=session
        )
        await _drain(persistence, created.investigation_id)
        await persistence.investigations.decide(
            created.investigation_id,
            DecisionCreate(verdict="approve", actions=[0]),
            session=session,
        )
        await _drain(persistence, created.investigation_id, after=9)
        work_order_id = (
            await persistence.investigations.get(created.investigation_id)
        ).work_order_id
        assert work_order_id is not None
        ids.append(work_order_id)
    return ids


async def test_list_and_get(persistence: Persistence) -> None:
    store: WorkOrderStore = persistence.work_orders
    ids = await _work_orders(persistence, 3)
    assert ids == ["WO-000001", "WO-000002", "WO-000003"]
    page = await store.list(limit=2)
    assert [w.work_order_id for w in page.items] == ["WO-000003", "WO-000002"]
    assert page.total == 3
    assert page.next_cursor is not None
    rest = await store.list(cursor=page.next_cursor, limit=2)
    assert [w.work_order_id for w in rest.items] == ["WO-000001"]
    assert rest.next_cursor is None
    work_order = await store.get("WO-000002")
    assert work_order.status == "open"
    assert not work_order.outcome_confirmed
    with pytest.raises(NotFoundError):
        await store.get("WO-999999")


async def test_updates_are_audited(persistence: Persistence) -> None:
    (work_order_id,) = await _work_orders(persistence, 1)
    session = await _engineer(persistence)
    store = persistence.work_orders

    updated = await store.update(
        work_order_id,
        WorkOrderUpdate(status="in_progress", note="Started", outcome="Sensor drift found"),
        session=session,
    )
    assert (updated.status, updated.note, updated.outcome) == (
        "in_progress",
        "Started",
        "Sensor drift found",
    )
    confirmed = await store.update(
        work_order_id, WorkOrderUpdate(outcome_confirmed=True), session=session
    )
    assert confirmed.outcome_confirmed
    assert confirmed.note == "Started"

    edited = await store.update(work_order_id, WorkOrderUpdate(outcome="Other"), session=session)
    assert not edited.outcome_confirmed
    cleared = await store.update(
        work_order_id, WorkOrderUpdate.model_validate({"note": None}), session=session
    )
    assert cleared.note is None

    entries = (await persistence.audit.list(action="work_order.updated")).items
    assert len(entries) == 4
    assert entries[-1].details == {
        "changes": {
            "status": {"from": "open", "to": "in_progress"},
            "note": {"from": None, "to": "Started"},
            "outcome": {"from": None, "to": "Sensor drift found"},
        }
    }
    assert entries[-1].actor_name == "Ali"

    unchanged = await store.update(
        work_order_id, WorkOrderUpdate(status="in_progress"), session=session
    )
    assert unchanged.updated_at == cleared.updated_at
    assert (await persistence.audit.list(action="work_order.updated")).total == 4


async def test_confirming_needs_an_outcome(persistence: Persistence) -> None:
    (work_order_id,) = await _work_orders(persistence, 1)
    with pytest.raises(InvalidArgumentError):
        await persistence.work_orders.update(
            work_order_id,
            WorkOrderUpdate(outcome_confirmed=True),
            session=await _engineer(persistence),
        )
    with pytest.raises(NotFoundError):
        await persistence.work_orders.update(
            "WO-123456", WorkOrderUpdate(status="done"), session=await _engineer(persistence)
        )


async def test_audit_log_pages_and_filters(persistence: Persistence) -> None:
    log: AuditLog = persistence.audit
    for _ in range(5):
        await _engineer(persistence)
    page = await log.list(limit=2)
    collected = list(page.items)
    while page.next_cursor:
        page = await log.list(cursor=page.next_cursor, limit=2)
        collected += page.items
    ids = [e.audit_id for e in collected]
    assert ids == sorted(ids, reverse=True)
    assert len(ids) == 5
    assert page.total == 5
    assert (await log.list(action="session.login")).total == 0
    with pytest.raises(InvalidArgumentError):
        await log.list(cursor=(await persistence.work_orders.list()).next_cursor or "x")


async def test_alarm_states(persistence: Persistence) -> None:
    open_alarm = await persistence.alarms.get("AL-1-risk")
    assert (open_alarm.status, open_alarm.investigation_id, open_alarm.updated_at) == (
        "open",
        None,
        None,
    )
    created = await persistence.investigations.create(
        InvestigationTrigger(kind="alarm", ref="AL-1-risk"), session=await _engineer(persistence)
    )
    states = await persistence.alarms.states(["AL-1-risk", "AL-2-t2"])
    assert list(states) == ["AL-1-risk"]
    assert states["AL-1-risk"].investigation_id == created.investigation_id
    assert list(await persistence.alarms.states()) == ["AL-1-risk"]
    await _drain(persistence, created.investigation_id)


SENSOR_HYPOTHESIS = Hypothesis(
    hypothesis="Synthetic test hypothesis: group G1 is associated with the alarm.",
    source_ids=[],
    evidence_for=[HypothesisEvidence(evidence_id="E1", observation="Synthetic observation.")],
    evidence_against=[],
    assessment="supported",
)


async def test_a_confirmed_cause_is_recorded_when_the_work_order_closes(
    persistence: Persistence, runner: FakeRunner
) -> None:
    runner.report = REPORT.model_copy(update={"hypotheses": [SENSOR_HYPOTHESIS]})
    (work_order_id,) = await _work_orders(persistence, 1)
    session = await _engineer(persistence)
    store = persistence.work_orders
    cause = ConfirmedCause(text="Synthetic confirmed cause.", hypothesis_index=0)

    with pytest.raises(InvalidArgumentError, match="closed"):
        await store.update(work_order_id, WorkOrderUpdate(confirmed_cause=cause), session=session)
    closed = await store.update(
        work_order_id, WorkOrderUpdate(status="done", confirmed_cause=cause), session=session
    )
    assert (closed.status, closed.confirmed_cause) == ("done", cause)
    assert (await store.get(work_order_id)).confirmed_cause == cause
    with pytest.raises(InvalidArgumentError, match="below 1"):
        await store.update(
            work_order_id,
            WorkOrderUpdate(confirmed_cause=ConfirmedCause(text="x", hypothesis_index=1)),
            session=session,
        )
    free = ConfirmedCause(text="Synthetic cause outside the hypotheses.")
    changed = await store.update(
        work_order_id, WorkOrderUpdate(confirmed_cause=free), session=session
    )
    assert changed.confirmed_cause == free
    entries = (await persistence.audit.list(action="work_order.updated")).items
    assert entries[0].details["changes"] == {
        "confirmed_cause": {
            "from": cause.model_dump(mode="json"),
            "to": {"text": free.text, "hypothesis_index": None},
        }
    }

    reopened = await store.update(
        work_order_id, WorkOrderUpdate(status="in_progress"), session=session
    )
    assert reopened.confirmed_cause is None  # reopening withdraws it
    await store.update(
        work_order_id, WorkOrderUpdate(status="done", confirmed_cause=free), session=session
    )
    cleared = await store.update(
        work_order_id, WorkOrderUpdate.model_validate({"confirmed_cause": None}), session=session
    )
    assert (cleared.status, cleared.confirmed_cause) == ("done", None)


async def test_a_hypothesis_index_needs_a_report_with_hypotheses(
    persistence: Persistence,
) -> None:
    (work_order_id,) = await _work_orders(persistence, 1)
    with pytest.raises(InvalidArgumentError, match="no hypotheses"):
        await persistence.work_orders.update(
            work_order_id,
            WorkOrderUpdate(
                status="done", confirmed_cause=ConfirmedCause(text="x", hypothesis_index=0)
            ),
            session=await _engineer(persistence),
        )
    assert (await persistence.work_orders.get(work_order_id)).status == "open"
