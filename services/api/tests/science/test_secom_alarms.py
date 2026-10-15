"""SECOM unit alarms without a replay clock: rules over every unit, stable IDs, stored states."""

import pytest

from yield_guardian.bundles.secom import SecomBundle
from yield_guardian.contracts.line import AlarmStatus
from yield_guardian.contracts.services import InvalidArgumentError
from yield_guardian.science.secom.alarms import SecomAlarms, alarm_rules


async def test_alarms_cover_every_unit_newest_first(
    alarms: SecomAlarms, secom_bundle: SecomBundle
) -> None:
    expected = {(r.sequence, r.kind) for found in alarm_rules(secom_bundle) for r in found}
    found: list[tuple[int, str]] = []
    cursor = None
    while True:
        page = await alarms.list_alarms(limit=500, cursor=cursor)
        found += [(a.sequence, a.kind) for a in page.items]
        cursor = page.next_cursor
        if cursor is None:
            break
    assert page.total == len(expected)
    assert set(found) == expected
    sequences = [s for s, _ in found]
    assert sequences == sorted(sequences, reverse=True)


async def test_alarm_rules_match_the_timeline(
    alarms: SecomAlarms, secom_bundle: SecomBundle
) -> None:
    t = secom_bundle.timeline
    everything = await alarms.list_alarms(limit=500)
    for alarm in everything.items:
        s = alarm.sequence
        assert alarm.alarm_id == f"AL-{alarm.unit_id}-{alarm.kind}"
        assert alarm.unit_id == int(t.unit_id[s])
        if alarm.kind == "t2":
            assert t.t2[s] > t.t2_limit_99[s]
            assert (alarm.severity == "alarm") == bool(t.t2[s] > t.t2_limit_999[s])
        if alarm.kind == "risk":
            assert t.risk_band[s] == "high"
    ewma = [a.sequence for a in (await alarms.list_alarms(kind="ewma", limit=500)).items]
    assert ewma == [900], "one EWMA warning per excursion, on its first unit"


async def test_alarm_pages_cover_every_alarm_once(alarms: SecomAlarms) -> None:
    total = (await alarms.list_alarms(limit=1)).total
    seen: list[str] = []
    cursor = None
    while True:
        page = await alarms.list_alarms(limit=97, cursor=cursor)
        seen += [a.alarm_id for a in page.items]
        cursor = page.next_cursor
        if cursor is None:
            break
    assert len(seen) == len(set(seen)) == total


async def test_a_bad_cursor_is_an_invalid_argument(alarms: SecomAlarms) -> None:
    with pytest.raises(InvalidArgumentError):
        await alarms.list_alarms(cursor="not-a-cursor")


async def test_an_alarm_is_open_unless_an_investigation_took_it_over(
    secom_bundle: SecomBundle,
) -> None:
    class Taken:
        async def overrides(self) -> dict[str, tuple[AlarmStatus, str | None]]:
            return {"AL-0-t2": ("investigating", "inv_0123456789")}

    alarms = SecomAlarms(secom_bundle, Taken())
    statuses = {
        a.alarm_id: (a.status, a.investigation_id)
        for a in (await alarms.list_alarms(limit=500)).items
    }
    if "AL-0-t2" in statuses:
        assert statuses.pop("AL-0-t2") == ("investigating", "inv_0123456789")
    assert set(statuses.values()) == {("open", None)}
    investigating = await alarms.list_alarms(status="investigating", limit=500)
    assert [a.alarm_id for a in investigating.items] in ([], ["AL-0-t2"])


def test_every_unit_shows_its_recorded_final_test(
    alarms: SecomAlarms, secom_bundle: SecomBundle
) -> None:
    t = secom_bundle.timeline
    for sequence in (0, 700, len(t) - 1):
        summary = alarms.summary(sequence)
        assert summary.final_test == ("fail" if t.failed[sequence] else "pass")
