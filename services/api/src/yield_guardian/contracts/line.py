"""SECOM unit summaries and alarms (GET /units, /alarms).

The wall-clock replay (`PlantClock`, `LineState` and the `LineEvent` messages of the former
/ws/line) is retired from the product (PLAN_V2 §3.3); those schemas stay published only until
the web no longer imports them.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, RootModel

from yield_guardian.contracts.base import (
    AlarmId,
    Contract,
    Count,
    InvestigationId,
    Probability,
    SequenceNo,
    UnitId,
)

Block = Literal["train", "validation", "test"]
RiskBand = Literal["low", "elevated", "high"]
RiskSource = Literal["oof", "validation", "test"]
FdcAlarmLevel = Literal["none", "warning", "alarm"]
FdcPeriod = Literal["reference", "monitoring"]
FinalTest = Literal["pass", "fail"]
AlarmKind = Literal["risk", "t2", "spe", "ewma", "cusum"]
AlarmSeverity = Literal["warning", "alarm"]
AlarmStatus = Literal["open", "investigating", "closed"]


class PlantClock(Contract):
    """Replay position, computed from the wall clock so every visitor sees the same plant.

    `position = floor((now - epoch) / seconds_per_unit) mod units_total`; `cycle` counts completed
    replays. Units after `position` have not come off the line yet and are never returned.
    """

    epoch: datetime
    now: datetime = Field(description="Server wall clock when this value was computed.")
    seconds_per_unit: float = Field(gt=0)
    units_total: Count
    position: SequenceNo = Field(description="Sequence number of the latest unit off the line.")
    cycle: Count
    plant_time: datetime = Field(
        description="Original timestamp of the latest unit (secom_labels.data)."
    )
    final_test_lag_units: Count = Field(
        description="A unit's final-test result is revealed this many units after it leaves the line."
    )


class OperatingPointRef(Contract):
    id: str = Field(examples=["fpr_0.05"])
    label: str = Field(examples=["5% false-alarm rate"])
    threshold: Probability


class UnitSummary(Contract):
    """One production unit as the line shows it. Values come from the SECOM bundle's timeline."""

    unit_id: UnitId
    sequence: SequenceNo
    timestamp: datetime
    block: Block
    risk: Probability | None = Field(
        description="Calibrated failure probability, always out of sample; null during the warm-up period."
    )
    risk_source: RiskSource | None
    risk_band: RiskBand | None
    t2: float = Field(ge=0, description="Hotelling T² of the unit.")
    spe: float = Field(ge=0, description="Squared prediction error (Q) of the unit.")
    fdc_alarm: FdcAlarmLevel
    fdc_period: FdcPeriod
    ewma_alarm: bool
    cusum_alarm: bool
    final_test: FinalTest | None = Field(
        description="Recorded final-test result (secom_labels.data)."
    )


class Alarm(Contract):
    """An alarm raised by a rule on one unit. Messages are written by code, not by a language model."""

    alarm_id: AlarmId
    unit_id: UnitId
    sequence: SequenceNo
    timestamp: datetime = Field(description="Plant time of the unit.")
    kind: AlarmKind
    severity: AlarmSeverity
    value: float | None
    limit: float | None
    message: str
    status: AlarmStatus
    investigation_id: InvestigationId | None


class AlarmPage(Contract):
    items: list[Alarm]
    next_cursor: str | None = None
    total: Count


class LineKpis(Contract):
    """Counts over the units in `LineState.recent`."""

    window_units: Count
    high_risk: Count
    elevated_risk: Count
    fdc_warnings: Count
    fdc_alarms: Count
    failures_revealed: Count


class LineState(Contract):
    clock: PlantClock
    operating_point: OperatingPointRef
    recent: list[UnitSummary] = Field(description="Latest units, oldest first.")
    kpis: LineKpis
    open_alarms: list[Alarm] = Field(description="Open alarms, newest first.")


class LineHello(Contract):
    """First message after the socket opens."""

    type: Literal["hello"]
    state: LineState


class LineUnitMessage(Contract):
    """A unit came off the line."""

    type: Literal["unit"]
    clock: PlantClock
    unit: UnitSummary


class LineAlarmMessage(Contract):
    type: Literal["alarm"]
    alarm: Alarm


class LineFinalTestMessage(Contract):
    """A final-test result was revealed for an earlier unit."""

    type: Literal["final_test"]
    unit_id: UnitId
    sequence: SequenceNo
    result: FinalTest


class LineHeartbeat(Contract):
    type: Literal["heartbeat"]
    clock: PlantClock


class LineCycle(Contract):
    """The replay reached the last unit and started again from the first one."""

    type: Literal["cycle"]
    clock: PlantClock


class LineEvent(
    RootModel[
        Annotated[
            LineHello
            | LineUnitMessage
            | LineAlarmMessage
            | LineFinalTestMessage
            | LineHeartbeat
            | LineCycle,
            Field(discriminator="type"),
        ]
    ]
):
    """A message on the /ws/line WebSocket (JSON text frames)."""
