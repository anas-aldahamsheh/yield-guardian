"""The SECOM unit alarms of v1: rules over the full SECOM sequence, their IDs and the alarm list.

Alarm rules (written by code, never by a language model):

- risk: the unit's calibrated risk is in the high band (at or above the default operating point);
- t2, spe: the statistic is beyond its 99% control limit (warning) or 99.9% limit (alarm);
- ewma, cusum: the detector starts signalling on this unit (one warning per excursion).

An alarm's ID is ``AL-<unit>-<kind>``, a pure function of the bundle, so every alarm an
investigation was opened from (the recorded ones included) keeps resolving. There is no replay
clock: every unit is visible with its recorded final-test result, and an alarm is open unless an
investigation took it over (investigating, then closed when the investigation is decided).
"""

import base64
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from yield_guardian.bundles.secom import SecomBundle
from yield_guardian.contracts.line import (
    Alarm,
    AlarmKind,
    AlarmPage,
    AlarmSeverity,
    AlarmStatus,
    OperatingPointRef,
    UnitSummary,
)
from yield_guardian.contracts.services import InvalidArgumentError

KIND_ORDER: tuple[AlarmKind, ...] = ("risk", "t2", "spe", "ewma", "cusum")


class AlarmStates(Protocol):
    async def overrides(self) -> Mapping[str, tuple[AlarmStatus, str | None]]:
        """Alarms whose status an investigation set: alarm ID to (status, investigation ID)."""
        ...


class NoAlarmStates:
    """Used when no database is configured: every alarm is open."""

    async def overrides(self) -> Mapping[str, tuple[AlarmStatus, str | None]]:
        return {}


@dataclass(frozen=True, slots=True)
class AlarmRule:
    sequence: int
    kind: AlarmKind
    severity: AlarmSeverity
    value: float | None
    limit: float | None
    message: str


def operating_point_ref(bundle: SecomBundle) -> OperatingPointRef:
    points = bundle.operating_points
    default = next(p for p in points.points if p.id == points.default)
    return OperatingPointRef(id=default.id, label=default.label, threshold=default.threshold)


def _control_rules(
    sequence: int, kind: AlarmKind, name: str, value: float, limit_99: float, limit_999: float
) -> list[AlarmRule]:
    if value <= limit_99:
        return []
    severe = value > limit_999
    limit = limit_999 if severe else limit_99
    level = "99.9" if severe else "99"
    return [
        AlarmRule(
            sequence,
            kind,
            "alarm" if severe else "warning",
            value,
            limit,
            f"{name} {value:.1f} is beyond the {level}% control limit {limit:.1f}.",
        )
    ]


def alarm_rules(bundle: SecomBundle) -> list[list[AlarmRule]]:
    """Alarm rules per sequence number, in KIND_ORDER."""
    timeline = bundle.timeline
    op = operating_point_ref(bundle)
    rules: list[list[AlarmRule]] = []
    for seq in range(len(timeline)):
        found: list[AlarmRule] = []
        risk = float(timeline.risk[seq])
        if timeline.risk_band[seq] == "high" and risk == risk:
            found.append(
                AlarmRule(
                    seq,
                    "risk",
                    "alarm",
                    risk,
                    op.threshold,
                    f"Failure risk {risk:.1%} is at or above the {op.label} threshold "
                    f"({op.threshold:.1%}).",
                )
            )
        found += _control_rules(
            seq,
            "t2",
            "T²",
            float(timeline.t2[seq]),
            float(timeline.t2_limit_99[seq]),
            float(timeline.t2_limit_999[seq]),
        )
        found += _control_rules(
            seq,
            "spe",
            "SPE",
            float(timeline.spe[seq]),
            float(timeline.spe_limit_99[seq]),
            float(timeline.spe_limit_999[seq]),
        )
        if timeline.ewma_alarm[seq] and not (seq > 0 and timeline.ewma_alarm[seq - 1]):
            found.append(
                AlarmRule(
                    seq,
                    "ewma",
                    "warning",
                    None,
                    None,
                    "The EWMA detector on the leading sensor groups started signalling a "
                    "sustained shift.",
                )
            )
        if timeline.cusum_alarm[seq] and not (seq > 0 and timeline.cusum_alarm[seq - 1]):
            found.append(
                AlarmRule(
                    seq,
                    "cusum",
                    "warning",
                    None,
                    None,
                    "The CUSUM detector on the leading sensor groups crossed its decision interval.",
                )
            )
        rules.append(found)
    return rules


