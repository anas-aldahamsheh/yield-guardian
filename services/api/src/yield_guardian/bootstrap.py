"""Builds the running registry from settings: verified bundles, the line replay, the SECOM service
and, when DATABASE_URL is set, the database-backed stores. A part that cannot load is left out, so
its routes answer 503 not_ready and /ready names the reason."""

from collections.abc import Mapping

import structlog

from yield_guardian.bundles.manifest import BundleError, latest_version, verify_bundle
from yield_guardian.bundles.secom import load_secom_bundle
from yield_guardian.contracts.line import AlarmStatus
from yield_guardian.core.settings import Settings
from yield_guardian.replay.clock import ReplayClock
from yield_guardian.replay.line import LineReplay
from yield_guardian.science.secom.service import SecomInference
from yield_guardian.services.alarms import AlarmStateStore
from yield_guardian.services.persistence import build_persistence
from yield_guardian.services.registry import ServiceRegistry

log = structlog.get_logger(__name__)


class StoredAlarmStates:
    """Alarm states an investigation set. A stored "open" (a failed investigation) falls back to
    the replay's own rule, so the alarm closes by itself like any other."""

    def __init__(self, store: AlarmStateStore) -> None:
        self.store = store

    async def overrides(self) -> Mapping[str, tuple[AlarmStatus, str | None]]:
        return {
            alarm_id: (state.status, state.investigation_id)
            for alarm_id, state in (await self.store.states()).items()
            if state.status != "open"
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
    try:
        verified = verify_bundle(latest_version(settings.artifacts_dir, "secom"), "secom")
        bundle = load_secom_bundle(verified, settings.secom_data_dir)
    except (BundleError, OSError) as error:
        registry.problems["secom_bundle"] = str(error)
        log.warning("secom_bundle_not_loaded", reason=str(error))
    else:
        clock = ReplayClock(
            epoch=settings.replay_epoch,
            seconds_per_unit=settings.replay_seconds_per_unit,
            plant_times=bundle.timeline.timestamp,
            final_test_lag_units=settings.final_test_lag_units,
        )
        states = StoredAlarmStates(persistence.alarms) if persistence else None
        registry.line = LineReplay(bundle, clock, states)
        registry.secom = SecomInference(
            bundle, registry.line, persistence.investigations if persistence else None
        )
        registry.bundles.append(verified.info)
        log.info("secom_bundle_loaded", version=verified.info.bundle.version)
    return registry
