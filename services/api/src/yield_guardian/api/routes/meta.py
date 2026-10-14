from fastapi import APIRouter

from yield_guardian import __version__
from yield_guardian.api.deps import Methods, Registry
from yield_guardian.api.problems import problem_responses
from yield_guardian.contracts.meta import Features, Health, Meta, Readiness, ReadinessCheck
from yield_guardian.contracts.methods import MeasuredResults

router = APIRouter(tags=["meta"])


@router.get("/health", operation_id="get_health")
async def get_health() -> Health:
    """Liveness: the process answers."""
    return Health(status="ok")


@router.get("/ready", operation_id="get_readiness", responses=problem_responses(503))
async def get_readiness(registry: Registry) -> Readiness:
    """Readiness: bundles verified, database reachable, services loaded."""
    checks = [
        ReadinessCheck(
            name="secom_bundle",
            ok=registry.secom is not None,
            detail=registry.problems.get("secom_bundle"),
        ),
        ReadinessCheck(
            name="wafermap_bundle",
            ok=registry.wafer is not None,
            detail=registry.problems.get("wafermap_bundle"),
        ),
        ReadinessCheck(
            name="database",
            ok=bool(registry.database_ok),
            detail=None if registry.database_ok is not None else "not configured",
        ),
    ]
    return Readiness(ready=all(c.ok for c in checks), checks=checks)


@router.get("/meta", operation_id="get_meta")
async def get_meta(registry: Registry) -> Meta:
    llm_ready = registry.llm is not None and await registry.llm.live_calls_available()
    return Meta(
        app_name=registry.settings.app_name,
        version=__version__,
        git_commit=registry.settings.git_commit,
        started_at=registry.started_at,
        bundles=registry.bundles,
        features=Features(
            live_investigations=llm_ready and registry.runner is not None,
            chat=llm_ready and registry.chat is not None,
            admin_login=registry.settings.admin_username is not None,
        ),
    )


@router.get("/results", operation_id="get_measured_results", responses=problem_responses(503))
async def get_measured_results(methods: Methods) -> MeasuredResults:
    """The measured-results table. A row's estimate is null until it is measured on held-out data."""
    return await methods.results()
