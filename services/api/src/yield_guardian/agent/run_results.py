"""One unit, wafer, lot or alarm of a run, picked out of its stage results (PLAN_V2 3.4, 8).

The run store implements :class:`~yield_guardian.live.protocols.RunReader` and the app registers
it as ``ServiceRegistry.run_reader``; the run tools (:mod:`yield_guardian.agent.run_tools`) read
runs through it and never change one. The functions here only select what the stages computed.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from yield_guardian.contracts.runs import (
    ControlChartsResult,
    DriftHealthResult,
    LotItem,
    LotResult,
    Run,
    RunAlarm,
    SensorRiskResult,
    UnitChartResult,
    UnitRiskResult,
    WaferPatternItem,
    WaferPatternResult,
    WaferSimilarItem,
    WaferSimilarResult,
)

RUN_ALARM_REF = re.compile(r"^(?P<run_id>run_[0-9a-z]{8,40}):(?P<alarm_id>RA-\d{1,6})$")
"""``InvestigationTrigger.ref`` of kind ``run_alarm``: ``<run_id>:<alarm_id>``."""


def parse_run_alarm_ref(ref: str) -> tuple[str, str] | None:
    """``(run_id, alarm_id)`` of a ``run_alarm`` reference, or None when it is not one."""
    match = RUN_ALARM_REF.match(ref.strip())
    return (match.group("run_id"), match.group("alarm_id")) if match else None


def stage_result[R](run: Run, kind: type[R]) -> R | None:
    """The result of the run's stage of type ``kind``, or None when that stage has none
    (pending, skipped or failed)."""
    for state in run.stages:
        if isinstance(state.result, kind):
            return state.result
    return None


def find_alarm(run: Run, alarm_id: str) -> RunAlarm | None:
    return next((a for a in run.alarms if a.alarm_id == alarm_id), None)


def _at[T: (UnitRiskResult, WaferPatternItem, WaferSimilarItem)](
    items: Sequence[T], index: int
) -> T | None:
    return next((item for item in items if item.index == index), None)


@dataclass(frozen=True, slots=True)
class UnitResults:
    """Everything the stages computed for one sensor unit of a run."""

    index: int
    risk_stage: SensorRiskResult | None
    risk: UnitRiskResult | None
    charts: ControlChartsResult | None
    chart: UnitChartResult | None
    drift: DriftHealthResult | None
    alarms: tuple[RunAlarm, ...]


def unit_results(run: Run, index: int, chart: UnitChartResult | None) -> UnitResults:
    """``chart`` is the unit's control-chart result as ``RunReader.get_unit_chart`` returns it,
    with ``z``: the run itself carries ``z`` for at most its first 200 units."""
    risk_stage = stage_result(run, SensorRiskResult)
    charts = stage_result(run, ControlChartsResult)
    return UnitResults(
        index=index,
        risk_stage=risk_stage,
        risk=_at(risk_stage.units, index) if risk_stage else None,
        charts=charts,
        chart=chart,
        drift=stage_result(run, DriftHealthResult),
        alarms=tuple(a for a in run.alarms if a.unit_index == index),
    )


@dataclass(frozen=True, slots=True)
class WaferResults:
    """Everything the stages computed for one wafer of a run."""

    index: int
    patterns: WaferPatternResult | None
    pattern: WaferPatternItem | None
    similar_stage: WaferSimilarResult | None
    similar: WaferSimilarItem | None
    lot: LotItem | None
    alarms: tuple[RunAlarm, ...]


def wafer_results(run: Run, index: int) -> WaferResults:
    patterns = stage_result(run, WaferPatternResult)
    similar_stage = stage_result(run, WaferSimilarResult)
    pattern = _at(patterns.wafers, index) if patterns else None
    lot = lot_item(run, pattern.lot) if pattern else None
    return WaferResults(
        index=index,
        patterns=patterns,
        pattern=pattern,
        similar_stage=similar_stage,
        similar=_at(similar_stage.wafers, index) if similar_stage else None,
        lot=lot,
        alarms=tuple(
            a
            for a in run.alarms
            if a.wafer_index == index
            or (lot is not None and a.wafer_index is None and a.lot == lot.lot)
        ),
    )


def lot_item(run: Run, lot: str) -> LotItem | None:
    lots = stage_result(run, LotResult)
    return next((item for item in lots.lots if item.lot == lot), None) if lots else None


def lot_wafers(run: Run, lot: str) -> list[WaferPatternItem]:
    """The run's wafer predictions of one lot, in input order."""
    patterns = stage_result(run, WaferPatternResult)
    return [w for w in patterns.wafers if w.lot == lot] if patterns else []
