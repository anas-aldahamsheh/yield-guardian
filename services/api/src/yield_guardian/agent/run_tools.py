"""The run tools (PLAN_V2 3.4, 7 and 8): what the investigator and the chat read of one run.

Four read-only tools over a run's stage results, through
:class:`~yield_guardian.live.protocols.RunReader`:

* ``get_run``: origin, stage statuses, counts, the highlights of each stage and the alarms;
* ``get_run_unit``: one sensor unit: risk, T² and SPE with their largest contributions, how far
  each sensor group deviated (share of T² and SPE, SHAP, standardised readings) and since when
  (EWMA and CUSUM onset), sensor health and alarms;
* ``get_run_wafer``: one wafer: pattern and confidence, unknown score, spatial clustering, the
  radial profile of its fail dies, similar wafers and their recorded labels, the literature
  causes proposed for its pattern, its lot's tests and alarms;
* ``get_run_lot``: one lot: pattern tests, the radial profile of its stacked map, its wafers and
  alarms.

Every number in a result is a value a stage computed, or a count, sum, maximum or share of such
values computed here, so the verifier can check each number a report cites. When an item is a
real SECOM unit or WM-811K wafer (``source_unit``, ``source_wafer``) the result says so; the
science tools read it under that ID.
"""

from __future__ import annotations

import base64
import binascii
import math
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from pydantic import Field

from yield_guardian.agent.run_results import (
    UnitResults,
    find_alarm,
    lot_item,
    lot_wafers,
    stage_result,
    unit_results,
    wafer_results,
)
from yield_guardian.agent.tool_base import Tool, ToolArgs
from yield_guardian.contracts.base import (
    Contract,
    Count,
    Estimate,
    Probability,
    SensorId,
    Share,
    UnitId,
    WaferId,
)
from yield_guardian.contracts.investigation import ToolName
from yield_guardian.contracts.knowledge import KnowledgeSource, PatternCause
from yield_guardian.contracts.runs import (
    MAX_UNITS,
    MAX_WAFERS,
    ControlChartsResult,
    DriftHealthResult,
    FinalResult,
    FinalTestResult,
    IntakeResult,
    LotItem,
    LotResult,
    RiskValidity,
    Run,
    RunAlarm,
    RunAlarmKind,
    RunId,
    RunOrigin,
    RunStatus,
    SensorRiskResult,
    SensorUnitInput,
    SimilarItem,
    StageId,
    StageStatus,
    Station,
    UnitChartResult,
    UnitRiskResult,
    UserLabel,
    WaferInput,
    WaferPatternItem,
    WaferPatternResult,
    WaferSimilarResult,
)
from yield_guardian.contracts.secom import FdcLimits, MetricValue, SensorStatus
from yield_guardian.contracts.services import (
    NotFoundError,
    NotReadyError,
    ScienceServices,
    ServiceError,
)
from yield_guardian.contracts.wafer import StackedMap, WaferLabel, WaferMap
from yield_guardian.live.protocols import RunReader

RUN_TOOL_NAMES: tuple[ToolName, ...] = ("get_run", "get_run_unit", "get_run_wafer", "get_run_lot")
MAX_LISTED_ALARMS = 40
"""Alarms listed in a run overview (the first raised); every alarm is counted."""
MAX_LISTED_LOTS = 20
MAX_UNIT_SENSORS = 30
MAX_UNIT_GROUPS = 12
MAX_LOT_WAFERS = 50
RADIAL_BANDS = 4
NO_RUNS = "the run store is not available"


# -- arguments ----------------------------------------------------------------------------------


class RunArgs(ToolArgs):
    run_id: RunId


class RunUnitArgs(ToolArgs):
    run_id: RunId
    unit_index: int = Field(
        ge=0, lt=MAX_UNITS, description="Position of the unit in the run input (0-based)."
    )


class RunWaferArgs(ToolArgs):
    run_id: RunId
    wafer_index: int = Field(
        ge=0, lt=MAX_WAFERS, description="Position of the wafer in the run input (0-based)."
    )


class RunLotArgs(ToolArgs):
    run_id: RunId
    lot: UserLabel


# -- results ------------------------------------------------------------------------------------


class StageStatusItem(Contract):
    stage: StageId
    station: Station
    status: StageStatus
    needs: str | None
    elapsed_ms: float | None
    problem: str | None = Field(description="Why a failed stage failed.")


class RiskHighlights(Contract):
    threshold: Probability
    elevated_threshold: Probability
    operating_point: str
    units_scored: Count
    units_above_threshold: Count
    highest_risk: Probability | None
    highest_risk_index: Count | None
    highest_risk_unit_id: UserLabel | None
    validity_counts: dict[RiskValidity, Count]
    skill: list[MetricValue]
    caution: str


