from typing import Annotated

from fastapi import APIRouter, Path, Query

from yield_guardian.api.deps import CurrentSession, Secom
from yield_guardian.api.problems import problem_responses
from yield_guardian.contracts.line import RiskBand
from yield_guardian.contracts.secom import (
    Explanation,
    FdcContributions,
    FdcSeries,
    FdcStatistic,
    OperatingPoints,
    SensorGroups,
    SensorHealthReport,
    SensorSeries,
    SensorStatus,
    UnitDetail,
    UnitPage,
    UnitRisk,
)
from yield_guardian.services.access import viewing

router = APIRouter(tags=["secom"])

UnitPath = Annotated[int, Path(ge=0, description="Row index in secom.data")]
SensorPath = Annotated[str, Path(pattern=r"^S\d{3}$")]
FromSeq = Annotated[int | None, Query(ge=0, description="First sequence number (inclusive).")]
ToSeq = Annotated[
    int | None,
    Query(ge=0, description="Last sequence number (inclusive); default: the last unit."),
]


@router.get("/units", operation_id="list_units", responses=problem_responses(503))
async def list_units(
    secom: Secom,
    from_seq: FromSeq = None,
    to_seq: ToSeq = None,
    band: RiskBand | None = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 200,
) -> UnitPage:
    """Units in time order."""
    return await secom.list_units(
        from_seq=from_seq, to_seq=to_seq, band=band, cursor=cursor, limit=limit
    )


@router.get("/units/{unit_id}", operation_id="get_unit", responses=problem_responses(404, 503))
async def get_unit(secom: Secom, session: CurrentSession, unit_id: UnitPath) -> UnitDetail:
    """The unit with its alarms and the investigations of it, as this workspace sees them."""
    with viewing(session.viewer):
        return await secom.get_unit(unit_id)


@router.get(
    "/units/{unit_id}/risk", operation_id="get_unit_risk", responses=problem_responses(404, 503)
)
async def get_unit_risk(secom: Secom, unit_id: UnitPath) -> UnitRisk:
    return await secom.get_risk(unit_id)


@router.get(
    "/units/{unit_id}/explanation",
    operation_id="get_unit_explanation",
    responses=problem_responses(404, 503),
)
async def get_unit_explanation(
    secom: Secom, unit_id: UnitPath, top: Annotated[int, Query(ge=1, le=100)] = 15
) -> Explanation:
    """TreeSHAP contributions of the unit's risk, in log-odds."""
    return await secom.get_explanation(unit_id, top_k=top)


@router.get(
    "/units/{unit_id}/contributions",
    operation_id="get_unit_contributions",
    responses=problem_responses(404, 503),
)
async def get_unit_contributions(
    secom: Secom,
    unit_id: UnitPath,
    statistic: FdcStatistic = "t2",
    top: Annotated[int, Query(ge=1, le=100)] = 15,
) -> FdcContributions:
    """Per-sensor contributions to the unit's T² or SPE."""
    return await secom.get_contributions(unit_id, statistic=statistic, top_k=top)


@router.get("/fdc/series", operation_id="get_fdc_series", responses=problem_responses(503))
async def get_fdc_series(secom: Secom, from_seq: FromSeq = None, to_seq: ToSeq = None) -> FdcSeries:
    """T² and SPE with control limits, in time order."""
    return await secom.get_fdc_series(from_seq=from_seq, to_seq=to_seq)


@router.get("/sensors/groups", operation_id="get_sensor_groups", responses=problem_responses(503))
async def get_sensor_groups(
    secom: Secom,
    significant_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> SensorGroups:
    """Sensor groups statistically associated with failure (association, not causation)."""
    return await secom.get_feature_groups(significant_only=significant_only, limit=limit)


@router.get("/sensors/health", operation_id="get_sensor_health", responses=problem_responses(503))
async def get_sensor_health(
    secom: Secom,
    status: Annotated[list[SensorStatus] | None, Query()] = None,
    sensor: Annotated[list[str] | None, Query(max_length=590)] = None,
) -> SensorHealthReport:
    return await secom.get_sensor_health(sensors=sensor, statuses=status)


@router.get(
    "/sensors/{sensor}/series",
    operation_id="get_sensor_series",
    responses=problem_responses(404, 503),
)
async def get_sensor_series(
    secom: Secom, sensor: SensorPath, from_seq: FromSeq = None, to_seq: ToSeq = None
) -> SensorSeries:
    return await secom.get_sensor_series(sensor, from_seq=from_seq, to_seq=to_seq)


@router.get(
    "/secom/operating-points", operation_id="get_operating_points", responses=problem_responses(503)
)
async def get_operating_points(secom: Secom) -> OperatingPoints:
    """Test-block performance at thresholds chosen on the validation block."""
    return await secom.get_operating_points()
