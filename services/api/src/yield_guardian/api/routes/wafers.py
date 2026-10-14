from typing import Annotated

from fastapi import APIRouter, Path, Query

from yield_guardian.api.deps import Wafers
from yield_guardian.api.problems import problem_responses
from yield_guardian.contracts.wafer import (
    LotDetail,
    LotPage,
    SimilarWafers,
    WaferDetail,
    WaferHero,
    WaferLabel,
    WaferPage,
    WaferPrediction,
)

router = APIRouter(tags=["wafers"])

WaferPath = Annotated[str, Path(pattern=r"^[A-Za-z0-9_.]+-\d+$", max_length=80)]
LotPath = Annotated[str, Path(pattern=r"^[A-Za-z0-9_.]+$", max_length=64)]


@router.get("/wafers", operation_id="list_wafers", responses=problem_responses(503))
async def list_wafers(
    wafers: Wafers,
    lot: Annotated[str | None, Query(max_length=64)] = None,
    label: WaferLabel | None = None,
    unknown: bool | None = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> WaferPage:
    """Wafers of the demo set (a derived WM-811K subset with attribution)."""
    return await wafers.list_wafers(
        lot=lot, label=label, unknown=unknown, cursor=cursor, limit=limit
    )


@router.get("/wafers/hero", operation_id="get_hero_wafer", responses=problem_responses(503))
async def get_hero_wafer(wafers: Wafers) -> WaferHero:
    """The real wafer shown on the home page, with the rule that picked it."""
    return await wafers.get_hero()


@router.get("/wafers/{wafer_id}", operation_id="get_wafer", responses=problem_responses(404, 503))
async def get_wafer(wafers: Wafers, wafer_id: WaferPath) -> WaferDetail:
    return await wafers.get_wafer(wafer_id)


@router.get(
    "/wafers/{wafer_id}/prediction",
    operation_id="get_wafer_prediction",
    responses=problem_responses(404, 503),
)
async def get_wafer_prediction(wafers: Wafers, wafer_id: WaferPath) -> WaferPrediction:
    return await wafers.get_prediction(wafer_id)


@router.get(
    "/wafers/{wafer_id}/similar",
    operation_id="get_similar_wafers",
    responses=problem_responses(404, 503),
)
async def get_similar_wafers(
    wafers: Wafers, wafer_id: WaferPath, k: Annotated[int, Query(ge=1, le=50)] = 10
) -> SimilarWafers:
    return await wafers.get_similar(wafer_id, k=k)


@router.get("/lots", operation_id="list_lots", responses=problem_responses(503))
async def list_lots(
    wafers: Wafers,
    flagged_only: bool = False,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> LotPage:
    return await wafers.list_lots(flagged_only=flagged_only, cursor=cursor, limit=limit)


@router.get("/lots/{lot}", operation_id="get_lot", responses=problem_responses(404, 503))
async def get_lot(wafers: Wafers, lot: LotPath) -> LotDetail:
    """Pattern excursion tests and the stacked failure map of one lot."""
    return await wafers.get_lot(lot)