class ChartHighlights(Contract):
    limits: FdcLimits
    monitored_sensors: Count
    units: Count
    units_at_warning: Count
    units_at_alarm: Count
    highest_t2: float | None
    highest_t2_index: Count | None
    highest_spe: float | None
    highest_spe_index: Count | None


class GroupOnset(Contract):
    group_id: str
    sensors: list[SensorId]
    ewma_limit: float
    ewma_max_abs: float | None
    cusum_h: float
    first_ewma_alarm: Count | None
    first_cusum_alarm: Count | None


class DriftHighlights(Contract):
    groups: list[GroupOnset]
    health_counts: dict[SensorStatus, Count]


class WaferHighlights(Contract):
    wafers: Count
    accept_threshold: Probability
    label_counts: dict[WaferLabel, Count] = Field(description="Predicted (top) patterns.")
    auto_accepted: Count
    unknown: Count
    clustered: Count = Field(description="Wafers whose fail dies cluster (join-count test).")
    with_recorded_label: Count
    agreeing_with_recorded: Count


class LotHighlights(Contract):
    lot: UserLabel
    wafers: Count
    flagged: bool
    flagged_labels: list[WaferLabel]
    min_q_value: Probability | None


class RunOverview(Contract):
    run_id: RunId
    status: RunStatus
    created_at: datetime
    expires_at: datetime | None
    origin: RunOrigin
    units: Count
    wafers: Count
    stages: list[StageStatusItem]
    intake: IntakeResult | None
    risk: RiskHighlights | None
    charts: ChartHighlights | None
    drift: DriftHighlights | None
    wafer_patterns: WaferHighlights | None
    lots: list[LotHighlights]
    lots_total: Count
    final_test: FinalTestResult | None
    alarms_total: Count = Field(description="Alarms listed on the run.")
    alarms_not_listed: Count = Field(description="Alarms raised beyond the run's cap.")
    alarm_counts: dict[RunAlarmKind, Count] = Field(description="Listed alarms by kind.")
    alarms: list[RunAlarm] = Field(description="The first listed alarms, in order.")


class SensorReading(Contract):
    sensor: SensorId
    value: float | None = Field(description="The reading in the run input; null when missing.")
    z: float | None = Field(description="Standardised reading in the control-chart model.")
    group_id: str | None
    t2_share: Share | None = Field(description="Share of the unit's T² (listed contributions).")
    spe_share: Share | None
    shap: float | None = Field(description="SHAP of the sensor's value feature (log-odds).")
    missing_indicator_shap: float | None
    health: SensorStatus | None = Field(description="Null when the health stage did not run.")
    health_reasons: list[str]


class GroupDeviation(Contract):
    group_id: str
    sensors: list[SensorId] = Field(description="The group's sensors this run lists.")
    shap: float | None = Field(
        description="Sum of the SHAP values (log-odds) of the group's listed risk features."
    )
    t2_share: float | None = Field(
        description="Sum of the shares of the group's sensors among the listed T² contributions."
    )
    spe_share: float | None
    max_abs_z: float | None
    max_abs_z_sensor: SensorId | None
    ewma: float | None = Field(description="The group's EWMA at this unit.")
    ewma_limit: float | None
    cusum_upper: float | None
    cusum_lower: float | None
    cusum_h: float | None
    first_ewma_alarm: Count | None = Field(description="Run index of the group's first EWMA alarm.")
    first_cusum_alarm: Count | None


class RunUnitEvidence(Contract):
    run_id: RunId
    index: Count
    unit_id: UserLabel
    source_unit: UnitId | None = Field(description="The SECOM unit this is, for a real unit.")
    timestamp: datetime | None
    recorded_result: FinalResult | None
    risk: UnitRiskResult | None
    risk_threshold: Probability | None
    risk_elevated_threshold: Probability | None
    operating_point: str | None
    risk_skill: list[MetricValue]
    risk_caution: str | None
    chart: UnitChartResult | None
    limits: FdcLimits | None
    groups: list[GroupDeviation]
    sensors: list[SensorReading]
    health_counts: dict[SensorStatus, Count] | None
    alarms: list[RunAlarm]
    notes: list[str]


class RadialBand(Contract):
    inner: float = Field(description="Inner edge, as a fraction of the wafer radius.")
    outer: float
    positions: Count = Field(description="Die positions in the band.")
    fail_share: Share | None = Field(
        description="Share of failed dies in the band (for a lot: mean of the stacked shares)."
    )


