"""The plant clock, alarm rules, line state and the /ws/line message stream."""

from datetime import timedelta

import pytest

from tests.science.conftest import EPOCH, FakeNow
from yield_guardian.bundles.secom import SecomBundle
from yield_guardian.contracts.line import (
    AlarmStatus,
    LineAlarmMessage,
    LineCycle,
    LineFinalTestMessage,
    LineHeartbeat,
    LineHello,
    LineUnitMessage,
)
from yield_guardian.contracts.services import InvalidArgumentError
from yield_guardian.replay.clock import ReplayClock
from yield_guardian.replay.line import LineReplay


def test_position_and_cycle_follow_the_wall_clock(clock: ReplayClock, now: FakeNow) -> None:
    now.at_tick(1100)
    reading = clock.read()
    assert (reading.position, reading.cycle) == (1100, 0)
    assert reading.plant_time == clock.plant_times[1100]
    now.at_tick(1567 * 3 + 5)
    reading = clock.read()
    assert (reading.position, reading.cycle) == (5, 3)
    now.at = EPOCH - timedelta(days=1)
    assert clock.read().position == 0


def test_a_tick_starts_exactly_on_its_boundary(clock: ReplayClock) -> None:
    assert clock.tick(clock.tick_time(42)) == 42
    assert clock.tick(clock.tick_time(42) - timedelta(microseconds=1)) == 41


async def test_state_shows_the_latest_units_and_counts_them(line: LineReplay) -> None:
    state = await line.state(window=120)
    sequences = [u.sequence for u in state.recent]
    assert sequences == list(range(981, 1101))
    assert state.kpis.window_units == 120
    assert state.kpis.high_risk == sum(u.risk_band == "high" for u in state.recent)
    assert state.kpis.failures_revealed == sum(u.final_test == "fail" for u in state.recent)


async def test_final_test_results_wait_for_the_lag(line: LineReplay) -> None:
    state = await line.state(window=40)
    for unit in state.recent:
        revealed = unit.sequence <= 1100 - 25
        assert (unit.final_test is not None) == revealed


async def test_no_alarm_is_from_a_unit_that_has_not_come_off_the_line(line: LineReplay) -> None:
    page = await line.list_alarms(limit=500)
    assert page.items
    assert all(a.sequence <= 1100 for a in page.items)
    sequences = [a.sequence for a in page.items]
    assert sequences == sorted(sequences, reverse=True)


async def test_alarm_rules_match_the_timeline(line: LineReplay, secom_bundle: SecomBundle) -> None:
    t = secom_bundle.timeline
    page = await line.list_alarms(limit=500)
    for alarm in page.items:
        s = alarm.sequence
        assert alarm.alarm_id == f"AL-{alarm.unit_id}-{alarm.kind}"
        if alarm.kind == "t2":
            assert t.t2[s] > t.t2_limit_99[s]
            assert (alarm.severity == "alarm") == bool(t.t2[s] > t.t2_limit_999[s])
        if alarm.kind == "risk":
            assert t.risk_band[s] == "high"
    ewma = [a.sequence for a in page.items if a.kind == "ewma"]
    assert ewma == [900], "one EWMA warning per excursion, on its first unit"


async def test_alarm_pages_cover_every_alarm_once(line: LineReplay) -> None:
    everything = await line.list_alarms(limit=500)
    seen = []
    cursor = None
    while True:
        page = await line.list_alarms(limit=7, cursor=cursor)
        seen += [a.alarm_id for a in page.items]
        cursor = page.next_cursor
        if cursor is None:
            break
    assert seen == [a.alarm_id for a in everything.items]
    assert everything.total == len(seen)


async def test_a_bad_cursor_is_an_invalid_argument(line: LineReplay) -> None:
    with pytest.raises(InvalidArgumentError):
        await line.list_alarms(cursor="not-a-cursor")


async def test_alarms_close_after_the_open_window_unless_taken_over(
    secom_bundle: SecomBundle, clock: ReplayClock
) -> None:
    class Taken:
        async def overrides(self) -> dict[str, tuple[AlarmStatus, str | None]]:
            return {"AL-0-t2": ("investigating", "inv_0123456789")}

    line = LineReplay(secom_bundle, clock, Taken(), open_units=60)
    page = await line.list_alarms(limit=500)
    for alarm in page.items:
        if alarm.alarm_id == "AL-0-t2":
            assert (alarm.status, alarm.investigation_id) == ("investigating", "inv_0123456789")
        else:
            assert alarm.status == ("open" if alarm.sequence > 1100 - 60 else "closed")
    state = await line.state()
    assert all(a.status != "closed" for a in state.open_alarms)


async def test_the_stream_sends_hello_then_each_unit_in_order(
    secom_bundle: SecomBundle, clock: ReplayClock, now: FakeNow
) -> None:
    async def advance(seconds: float) -> None:
        now.at += timedelta(seconds=seconds)

    now.at_tick(1566)
    line = LineReplay(secom_bundle, clock, sleep=advance, heartbeat_seconds=15.0)
    messages = []
    async for message in line.stream():
        messages.append(message)
        if len(messages) >= 40:
            break
    assert isinstance(messages[0], LineHello)
    units = [m for m in messages if isinstance(m, LineUnitMessage)]
    assert [u.unit.sequence for u in units[:3]] == [0, 1, 2], "the replay wraps after unit 1566"
    cycle = next(i for i, m in enumerate(messages) if isinstance(m, LineCycle))
    wrap = messages[cycle]
    assert isinstance(wrap, LineCycle)
    assert wrap.clock.cycle == 1
    assert isinstance(messages[cycle + 1], LineUnitMessage)
    assert any(isinstance(m, LineHeartbeat) for m in messages)
    for i, message in enumerate(messages):
        if isinstance(message, LineAlarmMessage):
            previous_units = [m for m in messages[:i] if isinstance(m, LineUnitMessage)]
            assert message.alarm.sequence == previous_units[-1].unit.sequence


async def test_final_test_messages_trail_by_the_lag(
    secom_bundle: SecomBundle, clock: ReplayClock, now: FakeNow
) -> None:
    async def advance(seconds: float) -> None:
        now.at += timedelta(seconds=seconds)

    now.at_tick(100)
    line = LineReplay(secom_bundle, clock, sleep=advance)
    results = []
    async for message in line.stream():
        if isinstance(message, LineFinalTestMessage):
            results.append(message.sequence)
        if len(results) == 5:
            break
    assert results == [76, 77, 78, 79, 80]


async def test_a_client_that_falls_far_behind_gets_a_fresh_hello(
    secom_bundle: SecomBundle, clock: ReplayClock, now: FakeNow
) -> None:
    async def jump(seconds: float) -> None:
        now.at += timedelta(seconds=6.0 * 500)

    line = LineReplay(secom_bundle, clock, sleep=jump)
    stream = line.stream()
    first = await anext(stream)
    second = await anext(stream)
    assert isinstance(first, LineHello)
    assert isinstance(second, LineHello)
    assert second.state.clock.position == (1100 + 500) % 1567
