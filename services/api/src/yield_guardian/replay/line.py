"""The live line: unit summaries, alarm rules, line state and the /ws/line message stream.

Alarm rules (written by code, never by a language model):

- risk: the unit's calibrated risk is in the high band (at or above the default operating point);
- t2, spe: the statistic is beyond its 99% control limit (warning) or 99.9% limit (alarm);
- ewma, cusum: the detector starts signalling on this unit (one warning per excursion).

An alarm stays open for `open_units` further units. Unless an investigation took it over, it then
closes by itself; the alarm list keeps it.
"""

import asyncio
import base64
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from yield_guardian.bundles.secom import SecomBundle
from yield_guardian.contracts.line import (
    Alarm,
    AlarmKind,
    AlarmPage,
    AlarmSeverity,
    AlarmStatus,
    FinalTest,
    LineAlarmMessage,
    LineCycle,
    LineFinalTestMessage,
    LineHeartbeat,
    LineHello,
    LineKpis,
    LineState,
    LineUnitMessage,
    OperatingPointRef,
    PlantClock,
    UnitSummary,
)
from yield_guardian.contracts.services import InvalidArgumentError
from yield_guardian.replay.clock import ReplayClock
from yield_guardian.services.protocols import LineMessage

KIND_ORDER: tuple[AlarmKind, ...] = ("risk", "t2", "spe", "ewma", "cusum")
OPEN_ALARMS_SHOWN = 50
CATCH_UP_LIMIT = 50


class AlarmStates(Protocol):
    async def overrides(self) -> Mapping[str, tuple[AlarmStatus, str | None]]:
        """Alarms whose status an investigation set: alarm ID to (status, investigation ID)."""
        ...


class NoAlarmStates:
    """Used when no database is configured: alarms open and close by the rule alone."""

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


class LineReplay:
    """LineService on a SECOM bundle. Stateless apart from the alarm states in the database."""

    def __init__(
        self,
        bundle: SecomBundle,
        clock: ReplayClock,
        states: AlarmStates | None = None,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        heartbeat_seconds: float = 15.0,
        open_units: int = 60,
    ) -> None:
        if clock.units_total != len(bundle.timeline):
            raise ValueError("The clock and the bundle disagree on the number of units.")
        self.bundle = bundle
        self.replay_clock = clock
        self.states = states or NoAlarmStates()
        self.sleep = sleep
        self.heartbeat_seconds = heartbeat_seconds
        self.open_units = open_units
        self.operating_point = operating_point_ref(bundle)
        self.rules = alarm_rules(bundle)

    def clock(self) -> PlantClock:
        return self.replay_clock.read()

    def summary(self, sequence: int, position: int) -> UnitSummary:
        t = self.bundle.timeline
        risk = float(t.risk[sequence])
        lag = self.replay_clock.final_test_lag_units
        final_test: FinalTest | None = None
        if sequence <= position - lag:
            final_test = "fail" if t.failed[sequence] else "pass"
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
            final_test=final_test,
        )

    def _alarm(
        self,
        rule: AlarmRule,
        position: int,
        overrides: Mapping[str, tuple[AlarmStatus, str | None]],
    ) -> Alarm:
        t = self.bundle.timeline
        unit = int(t.unit_id[rule.sequence])
        alarm_id = f"AL-{unit}-{rule.kind}"
        status, investigation = overrides.get(
            alarm_id, ("open" if rule.sequence > position - self.open_units else "closed", None)
        )
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

    async def alarms_for(self, sequence: int, position: int) -> list[Alarm]:
        """Alarms raised on one unit, if it has come off the line."""
        if sequence > position:
            return []
        overrides = await self.states.overrides()
        return [self._alarm(rule, position, overrides) for rule in self.rules[sequence]]

    def _newest_first(
        self, position: int, overrides: Mapping[str, tuple[AlarmStatus, str | None]]
    ) -> list[Alarm]:
        return [
            self._alarm(rule, position, overrides)
            for seq in range(position, -1, -1)
            for rule in self.rules[seq]
        ]

    async def state(self, *, window: int = 120) -> LineState:
        clock = self.clock()
        position = clock.position
        first = max(0, position - window + 1)
        recent = [self.summary(seq, position) for seq in range(first, position + 1)]
        overrides = await self.states.overrides()
        open_alarms = [a for a in self._newest_first(position, overrides) if a.status != "closed"]
        return LineState(
            clock=clock,
            operating_point=self.operating_point,
            recent=recent,
            kpis=LineKpis(
                window_units=len(recent),
                high_risk=sum(u.risk_band == "high" for u in recent),
                elevated_risk=sum(u.risk_band == "elevated" for u in recent),
                fdc_warnings=sum(u.fdc_alarm == "warning" for u in recent),
                fdc_alarms=sum(u.fdc_alarm == "alarm" for u in recent),
                failures_revealed=sum(u.final_test == "fail" for u in recent),
            ),
            open_alarms=open_alarms[:OPEN_ALARMS_SHOWN],
        )

    async def list_alarms(
        self,
        *,
        status: AlarmStatus | None = None,
        kind: AlarmKind | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> AlarmPage:
        position = self.clock().position
        overrides = await self.states.overrides()
        matching = [
            a
            for a in self._newest_first(position, overrides)
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

    async def _unit_messages(self, tick: int) -> AsyncIterator[LineMessage]:
        clock = self.replay_clock.at_tick(tick)
        position = clock.position
        if position == 0 and tick > 0:
            yield LineCycle(type="cycle", clock=clock)
        yield LineUnitMessage(type="unit", clock=clock, unit=self.summary(position, position))
        for alarm in await self.alarms_for(position, position):
            yield LineAlarmMessage(type="alarm", alarm=alarm)
        revealed = position - self.replay_clock.final_test_lag_units
        if revealed >= 0:
            t = self.bundle.timeline
            yield LineFinalTestMessage(
                type="final_test",
                unit_id=int(t.unit_id[revealed]),
                sequence=revealed,
                result="fail" if t.failed[revealed] else "pass",
            )

    async def stream(self) -> AsyncIterator[LineMessage]:
        """Hello first, then each unit as it comes off the line, its alarms and revealed results."""
        yield LineHello(type="hello", state=await self.state())
        clock = self.replay_clock
        last = clock.tick()
        heartbeat_at = clock.now().timestamp() + self.heartbeat_seconds
        while True:
            now = clock.now().timestamp()
            next_unit = clock.tick_time(last + 1).timestamp()
            await self.sleep(max(0.0, min(next_unit, heartbeat_at) - now))
            current = clock.tick()
            if current - last > CATCH_UP_LIMIT:
                yield LineHello(type="hello", state=await self.state())
                last = current
            while last < current:
                last += 1
                async for message in self._unit_messages(last):
                    yield message
            if clock.now().timestamp() >= heartbeat_at:
                yield LineHeartbeat(type="heartbeat", clock=clock.read())
                heartbeat_at = clock.now().timestamp() + self.heartbeat_seconds