class RunWaferEvidence(Contract):
    run_id: RunId
    index: Count
    lot: UserLabel
    wafer: int
    source_wafer: WaferId | None = Field(description="The WM-811K wafer this is, for a real one.")
    recorded_label: WaferLabel | None
    pattern: WaferPatternItem | None
    accept_threshold: Probability | None
    dies: Count | None
    failed_dies: Count | None
    fail_share: Share | None
    radial_profile: list[RadialBand]
    similar: list[SimilarItem]
    similar_recorded_labels: dict[WaferLabel, Count]
    similar_unlabelled: Count
    similar_matching_pattern: Count | None = Field(
        description="Similar wafers whose recorded label is this wafer's predicted pattern."
    )
    searched: Count | None
    precision_at_10: Estimate | None
    causes: list[PatternCause] = Field(
        description="Literature causes proposed for the predicted pattern: hypotheses to check."
    )
    causes_framing: str | None
    sources: list[KnowledgeSource]
    lot_result: LotItem | None
    alarms: list[RunAlarm]
    notes: list[str]


class LotWafer(Contract):
    index: Count
    wafer: int
    source_wafer: WaferId | None
    top_label: WaferLabel
    top_probability: Probability
    auto_accepted: bool
    is_unknown: bool
    clustered: bool | None
    recorded_label: WaferLabel | None


class RunLotEvidence(Contract):
    run_id: RunId
    lot: UserLabel
    result: LotItem | None
    stacked_radial_profile: list[RadialBand]
    wafers_total: Count
    wafers: list[LotWafer]
    alarms: list[RunAlarm]
    notes: list[str]


# -- reading ------------------------------------------------------------------------------------


def _reader(services: ScienceServices) -> RunReader:
    if services.runs is None:
        raise NotReadyError(NO_RUNS)
    return services.runs


async def read_run(services: ScienceServices, run_id: str) -> Run:
    run = await _reader(services).get_run(run_id)
    if run is None:
        raise NotFoundError(f"Run {run_id} does not exist or has expired.")
    return run


def _missing(run: Run, stages: Iterable[StageId]) -> list[str]:
    """Why stages a result relies on have no result, in the stages' own words."""
    out = []
    for state in run.stages:
        if state.stage not in stages or state.result is not None:
            continue
        if state.status == "skipped":
            out.append(f"{state.stage} was skipped: {state.needs or 'its input is missing'}")
        elif state.status == "failed":
            detail = state.problem.detail if state.problem and state.problem.detail else "failed"
            out.append(f"{state.stage} failed: {detail}")
        else:
            out.append(f"{state.stage} has no result yet (status {state.status})")
    return out


def _argmax(values: Sequence[tuple[float, int]]) -> tuple[float | None, int | None]:
    if not values:
        return None, None
    value, index = max(values, key=lambda item: item[0])
    return value, index


# -- get_run ------------------------------------------------------------------------------------


def _risk_highlights(stage: SensorRiskResult) -> RiskHighlights:
    top, index = _argmax([(u.risk, u.index) for u in stage.units])
    unit = next((u for u in stage.units if u.index == index), None)
    return RiskHighlights(
        threshold=stage.threshold,
        elevated_threshold=stage.elevated_threshold,
        operating_point=stage.operating_point,
        units_scored=len(stage.units),
        units_above_threshold=sum(u.above_threshold for u in stage.units),
        highest_risk=top,
        highest_risk_index=index,
        highest_risk_unit_id=unit.unit_id if unit else None,
        validity_counts=dict(Counter(u.validity for u in stage.units)),
        skill=stage.skill,
        caution=stage.caution,
    )


def _chart_highlights(stage: ControlChartsResult) -> ChartHighlights:
    t2, t2_index = _argmax([(u.t2, u.index) for u in stage.units])
    spe, spe_index = _argmax([(u.spe, u.index) for u in stage.units])
    return ChartHighlights(
        limits=stage.limits,
        monitored_sensors=len(stage.features),
        units=len(stage.units),
        units_at_warning=sum(u.level == "warning" for u in stage.units),
        units_at_alarm=sum(u.level == "alarm" for u in stage.units),
        highest_t2=t2,
        highest_t2_index=t2_index,
        highest_spe=spe,
        highest_spe_index=spe_index,
    )


def _drift_highlights(stage: DriftHealthResult) -> DriftHighlights:
    return DriftHighlights(
        groups=[
            GroupOnset(
                group_id=g.group_id,
                sensors=g.sensors,
                ewma_limit=g.ewma_limit,
                ewma_max_abs=max((abs(v) for v in g.ewma), default=None),
                cusum_h=g.cusum_h,
                first_ewma_alarm=g.first_ewma_alarm,
                first_cusum_alarm=g.first_cusum_alarm,
            )
            for g in stage.groups
        ],
        health_counts=stage.health_counts,
    )


