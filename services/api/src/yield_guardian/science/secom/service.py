"""SecomService on a verified SECOM bundle: risk, explanations, FDC, sensor groups and health.

Every value comes from the bundle or the SECOM source files. Units after the plant clock's
position have not come off the line and are never returned.
"""

import base64
from collections import Counter
from collections.abc import Sequence
from typing import Protocol

import numpy as np

from yield_guardian.bundles.secom import N_SENSORS, SecomBundle, sensor_column, sensor_id
from yield_guardian.contracts.line import FdcAlarmLevel, RiskBand
from yield_guardian.contracts.secom import (
    Explanation,
    FdcContribution,
    FdcContributions,
    FdcLimits,
    FdcPoint,
    FdcSeries,
    FdcStatistic,
    GroupContribution,
    HealthCounts,
    HealthWindow,
    MissingnessTest,
    OperatingPoints,
    SecomMetrics,
    SensorGroup,
    SensorGroups,
    SensorHealth,
    SensorHealthReport,
    SensorPoint,
    SensorReference,
    SensorSeries,
    SensorStatus,
    ShapContribution,
    UnitDetail,
    UnitPage,
    UnitRisk,
)
from yield_guardian.contracts.services import InvalidArgumentError, NotFoundError
from yield_guardian.replay.line import LineReplay

GROUP_WORDING = (
    "These sensor groups are associated with failure in this data. Association is not causation: "
    "confirm with an engineering check before acting."
)
RISK_NOTES = {
    None: "No out-of-sample prediction exists for this unit: it falls in the warm-up period "
    "before the first rolling-origin fold.",
    "oof": "Predicted by a model trained only on earlier units (rolling-origin).",
    "validation": "The calibrator was fit on the validation block, so calibration is in-sample "
    "for this unit.",
    "test": "Predicted by the final model on the held-out test block.",
}


class UnitInvestigations(Protocol):
    async def for_unit(self, unit_id: int) -> list[str]:
        """IDs of the investigations about one unit, newest first."""
        ...


class NoUnitInvestigations:
    async def for_unit(self, unit_id: int) -> list[str]:
        return []


def _encode(sequence: int) -> str:
    return base64.urlsafe_b64encode(f"u:{sequence}".encode()).decode().rstrip("=")


def _decode(cursor: str) -> int:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        prefix, sequence = raw.split(":")
        if prefix != "u":
            raise ValueError(prefix)
        return int(sequence)
    except (ValueError, UnicodeDecodeError) as error:
        raise InvalidArgumentError("The cursor is not valid; start again without it.") from error


def _level(value: float, limit_99: float, limit_999: float) -> FdcAlarmLevel:
    return "alarm" if value > limit_999 else "warning" if value > limit_99 else "none"


def _number(value: float) -> float | None:
    return None if value != value else float(value)


