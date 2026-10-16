"""Startup wiring of live runs: the engines for the loaded bundles, the run service, the upload
service and the case catalog. Called by ``bootstrap.build_registry`` after the bundles load.

Runs and uploads live in PostgreSQL: without DATABASE_URL the run routes answer 503 not_ready.
Without an engine, its track is unavailable: a run that needs it says so (503 on create, or a
failed stage), and the catalog leaves out the cases it would find.
"""

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import numpy.typing as npt
import structlog

from yield_guardian.bundles.manifest import BundleError
from yield_guardian.bundles.secom import SecomBundle
from yield_guardian.bundles.wafermap import WafermapBundle
from yield_guardian.contracts.base import LotId, UnitId
from yield_guardian.contracts.knowledge import PatternCauses
from yield_guardian.contracts.services import KnowledgeService, NotReadyError
from yield_guardian.contracts.wafer import WaferLabel
from yield_guardian.knowledge.service import LiteratureKnowledge
from yield_guardian.live.cases import CaseCatalog
from yield_guardian.live.causes import LiteratureCauses
from yield_guardian.live.protocols import PatternCausesSource
from yield_guardian.live.runs import Engines, RunService
from yield_guardian.live.sensor_file import SecomSensorFileParser
from yield_guardian.live.sensors import SecomSensorEngine
from yield_guardian.live.uploads import Attribution, UploadService
from yield_guardian.live.wafer_file import WaferDieFile
from yield_guardian.live.wafer_stats import JoinCount
from yield_guardian.live.wafers import LiveWafers
from yield_guardian.services.registry import ServiceRegistry
from yield_guardian.services.runs import DbRunStore, RunMaintenance

log = structlog.get_logger(__name__)

NO_DATABASE = "runs and uploads need DATABASE_URL (they are kept in PostgreSQL)"
NO_CAUSES = "The literature causes are not available: the knowledge base is not loaded."
NOT_TESTED = JoinCount(bb=0, fails=0, dies=0, expected=None, sd=None, z=None, p=None)


class NoCauses:
    """PatternCausesSource when the knowledge base is not loaded: the similar-wafer stage fails
    with this reason rather than showing no causes as if there were none."""

    def causes(self, labels: Sequence[WaferLabel]) -> PatternCauses:
        raise NotReadyError(NO_CAUSES)


class ScanWafers(LiveWafers):
    """The live wafer engine without the join-count test, for the case catalog's scan of every
    demo wafer (the test costs about 70 ms a wafer; the catalog's rules read only the model's
    outputs, which are the same with or without it)."""

    def spatial(self, grids: Sequence[npt.NDArray[np.uint8]]) -> list[JoinCount]:
        return [NOT_TESTED] * len(grids)


def causes_for(knowledge: KnowledgeService | None) -> PatternCausesSource:
    if isinstance(knowledge, LiteratureKnowledge):
        return LiteratureCauses.from_knowledge(knowledge)
    return NoCauses()


def build_engines(
    secom: SecomBundle | None,
    wafermap: WafermapBundle | None,
    problems: dict[str, str],
    knowledge: KnowledgeService | None = None,
) -> Engines:
    """The engines and file parsers for the loaded bundles; an engine that refuses its bundle
    is left out and `problems` says why."""
    sensors: SecomSensorEngine | None = None
    if secom is not None:
        try:
            sensors = SecomSensorEngine(secom)
        except BundleError as error:
            problems["sensor_engine"] = str(error)[:300]
            log.warning("sensor_engine_not_built", reason=problems["sensor_engine"])
    wafers: LiveWafers | None = None
    if wafermap is not None:
        try:
            wafers = LiveWafers(wafermap, causes_for(knowledge))
        except (BundleError, ValueError) as error:
            problems["wafer_engine"] = str(error)[:300]
            log.warning("wafer_engine_not_built", reason=problems["wafer_engine"])
    return Engines(
        sensors=sensors,
        wafers=wafers,
        sensor_file=SecomSensorFileParser() if sensors is not None else None,
        wafer_file=WaferDieFile() if wafers is not None else None,
    )


def secom_units(bundle: SecomBundle | None) -> tuple[list[UnitId], list[UnitId]]:
    """Every SECOM unit in time order, and the test block (units the risk model never saw)."""
    if bundle is None:
        return [], []
    timeline = bundle.timeline
    units = [int(u) for u in timeline.unit_id.tolist()]
    held_out = [u for u, block in zip(units, timeline.block, strict=True) if block == "test"]
    return units, held_out


def demo_lots(bundle: WafermapBundle | None) -> list[LotId]:
    return sorted(set(bundle.wafers.lot)) if bundle is not None else []


def install_runs(
    registry: ServiceRegistry,
    store: DbRunStore | None,
    *,
    secom: SecomBundle | None,
    wafermap: WafermapBundle | None,
    secom_attribution: Path | None,
    engines: Engines | None = None,
) -> None:
    """Set ``registry.runs`` and ``registry.uploads`` and append their resources (maintenance,
    case catalog, run service: the run service stops first and fails the runs still
    computing)."""
    if store is None:
        registry.problems["runs"] = NO_DATABASE
        return
    found = (
        engines
        if engines is not None
        else build_engines(secom, wafermap, registry.problems, registry.knowledge)
    )
    try:
        attribution = Attribution.load(
            secom_attribution, wafermap.attribution if wafermap is not None else None
        )
    except (OSError, ValueError) as error:
        log.warning("attribution_not_loaded", reason=str(error))
        attribution = Attribution(secom=None, wafermap=None)
    uploads = UploadService(
        store,
        sensor_file=found.sensor_file,
        wafer_file=found.wafer_file,
        sensors=found.sensors,
        wafers=found.wafers,
        attribution=attribution,
    )
    cases = None
    if found.sensors is not None or found.wafers is not None:
        units, held_out = secom_units(secom)
        scan = found.wafers
        if isinstance(scan, LiveWafers):
            scan = ScanWafers(scan.bundle, scan.causes_source)
        cases = CaseCatalog(
            found.sensors,
            found.wafers,
            units=units,
            held_out=held_out,
            lots=demo_lots(wafermap),
            scan_wafers=scan,
        )
    runs = RunService(store, found, cases=cases, uploads=uploads)
    registry.runs = runs
    registry.uploads = uploads
    # The one cleanup loop also ends sessions, handoff codes and workspaces nothing uses.
    pruners = [registry.sessions] if registry.sessions is not None else []
    registry.resources.append(RunMaintenance(store, pruners=pruners))
    if cases is not None:
        registry.resources.append(cases)
    registry.resources.append(runs)