def _wafer_highlights(stage: WaferPatternResult) -> WaferHighlights:
    wafers = stage.wafers
    labelled = [w for w in wafers if w.recorded_label is not None]
    return WaferHighlights(
        wafers=len(wafers),
        accept_threshold=stage.accept_threshold,
        label_counts=dict(Counter(w.top_label for w in wafers)),
        auto_accepted=sum(w.auto_accepted for w in wafers),
        unknown=sum(w.is_unknown for w in wafers),
        clustered=sum(bool(w.spatial and w.spatial.clustered) for w in wafers),
        with_recorded_label=len(labelled),
        agreeing_with_recorded=sum(w.top_label == w.recorded_label for w in labelled),
    )


def _lot_highlights(item: LotItem) -> LotHighlights:
    flagged = [t for t in item.tests if t.flagged]
    return LotHighlights(
        lot=item.lot,
        wafers=item.wafers,
        flagged=item.flagged,
        flagged_labels=[t.label for t in flagged],
        min_q_value=min((t.q_value for t in item.tests), default=None),
    )


def run_overview(run: Run) -> RunOverview:
    risk = stage_result(run, SensorRiskResult)
    charts = stage_result(run, ControlChartsResult)
    drift = stage_result(run, DriftHealthResult)
    patterns = stage_result(run, WaferPatternResult)
    lots = stage_result(run, LotResult)
    return RunOverview(
        run_id=run.run_id,
        status=run.status,
        created_at=run.created_at,
        expires_at=run.expires_at,
        origin=run.origin,
        units=run.units,
        wafers=run.wafers,
        stages=[
            StageStatusItem(
                stage=s.stage,
                station=s.station,
                status=s.status,
                needs=s.needs,
                elapsed_ms=s.elapsed_ms,
                problem=s.problem.detail if s.problem else None,
            )
            for s in run.stages
        ],
        intake=stage_result(run, IntakeResult),
        risk=_risk_highlights(risk) if risk else None,
        charts=_chart_highlights(charts) if charts else None,
        drift=_drift_highlights(drift) if drift else None,
        wafer_patterns=_wafer_highlights(patterns) if patterns else None,
        lots=[_lot_highlights(item) for item in (lots.lots if lots else [])][:MAX_LISTED_LOTS],
        lots_total=len(lots.lots) if lots else 0,
        final_test=stage_result(run, FinalTestResult),
        alarms_total=len(run.alarms),
        alarms_not_listed=run.alarms_not_listed,
        alarm_counts=dict(Counter(a.kind for a in run.alarms)),
        alarms=run.alarms[:MAX_LISTED_ALARMS],
    )


async def get_run(services: ScienceServices, args: RunArgs) -> RunOverview:
    return run_overview(await read_run(services, args.run_id))


def _run_summary(args: RunArgs, r: RunOverview) -> str:
    by_status = Counter(s.status for s in r.stages)
    stages = ", ".join(f"{n} {status}" for status, n in sorted(by_status.items()))
    return (
        f"Run {r.run_id} ({r.origin.title}): {r.units} units and {r.wafers} wafers, status "
        f"{r.status}; stages {stages}; {r.alarms_total} alarms."
    )


# -- get_run_unit -------------------------------------------------------------------------------


def _sensor_index(sensor: str) -> int:
    return int(sensor[1:]) - 1


def _unit_sensors(results: UnitResults) -> list[str]:
    """The sensors that stand out for a unit: its largest T² and SPE contributions, its largest
    SHAP features and the sensors its alarms name, in that order, without repeats."""
    named: list[str] = []
    if results.chart is not None:
        named += [c.sensor for c in results.chart.top_t2] + [
            c.sensor for c in results.chart.top_spe
        ]
    if results.risk is not None:
        named += [f.sensor for f in results.risk.top]
    for alarm in results.alarms:
        named += alarm.sensors
    return list(dict.fromkeys(named))[:MAX_UNIT_SENSORS]


def _group_members(results: UnitResults) -> dict[str, list[str]]:
    """Group ID to the sensors the run lists for it: every sensor of the groups the drift stage
    follows, and the sensors of the unit's risk features that name a group."""
    members: dict[str, list[str]] = {}
    if results.drift is not None:
        for group in results.drift.groups:
            members[group.group_id] = list(group.sensors)
    if results.risk is not None:
        for feature in results.risk.top:
            if feature.group_id is not None:
                listed = members.setdefault(feature.group_id, [])
                if feature.sensor not in listed:
                    listed.append(feature.sensor)
    return members


def _share_sum(shares: dict[str, float], sensors: Iterable[str]) -> float | None:
    found = [shares[s] for s in sensors if s in shares]
    return min(1.0, sum(found)) if found else None


def _z_of(results: UnitResults) -> dict[str, float | None]:
    charts, chart = results.charts, results.chart
    if charts is None or chart is None or chart.z is None:
        return {}
    return {sensor: chart.z[i] for i, sensor in enumerate(charts.features) if i < len(chart.z)}


