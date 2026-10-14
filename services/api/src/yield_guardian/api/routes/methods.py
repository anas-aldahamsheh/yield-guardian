from typing import Annotated, Literal

from fastapi import APIRouter, Path

from yield_guardian.api.deps import Methods, Secom, Wafers
from yield_guardian.api.problems import problem_responses
from yield_guardian.contracts.methods import MethodsOverview, ModelCard
from yield_guardian.contracts.secom import SecomMetrics
from yield_guardian.contracts.wafer import WaferMetrics

router = APIRouter(tags=["methods"])


@router.get("/methods", operation_id="get_methods_overview", responses=problem_responses(503))
async def get_methods_overview(methods: Methods) -> MethodsOverview:
    """Datasets with checksums, artifact bundles, model cards and limitations."""
    return await methods.overview()


@router.get("/methods/secom", operation_id="get_secom_metrics", responses=problem_responses(503))
async def get_secom_metrics(secom: Secom) -> SecomMetrics:
    """Every SECOM metric with its confidence interval, baselines and calibration."""
    return await secom.get_metrics()


@router.get("/methods/wafermap", operation_id="get_wafer_metrics", responses=problem_responses(503))
async def get_wafer_metrics(wafers: Wafers) -> WaferMetrics:
    """Every wafer-map metric with its confidence interval, on both splits."""
    return await wafers.get_metrics()


@router.get(
    "/methods/model-cards/{name}",
    operation_id="get_model_card",
    responses=problem_responses(404, 503),
)
async def get_model_card(
    methods: Methods, name: Annotated[Literal["secom", "wafermap"], Path()]
) -> ModelCard:
    return await methods.model_card(name)
