"""SECOM unit summaries and alarms (GET /units, /alarms).

The wall-clock replay of v1 (GET /line/state and /ws/line) is gone (PLAN_V2 §3.3): the line
runs only on an input, through the runs API (`contracts/runs.py`).
"""

from datetime import datetime
from typing import Literal

from pydantic import Field

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