def _groups(results: UnitResults, members: dict[str, list[str]]) -> list[GroupDeviation]:
    t2 = {c.sensor: c.share for c in results.chart.top_t2} if results.chart else {}
    spe = {c.sensor: c.share for c in results.chart.top_spe} if results.chart else {}
    z = _z_of(results)
    drift = {g.group_id: g for g in results.drift.groups} if results.drift else {}
    out: list[GroupDeviation] = []
    for group_id, sensors in members.items():
        shap_values = (
            [f.shap for f in results.risk.top if f.group_id == group_id] if results.risk else []
        )
        zs = [(abs(v), s) for s in sensors if (v := z.get(s)) is not None]
        top_z = max(zs, default=None)
        g = drift.get(group_id)
        at = results.index
        out.append(
            GroupDeviation(
                group_id=group_id,
                sensors=sensors,
                shap=sum(shap_values) if shap_values else None,
                t2_share=_share_sum(t2, sensors),
                spe_share=_share_sum(spe, sensors),
                max_abs_z=top_z[0] if top_z else None,
                max_abs_z_sensor=top_z[1] if top_z else None,
                ewma=g.ewma[at] if g and at < len(g.ewma) else None,
                ewma_limit=g.ewma_limit if g else None,
                cusum_upper=g.cusum_upper[at] if g and at < len(g.cusum_upper) else None,
                cusum_lower=g.cusum_lower[at] if g and at < len(g.cusum_lower) else None,
                cusum_h=g.cusum_h if g else None,
                first_ewma_alarm=g.first_ewma_alarm if g else None,
                first_cusum_alarm=g.first_cusum_alarm if g else None,
            )
        )

    def weight(group: GroupDeviation) -> tuple[float, float]:
        return (max(group.t2_share or 0.0, group.spe_share or 0.0), abs(group.shap or 0.0))

    return sorted(out, key=weight, reverse=True)[:MAX_UNIT_GROUPS]


def _readings(
    results: UnitResults, unit: SensorUnitInput | None, members: dict[str, list[str]]
) -> list[SensorReading]:
    t2 = {c.sensor: c.share for c in results.chart.top_t2} if results.chart else {}
    spe = {c.sensor: c.share for c in results.chart.top_spe} if results.chart else {}
    z = _z_of(results)
    group_of = {s: g for g, sensors in reversed(members.items()) for s in sensors}
    features = results.risk.top if results.risk else []
    health = {h.sensor: h for h in results.drift.health} if results.drift else None
    out = []
    for sensor in _unit_sensors(results):
        value_shap = [f.shap for f in features if f.sensor == sensor and not f.indicator]
        indicator_shap = [f.shap for f in features if f.sensor == sensor and f.indicator]
        item = health.get(sensor) if health is not None else None
        out.append(
            SensorReading(
                sensor=sensor,
                value=unit.readings[_sensor_index(sensor)] if unit else None,
                z=z.get(sensor),
                group_id=group_of.get(sensor),
                t2_share=t2.get(sensor),
                spe_share=spe.get(sensor),
                shap=value_shap[0] if value_shap else None,
                missing_indicator_shap=indicator_shap[0] if indicator_shap else None,
                health=None if health is None else (item.status if item else "ok"),
                health_reasons=item.reasons if item else [],
            )
        )
    return out


def run_unit_evidence(
    run: Run, index: int, unit: SensorUnitInput | None, chart: UnitChartResult | None
) -> RunUnitEvidence:
    if not 0 <= index < run.units:
        raise NotFoundError(
            f"Run {run.run_id} has {run.units} sensor units"
            + (f" (positions 0 to {run.units - 1})" if run.units else "")
            + f"; there is none at position {index}."
        )
    results = unit_results(run, index, chart)
    members = _group_members(results)
    risk_stage, charts = results.risk_stage, results.charts
    if unit is not None:
        label = unit.unit_id
    elif results.risk is not None:
        label = results.risk.unit_id
    elif results.chart is not None:
        label = results.chart.unit_id
    else:
        raise NotFoundError(f"Unit {index} of run {run.run_id} has no stored input or result.")
    notes = _missing(run, ("sensor_risk", "control_charts", "drift_health"))
    notes.append(
        "Group shares add the shares of the group's sensors among the unit's listed T² and SPE "
        "contributions; a group's sensors are all those of the groups the drift stage follows, "
        "else only the sensors of its listed risk features."
    )
    if unit is not None and unit.source_unit is not None:
        notes.append(
            f"This is SECOM unit {unit.source_unit}: get_unit, get_risk, get_shap and "
            f"get_contributions read it with unit_id {unit.source_unit}."
        )
    return RunUnitEvidence(
        run_id=run.run_id,
        index=index,
        unit_id=label,
        source_unit=unit.source_unit if unit else None,
        timestamp=unit.timestamp if unit else None,
        recorded_result=unit.result if unit else None,
        risk=results.risk,
        risk_threshold=risk_stage.threshold if risk_stage else None,
        risk_elevated_threshold=risk_stage.elevated_threshold if risk_stage else None,
        operating_point=risk_stage.operating_point if risk_stage else None,
        risk_skill=risk_stage.skill if risk_stage else [],
        risk_caution=risk_stage.caution if risk_stage else None,
        chart=results.chart,
        limits=charts.limits if charts else None,
        groups=_groups(results, members),
        sensors=_readings(results, unit, members),
        health_counts=results.drift.health_counts if results.drift else None,
        alarms=list(results.alarms),
        notes=notes,
    )