class SecomInference:
    def __init__(
        self,
        bundle: SecomBundle,
        line: LineReplay,
        investigations: UnitInvestigations | None = None,
    ) -> None:
        self.bundle = bundle
        self.line = line
        self.investigations = investigations or NoUnitInvestigations()
        self.timeline = bundle.timeline
        self.group_of = {s: g.group_id for g in bundle.groups.groups for s in g.sensors}
        self.health_of = {h.sensor: h for h in bundle.health.sensors}
        self.model_sensors = sorted(set(bundle.shap.feature_sensors))

    # Visibility -------------------------------------------------------------------------------

    def _position(self) -> int:
        return self.line.clock().position

    def _sequence(self, unit_id: int, position: int) -> int:
        if not 0 <= unit_id < len(self.timeline):
            raise NotFoundError(
                f"Unit {unit_id} does not exist; SECOM has units 0 to {len(self.timeline) - 1}."
            )
        sequence = int(self.timeline.sequence_of[unit_id])
        if sequence > position:
            raise NotFoundError(f"Unit {unit_id} has not come off the line yet.")
        return sequence

    @staticmethod
    def _range(from_seq: int | None, to_seq: int | None, position: int) -> range:
        if from_seq is not None and to_seq is not None and from_seq > to_seq:
            raise InvalidArgumentError("from_seq must not be greater than to_seq.")
        last = position if to_seq is None else min(to_seq, position)
        return range(from_seq or 0, last + 1)

    # Units and risk ---------------------------------------------------------------------------

    async def list_units(
        self,
        *,
        from_seq: int | None = None,
        to_seq: int | None = None,
        band: RiskBand | None = None,
        cursor: str | None = None,
        limit: int = 200,
    ) -> UnitPage:
        position = self._position()
        sequences = [
            s
            for s in self._range(from_seq, to_seq, position)
            if band is None or self.timeline.risk_band[s] == band
        ]
        start = 0
        if cursor is not None:
            after = _decode(cursor)
            start = next((i for i, s in enumerate(sequences) if s > after), len(sequences))
        page = sequences[start : start + limit]
        more = start + limit < len(sequences)
        return UnitPage(
            items=[self.line.summary(s, position) for s in page],
            next_cursor=_encode(page[-1]) if more and page else None,
            total=len(sequences),
        )

    def _risk(self, sequence: int) -> UnitRisk:
        t = self.timeline
        risk = _number(float(t.risk[sequence]))
        op = self.line.operating_point
        return UnitRisk(
            unit_id=int(t.unit_id[sequence]),
            block=t.block[sequence],
            risk=risk,
            risk_source=t.risk_source[sequence],
            risk_band=t.risk_band[sequence],
            operating_point=op,
            above_threshold=None if risk is None else risk >= op.threshold,
            note=RISK_NOTES[t.risk_source[sequence]],
        )

    async def get_risk(self, unit_id: int) -> UnitRisk:
        return self._risk(self._sequence(unit_id, self._position()))

    async def get_unit(self, unit_id: int) -> UnitDetail:
        position = self._position()
        sequence = self._sequence(unit_id, position)
        readings = self.bundle.source.readings[unit_id]
        measured = int(np.isfinite(readings).sum())
        return UnitDetail(
            **self.line.summary(sequence, position).model_dump(),
            risk_detail=self._risk(sequence),
            sensors_measured=measured,
            sensors_missing=N_SENSORS - measured,
            explanation_available=not bool(np.isnan(self.bundle.shap.values[unit_id]).all()),
            alarms=await self.line.alarms_for(sequence, position),
            investigation_ids=await self.investigations.for_unit(unit_id),
        )

    # Explanations -----------------------------------------------------------------------------

    async def get_explanation(self, unit_id: int, *, top_k: int = 15) -> Explanation:
        sequence = self._sequence(unit_id, self._position())
        shap = self.bundle.shap
        values = shap.values[unit_id].astype(np.float64)
        if np.isnan(values).all():
            raise NotFoundError(
                f"Unit {unit_id} has no out-of-sample explanation: it falls in the warm-up period."
            )
        values = np.nan_to_num(values, nan=0.0)
        readings = self.bundle.source.readings[unit_id]
        order = np.argsort(-np.abs(values), kind="stable")
        shown = order[:top_k]
        contributions = []
        for j in shown.tolist():
            sensor = shap.feature_sensors[j]
            reading = float(readings[sensor_column(sensor)])
            indicator = shap.feature_is_indicator[j]
            contributions.append(
                ShapContribution(
                    feature=shap.features[j],
                    sensor=sensor,
                    kind="missing_indicator" if indicator else "reading",
                    value=float(reading != reading) if indicator else _number(reading),
                    shap=float(values[j]),
                    group_id=self.group_of.get(sensor),
                )
            )
        by_group: dict[str, float] = {}
        for j, sensor in enumerate(shap.feature_sensors):
            group = self.group_of.get(sensor)
            if group is not None:
                by_group[group] = by_group.get(group, 0.0) + float(values[j])
        members = {g.group_id: g.sensors for g in self.bundle.groups.groups}
        groups = [
            GroupContribution(group_id=g, sensors=members[g], shap=v)
            for g, v in sorted(by_group.items(), key=lambda item: -abs(item[1]))
        ]
        base = float(shap.base_values[unit_id])
        risk = _number(float(self.timeline.risk[sequence]))
        return Explanation(
            unit_id=unit_id,
            risk=risk,
            base_value=base,
            raw_score=base + float(values.sum()),
            contributions=contributions,
            other_features=len(values) - len(shown),
            other_shap=float(values[order[top_k:]].sum()),
            groups=groups,
            method=self.bundle.methods.explanation,
        )

    async def get_feature_groups(
        self, *, significant_only: bool = False, limit: int = 20
    ) -> SensorGroups:
        file = self.bundle.groups
        threshold = file.method.stability_threshold
        significant = [g for g in file.groups if g.significant]
        chosen = significant if significant_only else file.groups
        return SensorGroups(
            method=file.method,
            groups=[
                SensorGroup(
                    group_id=g.group_id,
                    sensors=g.sensors,
                    representative=g.representative,
                    importance=g.importance,
                    stability=g.stability,
                    p_value=g.p_value,
                    q_value=g.q_value,
                    significant=g.significant,
                    stable=g.stability >= threshold,
                    univariate=g.univariate,
                )
                for g in chosen[:limit]
            ],
            sensors_total=len(self.model_sensors),
            significant_groups=len(significant),
            sensors_in_significant_groups=sum(len(g.sensors) for g in significant),
            wording=GROUP_WORDING,
        )

    # Fault detection --------------------------------------------------------------------------

    async def get_fdc_series(
        self, *, from_seq: int | None = None, to_seq: int | None = None
    ) -> FdcSeries:
        t = self.timeline
        fdc = self.bundle.fdc
        position = self._position()
        return FdcSeries(
            limits=FdcLimits(
                t2_99=fdc.limits[0],
                t2_999=fdc.limits[1],
                spe_99=fdc.limits[2],
                spe_999=fdc.limits[3],
            ),
            n_components=fdc.n_components,
            explained_variance=self.bundle.fdc_explained_variance,
            features=len(fdc.features),
            reference=self.bundle.fdc_reference,
            points=[
                FdcPoint(
                    unit_id=int(t.unit_id[s]),
                    sequence=s,
                    timestamp=t.timestamp[s],
                    t2=float(t.t2[s]),
                    spe=float(t.spe[s]),
                    fdc_alarm=t.fdc_alarm[s],
                    fdc_period=t.fdc_period[s],
                    ewma_alarm=bool(t.ewma_alarm[s]),
                    cusum_alarm=bool(t.cusum_alarm[s]),
                )
                for s in self._range(from_seq, to_seq, position)
            ],
            method=self.bundle.methods.fdc,
        )

    async def get_contributions(
        self, unit_id: int, *, statistic: FdcStatistic = "t2", top_k: int = 15
    ) -> FdcContributions:
        sequence = self._sequence(unit_id, self._position())
        t = self.timeline
        fdc = self.bundle.fdc
        if statistic == "t2":
            row = fdc.contrib_t2[unit_id].astype(np.float64)
            value = float(t.t2[sequence])
            limit_99, limit_999 = float(t.t2_limit_99[sequence]), float(t.t2_limit_999[sequence])
        else:
            row = fdc.contrib_spe[unit_id].astype(np.float64)
            value = float(t.spe[sequence])
            limit_99, limit_999 = float(t.spe_limit_99[sequence]), float(t.spe_limit_999[sequence])
        row = np.nan_to_num(row, nan=0.0)
        positive = np.clip(row, 0.0, None)
        total = float(positive.sum())
        shares = positive / total if total > 0 else np.zeros_like(positive)
        order = np.argsort(-row, kind="stable")[:top_k]
        readings = self.bundle.source.readings[unit_id]
        contributions = [
            FdcContribution(
                sensor=fdc.features[j],
                contribution=float(row[j]),
                share=float(shares[j]),
                value=_number(float(readings[sensor_column(fdc.features[j])])),
                reference_median=_number(float(fdc.reference_medians[j])),
            )
            for j in order.tolist()
        ]
        return FdcContributions(
            unit_id=unit_id,
            statistic=statistic,
            value=value,
            limit_99=limit_99,
            limit_999=limit_999,
            alarm=_level(value, limit_99, limit_999),
            contributions=contributions,
            other_share=float(min(1.0, max(0.0, 1.0 - float(shares[order].sum())))),
            method=self.bundle.methods.contributions,
        )

    # Sensor health ----------------------------------------------------------------------------

    async def get_sensor_health(
        self,
        *,
        sensors: Sequence[str] | None = None,
        statuses: Sequence[SensorStatus] | None = None,
    ) -> SensorHealthReport:
        health = self.bundle.health
        if sensors is not None:
            unknown = [s for s in sensors if s not in self.health_of]
            if unknown:
                raise InvalidArgumentError(f"Unknown sensor IDs: {', '.join(unknown[:10])}.")
        position = self._position()
        plant_time = self.timeline.timestamp[position]
        started = [w.start <= plant_time for w in health.windows]
        wanted = set(sensors) if sensors is not None else None
        report = [
            SensorHealth(
                sensor=h.sensor,
                status=h.status,
                reasons=h.reasons,
                missing_rate=h.missing_rate,
                missing_by_window=[
                    rate if started[i] else None for i, rate in enumerate(h.missing_by_window)
                ],
                flatline_windows=h.flatline_windows,
                stuck_value=h.stuck_value,
                jump_unit_ids=[
                    u
                    for u in h.jump_unit_ids
                    if 0 <= u < len(self.timeline) and self.timeline.sequence_of[u] <= position
                ],
                out_of_reference_rate=h.out_of_reference_rate,
                missing_vs_failure=None
                if h.missing_vs_failure is None
                else MissingnessTest(**h.missing_vs_failure.model_dump()),
            )
            for h in health.sensors
            if (wanted is None or h.sensor in wanted) and (statuses is None or h.status in statuses)
        ]
        counts = Counter(h.status for h in health.sensors)
        return SensorHealthReport(
            windows=[
                HealthWindow(window_id=w.window_id, start=w.start, end=w.end, units=len(w.unit_ids))
                for w in health.windows
            ],
            sensors=report,
            counts=HealthCounts(
                ok=counts["ok"],
                watch=counts["watch"],
                maintenance=counts["maintenance"],
                dead=counts["dead"],
            ),
            rules=health.rules,
        )

    async def get_sensor_series(
        self, sensor: str, *, from_seq: int | None = None, to_seq: int | None = None
    ) -> SensorSeries:
        try:
            column = sensor_column(sensor)
        except ValueError as error:
            raise NotFoundError(f"{sensor} is not a SECOM sensor (S001 to S590).") from error
        health = self.health_of.get(sensor_id(column))
        if health is None:
            raise NotFoundError(f"The bundle has no health record for {sensor}.")
        t = self.timeline
        readings = self.bundle.source.readings[:, column]
        reference_values = readings[self.bundle.fdc.reference_unit_ids]
        reference_values = reference_values[np.isfinite(reference_values)]
        reference = (
            SensorReference(
                median=float(np.median(reference_values)),
                q01=float(np.quantile(reference_values, 0.01)),
                q99=float(np.quantile(reference_values, 0.99)),
            )
            if reference_values.size
            else None
        )
        position = self._position()
        return SensorSeries(
            sensor=sensor,
            status=health.status,
            group_id=self.group_of.get(sensor),
            reference=reference,
            points=[
                SensorPoint(
                    unit_id=int(t.unit_id[s]),
                    sequence=s,
                    timestamp=t.timestamp[s],
                    value=_number(float(readings[int(t.unit_id[s])])),
                )
                for s in self._range(from_seq, to_seq, position)
            ],
        )

    # Model results ----------------------------------------------------------------------------

    async def get_operating_points(self) -> OperatingPoints:
        return self.bundle.operating_points

    async def get_metrics(self) -> SecomMetrics:
        return self.bundle.metrics
