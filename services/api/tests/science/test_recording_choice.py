"""The alarms chosen for the recorded demo runs follow the documented rule on the real replay."""

import pytest

from yield_guardian.agent.recording import KINDS, choose_alarms
from yield_guardian.bundles.secom import SecomBundle
from yield_guardian.replay.line import alarm_rules


def test_the_choice_follows_the_rule_and_is_the_same_every_time(
    secom_bundle: SecomBundle,
) -> None:
    chosen = choose_alarms(secom_bundle, 6)
    assert chosen == choose_alarms(secom_bundle, 6)
    assert chosen
    timeline = secom_bundle.timeline
    rules = alarm_rules(secom_bundle)
    for alarm in chosen:
        assert timeline.block[alarm.sequence] == "test"
        assert alarm.alarm_id == f"AL-{alarm.unit_id}-{alarm.kind}"
        (rule,) = [r for r in rules[alarm.sequence] if r.kind == alarm.kind]
        assert rule.severity == "alarm"
        assert alarm.message == rule.message
    assert len({a.unit_id for a in chosen}) == len(chosen)
    # Round-robin: the first picks are one of each kind that occurs, in the order of KINDS.
    present = [k for k in KINDS if any(a.kind == k for a in chosen)]
    assert [a.kind for a in chosen[: len(present)]] == present
    # Within a kind, picks follow plant order.
    for kind in KINDS:
        sequences = [a.sequence for a in chosen if a.kind == kind]
        assert sequences == sorted(sequences)


def test_at_least_one_alarm_is_asked_for(secom_bundle: SecomBundle) -> None:
    with pytest.raises(ValueError):
        choose_alarms(secom_bundle, 0)
    assert len(choose_alarms(secom_bundle, 1)) == 1