async def get_run_unit(services: ScienceServices, args: RunUnitArgs) -> RunUnitEvidence:
    run = await read_run(services, args.run_id)
    unit, chart = None, None
    if 0 <= args.unit_index < run.units:
        reader = _reader(services)
        unit = await reader.get_unit_input(args.run_id, args.unit_index)
        chart = await reader.get_unit_chart(args.run_id, args.unit_index)  # with z, any unit
    return run_unit_evidence(run, args.unit_index, unit, chart)


def _num(value: float | None, digits: int = 3) -> str:
    return "not available" if value is None else f"{value:.{digits}g}"


def _run_unit_summary(args: RunUnitArgs, u: RunUnitEvidence) -> str:
    source = f", SECOM unit {u.source_unit}" if u.source_unit is not None else ""
    risk = f"risk {u.risk.risk:.3f} ({u.risk.band})" if u.risk else "no risk result"
    chart = (
        f"T² {_num(u.chart.t2)}, SPE {_num(u.chart.spe)}, FDC level {u.chart.level}"
        if u.chart
        else "no control-chart result"
    )
    return (
        f"Run unit at position {u.index} ({u.unit_id}{source}): {risk}; {chart}; "
        f"{len(u.groups)} sensor groups and {len(u.alarms)} alarms listed."
    )


# -- get_run_wafer and get_run_lot --------------------------------------------------------------