def _encode_cursor(sequence: int, kind: AlarmKind) -> str:
    raw = f"{sequence}:{KIND_ORDER.index(kind)}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[int, int]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        sequence, kind = base64.urlsafe_b64decode(padded).decode().split(":")
        return int(sequence), int(kind)
    except (ValueError, UnicodeDecodeError) as error:
        raise InvalidArgumentError("The cursor is not valid; start again without it.") from error


class SecomAlarms:
    """The unit summaries and alarms of the SECOM bundle. Stateless apart from the alarm states
    an investigation stored in the database."""

    def __init__(self, bundle: SecomBundle, states: AlarmStates | None = None) -> None:
        self.bundle = bundle
        self.states = states or NoAlarmStates()
        self.operating_point = operating_point_ref(bundle)
        self.rules = alarm_rules(bundle)

    @property
    def last_sequence(self) -> int:
        return len(self.bundle.timeline) - 1

    def summary(self, sequence: int) -> UnitSummary:
        t = self.bundle.timeline
        risk = float(t.risk[sequence])
        return UnitSummary(
            unit_id=int(t.unit_id[sequence]),
            sequence=sequence,
            timestamp=t.timestamp[sequence],
            block=t.block[sequence],
            risk=None if risk != risk else risk,
            risk_source=t.risk_source[sequence],
            risk_band=t.risk_band[sequence],
            t2=float(t.t2[sequence]),
            spe=float(t.spe[sequence]),
            fdc_alarm=t.fdc_alarm[sequence],
            fdc_period=t.fdc_period[sequence],
            ewma_alarm=bool(t.ewma_alarm[sequence]),
            cusum_alarm=bool(t.cusum_alarm[sequence]),
            final_test="fail" if t.failed[sequence] else "pass",
        )

    def _alarm(
        self, rule: AlarmRule, overrides: Mapping[str, tuple[AlarmStatus, str | None]]
    ) -> Alarm:
        t = self.bundle.timeline
        unit = int(t.unit_id[rule.sequence])
        alarm_id = f"AL-{unit}-{rule.kind}"
        status, investigation = overrides.get(alarm_id, ("open", None))
        return Alarm(
            alarm_id=alarm_id,
            unit_id=unit,
            sequence=rule.sequence,
            timestamp=t.timestamp[rule.sequence],
            kind=rule.kind,
            severity=rule.severity,
            value=rule.value,
            limit=rule.limit,
            message=rule.message,
            status=status,
            investigation_id=investigation,
        )

    async def alarms_for(self, sequence: int) -> list[Alarm]:
        """Alarms raised on one unit."""
        overrides = await self.states.overrides()
        return [self._alarm(rule, overrides) for rule in self.rules[sequence]]

    def _newest_first(
        self, last: int, overrides: Mapping[str, tuple[AlarmStatus, str | None]]
    ) -> list[Alarm]:
        return [
            self._alarm(rule, overrides) for seq in range(last, -1, -1) for rule in self.rules[seq]
        ]

    async def list_alarms(
        self,
        *,
        status: AlarmStatus | None = None,
        kind: AlarmKind | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> AlarmPage:
        """Every alarm, newest unit first (KIND_ORDER within a unit)."""
        overrides = await self.states.overrides()
        matching = [
            a
            for a in self._newest_first(self.last_sequence, overrides)
            if (status is None or a.status == status) and (kind is None or a.kind == kind)
        ]
        start = 0
        if cursor is not None:
            sequence, kind_index = _decode_cursor(cursor)
            start = next(
                (
                    i
                    for i, a in enumerate(matching)
                    if (-a.sequence, KIND_ORDER.index(a.kind)) > (-sequence, kind_index)
                ),
                len(matching),
            )
        page = matching[start : start + limit]
        more = start + limit < len(matching)
        return AlarmPage(
            items=page,
            next_cursor=_encode_cursor(page[-1].sequence, page[-1].kind) if more and page else None,
            total=len(matching),
        )
