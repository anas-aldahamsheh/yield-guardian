"""Builds the running registry from settings: verified bundles, the SECOM alarms, the SECOM and
wafer-map services, the language-model admin, investigator and chat when TOKEN_FACTORY_API_KEY
is set and, when DATABASE_URL is set, the database-backed stores and live runs. A part that
cannot load is left out, so its routes answer 503 not_ready and /ready names the reason."""

from collections.abc import Mapping

import structlog

from yield_guardian.agent.wiring import install_agent
from yield_guardian.bundles.manifest import BundleError, latest_version, verify_bundle
from yield_guardian.bundles.secom import SecomBundle, load_secom_bundle
from yield_guardian.bundles.wafermap import WafermapBundle, load_wafermap_bundle
from yield_guardian.contracts.line import AlarmStatus
from yield_guardian.core.settings import Settings
from yield_guardian.live.wiring import install_runs
from yield_guardian.science.secom.alarms import SecomAlarms
from yield_guardian.science.secom.service import SecomInference
from yield_guardian.science.wafermap.service import WaferInference
from yield_guardian.services.access import current_viewer
from yield_guardian.services.alarms import DbAlarmStateStore
from yield_guardian.services.methods import BundleMethods
from yield_guardian.services.persistence import build_persistence
from yield_guardian.services.registry import ServiceRegistry

log = structlog.get_logger(__name__)


class StoredAlarmStates:
    """The alarm states the workspace of the current request or investigation job set with its
    own investigations; every other alarm is open, and every alarm is open to a request of no
    workspace. One visitor never sees another's activity (services.access)."""

    def __init__(self, store: DbAlarmStateStore) -> None:
        self.store = store

    async def overrides(self) -> Mapping[str, tuple[AlarmStatus, str | None]]:
        viewer = current_viewer()
        if viewer is None or viewer.uuid is None:
            return {}
        return {
            alarm_id: (state.status, state.investigation_id)
            for alarm_id, state in (await self.store.of_workspace(viewer)).items()
        }


def build_registry(settings: Settings) -> ServiceRegistry:
    registry = ServiceRegistry(settings=settings)
    persistence = None
    if settings.database_url is not None:
        persistence = build_persistence(
            settings,
            runner_provider=lambda: registry.runner,
            migrate=settings.migrate_on_start,
        )
        persistence.install(registry)
    # Its resources start after the database (migrated) and before the job worker.
    install_agent(
        registry, settings, sessions=persistence.database.sessionmaker if persistence else None
    )
    loaded: SecomBundle | None = None
    loaded_wafers: WafermapBundle | None = None
    try:
        verified = verify_bundle(latest_version(settings.artifacts_dir, "secom"), "secom")
        bundle = load_secom_bundle(verified, settings.secom_data_dir)
    except (BundleError, OSError) as error:
        registry.problems["secom_bundle"] = str(error)
        log.warning("secom_bundle_not_loaded", reason=str(error))
    else:
        states = StoredAlarmStates(persistence.alarms) if persistence else None
        alarms = SecomAlarms(bundle, states)
        registry.alarms = alarms
        registry.secom = SecomInference(
            bundle, alarms, persistence.investigations if persistence else None
        )
        registry.bundles.append(verified.info)
        loaded = bundle
        log.info("secom_bundle_loaded", version=verified.info.bundle.version)
    try:
        wafer_verified = verify_bundle(
            latest_version(settings.artifacts_dir, "wafermap"), "wafermap"
        )
        wafer_bundle = load_wafermap_bundle(wafer_verified)
        wafer_service = WaferInference(wafer_bundle)
    except Exception as error:  # a broken bundle never stops the API: /ready names the reason
        registry.problems["wafermap_bundle"] = str(error)
        log.warning("wafermap_bundle_not_loaded", reason=str(error))
    else:
        registry.wafer = wafer_service
        registry.bundles.append(wafer_verified.info)
        loaded_wafers = wafer_bundle
        parity = wafer_bundle.parity
        log.info(
            "wafermap_bundle_loaded",
            version=wafer_verified.info.bundle.version,
            wafers=parity.wafers,
            parity_top_label_agreement=parity.top_label_agreement,
            parity_max_confidence_diff=parity.max_confidence_diff,
        )
    if registry.bundles:
        registry.methods = BundleMethods(
            bundles=registry.bundles,
            artifacts_dir=settings.artifacts_dir,
            manifest_path=settings.secom_data_dir.parent / "manifest.json",
            secom=registry.secom,
            wafer=registry.wafer,
        )
    # After every other resource: the run service stops first and fails the runs still computing.
    install_runs(
        registry,
        persistence.runs if persistence else None,
        secom=loaded,
        wafermap=loaded_wafers,
        secom_attribution=settings.secom_data_dir / "ATTRIBUTION.md",
    )
    return registry