def _cells(wafer_map: WaferMap) -> list[int] | None:
    try:
        raw = base64.b64decode(wafer_map.cells, validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(raw) != wafer_map.height * wafer_map.width:
        return None
    return list(raw)


def radial_profile(
    width: int, positions: Sequence[tuple[int, float]], bands: int = RADIAL_BANDS
) -> list[RadialBand]:
    """Failure by distance from the wafer centre: ``positions`` are (row-major cell, failure in
    0..1) for every die position; the centre is the centroid of the dies and the radius the
    largest distance of a die from it. Bands of equal width from the centre to the edge."""
    if not positions:
        return []
    rows = [cell // width for cell, _ in positions]
    cols = [cell % width for cell, _ in positions]
    cy, cx = sum(rows) / len(rows), sum(cols) / len(cols)
    distances = [math.hypot(r - cy, c - cx) for r, c in zip(rows, cols, strict=True)]
    radius = max(distances)
    counts = [0] * bands
    fails = [0.0] * bands
    for d, (_, failure) in zip(distances, positions, strict=True):
        band = min(int(d / radius * bands), bands - 1) if radius > 0 else 0
        counts[band] += 1
        fails[band] += failure
    return [
        RadialBand(
            inner=i / bands,
            outer=(i + 1) / bands,
            positions=counts[i],
            fail_share=min(1.0, fails[i] / counts[i]) if counts[i] else None,
        )
        for i in range(bands)
    ]


def wafer_radial(wafer_map: WaferMap) -> tuple[int, int, list[RadialBand]] | None:
    """(dies, failed dies, radial profile) of a wafer map; None when the map does not decode."""
    cells = _cells(wafer_map)
    if cells is None:
        return None
    dies = [(i, 1.0 if v == 2 else 0.0) for i, v in enumerate(cells) if v in (1, 2)]
    failed = sum(1 for _, f in dies if f)
    return len(dies), failed, radial_profile(wafer_map.width, dies)


def stacked_radial(stacked: StackedMap | None) -> list[RadialBand]:
    if stacked is None or len(stacked.frequencies) != stacked.height * stacked.width:
        return []
    positions = [(i, f) for i, f in enumerate(stacked.frequencies) if f is not None]
    return radial_profile(stacked.width, positions)


async def _causes(
    services: ScienceServices, stage: WaferSimilarResult | None, label: WaferLabel
) -> tuple[list[PatternCause], list[KnowledgeSource], str | None, str | None]:
    """Literature causes of one pattern: from the run's similar-wafer stage, else from the
    knowledge base. Returns causes, their sources, the framing and a note when none could be read."""
    if label == "none":
        return [], [], None, None
    if stage is not None:
        table = stage.causes
    else:
        try:
            table = await services.knowledge.pattern_causes(label)
        except ServiceError as exc:
            return [], [], None, f"literature causes not read: {exc.detail}"
    causes = [c for c in table.causes if c.label == label]
    quoted = {q.source_id for c in causes for q in c.quotes}
    sources = [s for s in table.sources if s.source_id in quoted]
    return causes, sources, table.framing, None


async def get_run_wafer(services: ScienceServices, args: RunWaferArgs) -> RunWaferEvidence:
    run = await read_run(services, args.run_id)
    index = args.wafer_index
    if not 0 <= index < run.wafers:
        raise NotFoundError(
            f"Run {run.run_id} has {run.wafers} wafers"
            + (f" (positions 0 to {run.wafers - 1})" if run.wafers else "")
            + f"; there is none at position {index}."
        )
    results = wafer_results(run, index)
    pattern = results.pattern
    # The pattern stage carries the processed map and the WM-811K origin; the input is read
    # only for a wafer that stage has no result for.
    wafer = (
        pattern
        if pattern is not None
        else await _reader(services).get_wafer_input(args.run_id, index)
    )
    if wafer is None:
        raise NotFoundError(f"Wafer {index} of run {run.run_id} has no stored input or result.")
    notes = _missing(run, ("wafer_pattern", "wafer_similar", "lot"))
    shape = wafer_radial(wafer.map)
    if shape is None:
        notes.append("the wafer map does not decode, so no radial profile is given")
    similar = results.similar.similar if results.similar else []
    recorded = [s.recorded_label for s in similar if s.recorded_label is not None]
    causes: list[PatternCause] = []
    sources: list[KnowledgeSource] = []
    framing = None
    if pattern is not None:
        causes, sources, framing, failed = await _causes(
            services, results.similar_stage, pattern.top_label
        )
        if failed:
            notes.append(failed)
    if wafer.source_wafer is not None:
        notes.append(
            f"This is WM-811K wafer {wafer.source_wafer}: get_wafer_prediction and "
            f"get_similar_wafers read it with wafer_id {wafer.source_wafer}."
        )
    return RunWaferEvidence(
        run_id=run.run_id,
        index=index,
        lot=wafer.lot,
        wafer=wafer.wafer,
        source_wafer=wafer.source_wafer,
        recorded_label=wafer.label if isinstance(wafer, WaferInput) else wafer.recorded_label,
        pattern=pattern,
        accept_threshold=results.patterns.accept_threshold if results.patterns else None,
        dies=shape[0] if shape else None,
        failed_dies=shape[1] if shape else None,
        fail_share=shape[1] / shape[0] if shape and shape[0] else None,
        radial_profile=shape[2] if shape else [],
        similar=similar,
        similar_recorded_labels=dict(Counter(recorded)),
        similar_unlabelled=len(similar) - len(recorded),
        similar_matching_pattern=sum(r == pattern.top_label for r in recorded) if pattern else None,
        searched=results.similar_stage.searched if results.similar_stage else None,
        precision_at_10=results.similar_stage.precision_at_10 if results.similar_stage else None,
        causes=causes,
        causes_framing=framing,
        sources=sources,
        lot_result=results.lot,
        alarms=list(results.alarms),
        notes=notes,
    )


def _run_wafer_summary(args: RunWaferArgs, w: RunWaferEvidence) -> str:
    source = f", WM-811K wafer {w.source_wafer}" if w.source_wafer else ""
    if w.pattern is None:
        found = "no pattern result"
    else:
        kind = "unknown pattern" if w.pattern.is_unknown else "known pattern"
        found = (
            f"predicted {w.pattern.top_label} with probability {w.pattern.top_probability:.3f} "
            f"({kind})"
        )
    return (
        f"Run wafer at position {w.index} (lot {w.lot}, wafer {w.wafer}{source}): {found}; "
        f"{len(w.similar)} similar wafers; {len(w.causes)} literature causes listed."
    )


async def get_run_lot(services: ScienceServices, args: RunLotArgs) -> RunLotEvidence:
    run = await read_run(services, args.run_id)
    wafers = lot_wafers(run, args.lot)
    item = lot_item(run, args.lot)
    if not wafers and item is None:
        patterns = stage_result(run, WaferPatternResult)
        known = sorted({w.lot for w in patterns.wafers}) if patterns else []
        listed = ", ".join(known[:10]) or "none"
        raise NotFoundError(f"Run {run.run_id} has no lot {args.lot!r}; its lots: {listed}.")
    listed_wafers = []
    for w in wafers[:MAX_LOT_WAFERS]:
        listed_wafers.append(
            LotWafer(
                index=w.index,
                wafer=w.wafer,
                source_wafer=w.source_wafer,
                top_label=w.top_label,
                top_probability=w.top_probability,
                auto_accepted=w.auto_accepted,
                is_unknown=w.is_unknown,
                clustered=w.spatial.clustered if w.spatial else None,
                recorded_label=w.recorded_label,
            )
        )
    indexes = {w.index for w in wafers}
    return RunLotEvidence(
        run_id=run.run_id,
        lot=args.lot,
        result=item,
        stacked_radial_profile=stacked_radial(item.stacked if item else None),
        wafers_total=len(wafers),
        wafers=listed_wafers,
        alarms=[a for a in run.alarms if a.lot == args.lot or a.wafer_index in indexes],
        notes=_missing(run, ("wafer_pattern", "lot")),
    )


def _run_lot_summary(args: RunLotArgs, d: RunLotEvidence) -> str:
    flagged = [t.label for t in d.result.tests if t.flagged] if d.result else []
    tests = (
        f"patterns flagged against the training-period rate: {', '.join(flagged) or 'none'}"
        if d.result
        else "no lot test result"
    )
    return f"Run lot {d.lot}: {d.wafers_total} wafers; {tests}; {len(d.alarms)} alarms."


# -- the tools ----------------------------------------------------------------------------------


RUN_TOOLS: tuple[Tool[Any, Any], ...] = (
    Tool(
        "get_run",
        "Read a run (one submission processed stage by stage): where its input came from, each "
        "stage's status, counts, the highlights of each stage and its alarms.",
        RunArgs,
        get_run,
        lambda a: f"Read run {a.run_id}",
        _run_summary,
        hidden=(
            "/final_test/units",
            "/final_test/wafers",
            "/intake/unmonitored_sensors",
            "/stages/*/elapsed_ms",
            "/alarms/*/run_id",
            "/alarms/*/meaning",
            "/alarms/*/investigation_id",
            "/alarms/*/investigation_status",
        ),
        caps=(("/alarms", 8), ("/lots", 8)),
    ),
    Tool(
        "get_run_unit",
        "Read one sensor unit of a run by position: risk, T² and SPE with their largest sensor "
        "contributions, how far each sensor group deviated and since when (EWMA, CUSUM), sensor "
        "health and the unit's alarms.",
        RunUnitArgs,
        get_run_unit,
        lambda a: f"Read unit {a.unit_index} of run {a.run_id}",
        _run_unit_summary,
        hidden=(
            "/chart/z",
            "/alarms/*/run_id",
            "/alarms/*/meaning",
            "/alarms/*/investigation_id",
            "/alarms/*/investigation_status",
        ),
        caps=(
            ("/risk/top", 8),
            ("/chart/top_t2", 5),
            ("/chart/top_spe", 5),
            ("/groups", 6),
            ("/sensors", 10),
        ),
    ),
    Tool(
        "get_run_wafer",
        "Read one wafer of a run by position: predicted pattern and confidence, unknown score, "
        "spatial clustering, radial failure profile, similar real wafers and their recorded "
        "labels, the literature causes proposed for its pattern, its lot's tests and alarms.",
        RunWaferArgs,
        get_run_wafer,
        lambda a: f"Read wafer {a.wafer_index} of run {a.run_id}",
        _run_wafer_summary,
        hidden=(
            "/pattern/map",
            "/similar/*/map",
            "/lot_result/stacked",
            "/sources/*/authors",
            "/sources/*/url",
            "/alarms/*/run_id",
            "/alarms/*/meaning",
            "/alarms/*/investigation_id",
            "/alarms/*/investigation_status",
        ),
        caps=(("/similar", 5), ("/pattern/probabilities", 3), ("/causes/*/quotes", 1)),
    ),
    Tool(
        "get_run_lot",
        "Read one lot of a run: its pattern-excursion tests against the training-period rate, "
        "the radial profile of its stacked failure map, its wafers and alarms.",
        RunLotArgs,
        get_run_lot,
        lambda a: f"Read lot {a.lot} of run {a.run_id}",
        _run_lot_summary,
        hidden=(
            "/result/stacked",
            "/alarms/*/run_id",
            "/alarms/*/meaning",
            "/alarms/*/investigation_id",
            "/alarms/*/investigation_status",
        ),
        caps=(("/wafers", 12),),
    ),
)


def alarm_item_call(run: Run, alarm_id: str) -> tuple[ToolName, dict[str, object]] | None:
    """The run tool that reads the item an alarm is about (its unit, wafer or lot), or None
    when the alarm does not exist in the run or names no item."""
    alarm = find_alarm(run, alarm_id)
    if alarm is None:
        return None
    if alarm.unit_index is not None:
        return "get_run_unit", {"run_id": run.run_id, "unit_index": alarm.unit_index}
    if alarm.wafer_index is not None:
        return "get_run_wafer", {"run_id": run.run_id, "wafer_index": alarm.wafer_index}
    if alarm.lot is not None:
        return "get_run_lot", {"run_id": run.run_id, "lot": alarm.lot}
    return None
