"""Alarm rules of a live run. Code, not a language model, decides when an alarm is raised and
writes its fixed title and its one-sentence meaning; every number in it is a computed value.

Rules, by stage (each alarm is about one unit, one wafer or one lot of the run):

- ``sensor_risk``, kind ``risk`` (warning): the unit's calibrated failure risk is above the
  operating-point threshold. The meaning says the signal is weak on held-out data.
- ``control_charts``, kinds ``t2`` and ``spe``: the statistic is beyond its 99% control limit
  (warning) or its 99.9% limit (alarm); the sensors are the largest contributions.
- ``drift_health``, kinds ``ewma`` and ``cusum`` (warning): the first unit of the run at which a
  sensor group's EWMA or CUSUM signals, one alarm per group and detector.
- ``wafer_pattern``, kind ``unknown_pattern`` (warning): the wafer's unknown score is above its
  threshold; otherwise kind ``wafer_pattern`` (warning) when the predicted pattern is not "none".
- ``lot``, kind ``lot_excursion`` (alarm): a pattern repeats in a lot more often than the
  training-period rate allows (a flagged test, after Benjamini-Hochberg).

Cap: at most 50 alarms are listed per run. They are given out per stage as each result arrives,
so a station turns red as soon as its result is in: ``sensor_risk`` 10, ``control_charts`` 15,
``drift_health`` 10, ``wafer_pattern`` 10, ``lot`` 5. Within a stage the most severe come first:
alarm before warning, then the larger value relative to its limit, then input order. Alarms
beyond a stage's quota are counted in ``alarms_not_listed``; the stage result keeps every value.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from yield_guardian.contracts.runs import (
    ControlChartsResult,
    DriftHealthResult,
    FdcContributionItem,
    LotResult,
    RunAlarmKind,
    RunAlarmSeverity,
    SensorRiskResult,
    SensorUnitInput,
    StageId,
    StageResult,
    UnitChartResult,
    WaferPatternResult,
)

MAX_ALARMS = 50
QUOTAS: dict[StageId, int] = {
    "sensor_risk": 10,
    "control_charts": 15,
    "drift_health": 10,
    "wafer_pattern": 10,
    "lot": 5,
}
assert sum(QUOTAS.values()) == MAX_ALARMS

TITLES: dict[RunAlarmKind, str] = {
    "risk": "Raised failure risk (weak signal)",
    "t2": "Readings far from normal (T²)",
    "spe": "Sensor relationships broke (SPE)",
    "ewma": "Slow drift (EWMA)",
    "cusum": "Sustained shift (CUSUM)",
    "wafer_pattern": "Defect pattern on a wafer",
    "unknown_pattern": "Unknown wafer pattern",
    "lot_excursion": "Pattern repeats across a lot",
}
SENSORS_NAMED = 3
SENSORS_LISTED = 10


@dataclass(frozen=True, slots=True)
class Candidate:
    """An alarm a rule raised, before it is numbered and listed."""

    kind: RunAlarmKind
    severity: RunAlarmSeverity
    meaning: str
    value: float | None
    limit: float | None
    score: float = field(repr=False)
    """Larger is more severe within a severity: the value relative to its limit."""
    order: int = field(repr=False)
    """Input order, the last tie-break."""
    unit_index: int | None = None
    unit_id: str | None = None
    wafer_index: int | None = None
    lot: str | None = None
    sensors: tuple[str, ...] = ()

    @property
    def title(self) -> str:
        return TITLES[self.kind]

    def rank(self) -> tuple[int, float, int]:
        return (0 if self.severity == "alarm" else 1, -self.score, self.order)


def _ratio(value: float, limit: float) -> float:
    return value / limit if limit > 0 else value


def _names(sensors: Sequence[str]) -> str:
    named = list(sensors[:SENSORS_NAMED])
    if len(named) <= 1:
        return "".join(named)
    return ", ".join(named[:-1]) + " and " + named[-1]


def _unique(sensors: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(sensors))[:SENSORS_LISTED]


def risk_alarms(result: SensorRiskResult) -> list[Candidate]:
    skill = next((m for m in result.skill if m.metric == "roc_auc" or m.label == "ROC-AUC"), None)
    measured = f" (held-out ROC-AUC {skill.estimate.value:.2f})" if skill is not None else ""
    found: list[Candidate] = []
    for unit in result.units:
        if not unit.above_threshold:
            continue
        found.append(
            Candidate(
                kind="risk",
                severity="warning",
                meaning=(
                    f"Unit {unit.unit_id}: failure risk {unit.risk:.1%} is above the "
                    f"{result.threshold:.1%} threshold, but this signal is weak{measured}, so "
                    "treat it as a reason to look, not as a prediction."
                ),
                value=unit.risk,
                limit=result.threshold,
                score=_ratio(unit.risk, result.threshold),
                order=unit.index,
                unit_index=unit.index,
                unit_id=unit.unit_id,
                sensors=_unique([f.sensor for f in unit.top]),
            )
        )
    return found


def _chart_alarm(
    unit: UnitChartResult,
    kind: RunAlarmKind,
    value: float,
    limit_99: float,
    limit_999: float,
    top: Sequence[FdcContributionItem],
) -> Candidate | None:
    if value <= limit_99:
        return None
    severe = value > limit_999
    limit = limit_999 if severe else limit_99
    level = "99.9" if severe else "99"
    name, plain = (
        ("T²", "its readings sit unusually far from normal operation")
        if kind == "t2"
        else ("SPE", "its sensors no longer move together as in normal operation")
    )
    sensors = [c.sensor for c in top]
    led = f"; the largest contributions come from {_names(sensors)}" if sensors else ""
    return Candidate(
        kind=kind,
        severity="alarm" if severe else "warning",
        meaning=(
            f"Unit {unit.unit_id}: {name} {value:.1f} is beyond the {level}% control limit "
            f"{limit:.1f}, so {plain}{led}."
        ),
        value=value,
        limit=limit,
        score=_ratio(value, limit),
        order=unit.index,
        unit_index=unit.index,
        unit_id=unit.unit_id,
        sensors=_unique(sensors),
    )


def chart_alarms(result: ControlChartsResult) -> list[Candidate]:
    limits = result.limits
    found: list[Candidate] = []
    for unit in result.units:
        for alarm in (
            _chart_alarm(unit, "t2", unit.t2, limits.t2_99, limits.t2_999, unit.top_t2),
            _chart_alarm(unit, "spe", unit.spe, limits.spe_99, limits.spe_999, unit.top_spe),
        ):
            if alarm is not None:
                found.append(alarm)
    return found


def drift_alarms(result: DriftHealthResult, units: Sequence[SensorUnitInput]) -> list[Candidate]:
    found: list[Candidate] = []
    for order, group in enumerate(result.groups):
        size = f"{len(group.sensors)} sensor{'s' if len(group.sensors) != 1 else ''}"
        first = group.first_ewma_alarm
        if first is not None and first < len(group.ewma) and first < len(units):
            value = group.ewma[first]
            found.append(
                Candidate(
                    kind="ewma",
                    severity="warning",
                    meaning=(
                        f"Sensor group {group.group_id} ({size}): its EWMA crossed the limit "
                        f"{group.ewma_limit:.2f} at unit {units[first].unit_id}, the first sign "
                        "in this run of a small, sustained shift in these sensors."
                    ),
                    value=value,
                    limit=group.ewma_limit,
                    score=_ratio(abs(value), group.ewma_limit),
                    order=order,
                    unit_index=first,
                    unit_id=units[first].unit_id,
                    sensors=_unique(group.sensors),
                )
            )
        first = group.first_cusum_alarm
        if (
            first is not None
            and first < min(len(group.cusum_upper), len(group.cusum_lower))
            and first < len(units)
        ):
            value = max(group.cusum_upper[first], group.cusum_lower[first], key=abs)
            found.append(
                Candidate(
                    kind="cusum",
                    severity="warning",
                    meaning=(
                        f"Sensor group {group.group_id} ({size}): its CUSUM crossed the decision "
                        f"interval h = {group.cusum_h:g} at unit {units[first].unit_id}, a "
                        "sustained shift that began at or before this unit."
                    ),
                    value=value,
                    limit=group.cusum_h,
                    score=_ratio(abs(value), group.cusum_h),
                    order=order,
                    unit_index=first,
                    unit_id=units[first].unit_id,
                    sensors=_unique(group.sensors),
                )
            )
    return found


def pattern_alarms(result: WaferPatternResult) -> list[Candidate]:
    found: list[Candidate] = []
    for wafer in result.wafers:
        where = f"Wafer {wafer.wafer} of lot {wafer.lot}"
        if wafer.is_unknown:
            found.append(
                Candidate(
                    kind="unknown_pattern",
                    severity="warning",
                    meaning=(
                        f"{where} does not match any pattern the model learned (unknown score "
                        f"{wafer.unknown_score:.1f}, above the threshold "
                        f"{wafer.unknown_threshold:.1f}): an engineer should look at the map."
                    ),
                    value=wafer.unknown_score,
                    limit=wafer.unknown_threshold,
                    score=_ratio(wafer.unknown_score, wafer.unknown_threshold),
                    order=wafer.index,
                    wafer_index=wafer.index,
                    lot=wafer.lot,
                )
            )
        elif wafer.top_label != "none":
            decided = (
                "auto-accepted at the 99%-precision threshold"
                if wafer.auto_accepted
                else "below the auto-accept threshold, for review"
            )
            found.append(
                Candidate(
                    kind="wafer_pattern",
                    severity="warning",
                    meaning=(
                        f"{where} shows a {wafer.top_label} pattern ({wafer.top_probability:.0%} "
                        f"probability, {decided}); its literature causes are hypotheses to "
                        "check, not a diagnosis."
                    ),
                    value=wafer.top_probability,
                    limit=result.accept_threshold,
                    score=_ratio(wafer.top_probability, result.accept_threshold),
                    order=wafer.index,
                    wafer_index=wafer.index,
                    lot=wafer.lot,
                )
            )
    return found


def lot_alarms(result: LotResult) -> list[Candidate]:
    found: list[Candidate] = []
    for order, lot in enumerate(result.lots):
        if not lot.flagged:
            continue
        tests = [t for t in lot.tests if t.flagged] or sorted(lot.tests, key=lambda t: t.q_value)[
            :1
        ]
        for test in tests:
            found.append(
                Candidate(
                    kind="lot_excursion",
                    severity="alarm",
                    meaning=(
                        f"Lot {lot.lot}: {test.count} of {test.wafers} wafers show {test.label}, "
                        f"against a training-period rate of {test.expected_rate:.1%} "
                        f"(q = {test.q_value:.2g}): a repeat this large is unlikely to be chance."
                    ),
                    value=test.q_value,
                    limit=None,
                    score=1.0 - test.q_value,
                    order=order,
                    lot=lot.lot,
                )
            )
    return found


def raise_alarms(
    stage: StageId, result: StageResult, units: Sequence[SensorUnitInput]
) -> tuple[list[Candidate], int]:
    """The alarms a stage result raises, most severe first and cut to the stage's quota, and how
    many were left out."""
    match result:
        case SensorRiskResult():
            found = risk_alarms(result)
        case ControlChartsResult():
            found = chart_alarms(result)
        case DriftHealthResult():
            found = drift_alarms(result, units)
        case WaferPatternResult():
            found = pattern_alarms(result)
        case LotResult():
            found = lot_alarms(result)
        case _:
            found = []
    found.sort(key=Candidate.rank)
    quota = QUOTAS.get(stage, 0)
    return found[:quota], max(0, len(found) - quota)
