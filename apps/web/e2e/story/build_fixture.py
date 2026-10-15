"""Test-only: builds the run fixture of the Line page's tests with the API's own run code.

The Line page's tests stub the runs API with the events of real runs (e2e/story/stub.ts). This
script makes those runs the way the API does, in process and without a database: the deployed
bundles (`artifacts/secom/v1`, `artifacts/wafermap/v1`, `data/secom`), the live engines, the
materialiser and the run orchestrator (live/runs.py), with the literature causes of
`docs/knowledge`:

* the sample: SampleRunCreate with the first seed from SEED whose run turns both tracks red (a
  unit beyond the 99.9% limits and a lot excursion), has a pattern the model does not know and a
  recorded failure, on small enough maps to keep the file small;
* sensors only: the same units picked by id (PickRunCreate), so the wafer stages are skipped;
* the case catalog: the API's own scan of the data (live/cases.py);
* the draw layouts: the wafer engine's;
* the upload summaries: the upload service on its own example files, the sensor one with one
  timestamp left out (a warning) and the wafer one with a few errors put in (a die outside the
  map, a result that is not one, a repeated die);
* the 410 problem: the run store's own.

Each stage's elapsed time is what it took here. Standardised readings are rounded to 4 decimals
and six similar wafers are kept per wafer, to keep the file small; nothing else is changed. The
output is validated against contracts/runs.py.

Run from the repository root (the case scan takes about half a minute):
    services/api/.venv/bin/python apps/web/e2e/story/build_fixture.py
"""

import asyncio
import csv
import io
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from yield_guardian.bundles.manifest import verify_bundle
from yield_guardian.bundles.secom import load_secom_bundle
from yield_guardian.bundles.wafermap import load_wafermap_bundle
from yield_guardian.contracts.runs import (
    DrawLayoutItem,
    DrawLayoutList,
    PickRunCreate,
    RunAlarm,
    RunCreated,
    RunEvent,
    RunStartedEvent,
    RunStatus,
    SampleRunCreate,
    StageState,
    UnitChartResult,
    UploadSummary,
)
from yield_guardian.live.cases import CaseCatalog
from yield_guardian.live.causes import LiteratureCauses
from yield_guardian.live.runs import Engines, Materialiser, RunOrchestrator
from yield_guardian.live.sensor_file import SecomSensorFileParser
from yield_guardian.live.sensors import SecomSensorEngine
from yield_guardian.live.uploads import UploadService
from yield_guardian.live.wafer_file import WaferDieFile
from yield_guardian.live.wafers import LiveWafers
from yield_guardian.live.wiring import ScanWafers, demo_lots, secom_units
from yield_guardian.services.runs import RunInput, _expired

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent / "run-fixture.json"

RUN_ID = "run_0storyfixture0sample01"
SENSORS_ID = "run_0storyfixture0sensors1"
SEED = 20261015
MAX_DIES = 1_500  # per wafer: larger maps make the file large
SIMILAR_K = 6  # the contract allows up to 10; six keep the file small


@dataclass
class MemoryWriter:
    """The run store in memory: events get seq 2, 3, ... after run_started (seq 1)."""

    events: list[Any] = field(default_factory=list)
    alarms: list[RunAlarm] = field(default_factory=list)
    statuses: list[RunStatus] = field(default_factory=list)

    async def update(
        self,
        run_id: str,
        *,
        status: RunStatus | None = None,
        stage: StageState | None = None,
        alarms: Sequence[RunAlarm] = (),
        not_listed: int = 0,
        events: Sequence[Callable[[int, datetime], Any]] = (),
        unit_charts: Sequence[UnitChartResult] = (),
    ) -> None:
        if status is not None:
            self.statuses.append(status)
        self.alarms += alarms
        for make in events:
            self.events.append(make(len(self.events) + 2, datetime.now(UTC)))

    async def heartbeat(self, run_id: str) -> None:
        return None


@dataclass
class MemoryUploads:
    """The upload store in memory: keeps nothing, answers with the summary."""

    created: datetime = field(default_factory=lambda: datetime.now(UTC))

    async def create_upload(
        self,
        *,
        kind: str,
        filename: str,
        data: RunInput,
        summary: Callable[[str, datetime], UploadSummary],
    ) -> UploadSummary:
        return summary(f"upl_0storyfixture0{kind}", self.created + timedelta(hours=24))

    async def get_upload(self, upload_id: str) -> tuple[UploadSummary, RunInput]:
        raise NotImplementedError


async def run(
    engines: Engines, run_id: str, payload: Any
) -> tuple[RunCreated, list[RunEvent], RunInput]:
    """A run as the API makes it: materialise, plan, run_started, then the orchestrator."""
    origin, data = await Materialiser(engines, None, None)(payload)
    writer = MemoryWriter()
    orchestrator = RunOrchestrator(engines, writer, heartbeat_s=60)
    plan = orchestrator.plan(data)
    started = RunStartedEvent(
        seq=1, at=datetime.now(UTC), run_id=run_id, origin=origin, stages=list(plan)
    )
    await orchestrator.execute(run_id, data, plan)
    created = RunCreated(run_id=run_id, events_url=f"/api/v1/runs/{run_id}/events", origin=origin)
    return created, [started, *writer.events], data


def kinds(events: list[Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in events:
        if e.type == "alarm":
            key = f"{e.alarm.kind}/{e.alarm.severity}"
            out[key] = out.get(key, 0) + 1
    return out


def wanted(events: list[Any], data: RunInput) -> bool:
    """Both tracks red, an unknown pattern, a recorded failure, small maps."""
    k = kinds(events)
    red_sensors = k.get("t2/alarm", 0) + k.get("spe/alarm", 0) > 0
    red_wafers = k.get("lot_excursion/alarm", 0) > 0
    unknown = any(key.startswith("unknown_pattern") for key in k)
    failed = any(u.result == "fail" for u in data.units)
    small = all(w.map.height * w.map.width <= MAX_DIES * 1.6 for w in data.wafers)
    return red_sensors and red_wafers and unknown and failed and small


def trim(event: dict[str, Any]) -> dict[str, Any]:
    """z to 4 decimals, six similar wafers a wafer."""
    if event.get("type") != "stage_result":
        return event
    result = event["result"]
    if result.get("stage") == "control_charts":
        for unit in result["units"]:
            if unit.get("z") is not None:
                unit["z"] = [None if v is None else round(v, 4) for v in unit["z"]]
    if result.get("stage") == "wafer_similar":
        for item in result["wafers"]:
            item["similar"] = item["similar"][:SIMILAR_K]
    return event


def broken_wafer_file(content: bytes) -> bytes:
    """The real wafer example with three errors put in, the kinds a person makes."""
    rows = list(csv.reader(io.StringIO(content.decode("utf-8"))))
    header, body = rows[0], rows[1:]
    x, result = header.index("x"), header.index("result")
    body[5][x] = "-1"  # a die outside the map
    body[11][result] = "maybe"  # a result that is not one
    body.insert(20, list(body[19]))  # the same die twice
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows([header, *body])
    return out.getvalue().encode("utf-8")


def undated_sensor_file(content: bytes) -> bytes:
    """The real sensor example with one unit's timestamp left out: a warning, still runnable."""
    rows = list(csv.reader(io.StringIO(content.decode("utf-8"))))
    rows[3][rows[0].index("timestamp")] = ""
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(rows)
    return out.getvalue().encode("utf-8")


def dump(model: Any) -> Any:
    return model.model_dump(mode="json")


async def main() -> None:
    secom = load_secom_bundle(
        verify_bundle(ROOT / "artifacts/secom/v1", "secom"), ROOT / "data/secom"
    )
    wafer_bundle = load_wafermap_bundle(verify_bundle(ROOT / "artifacts/wafermap/v1", "wafermap"))
    causes = LiteratureCauses.from_directory(ROOT / "docs/knowledge")
    sensors = SecomSensorEngine(secom)
    wafers = LiveWafers(wafer_bundle, causes)
    engines = Engines(
        sensors=sensors,
        wafers=wafers,
        sensor_file=SecomSensorFileParser(),
        wafer_file=WaferDieFile(),
    )

    # The sample.
    for seed in range(SEED, SEED + 200):
        created, events, data = await run(
            engines, RUN_ID, SampleRunCreate(source="sample", seed=seed)
        )
        print(f"seed {seed}: {kinds(events)}")
        if wanted(events, data):
            break
    else:
        raise SystemExit("no seed in range gives the run the tests need")

    # The same units, picked by id: the wafer stages are skipped.
    sensors_created, sensors_events, _ = await run(
        engines,
        SENSORS_ID,
        PickRunCreate(
            source="pick", unit_ids=[u.source_unit for u in data.units], wafer_ids=[], lot=None
        ),
    )

    # The case catalog, as the API finds it.
    units, held_out = secom_units(secom)
    catalog = CaseCatalog(
        sensors,
        wafers,
        units=units,
        held_out=held_out,
        lots=demo_lots(wafer_bundle),
        scan_wafers=ScanWafers(wafer_bundle, causes),
        wait_s=600,
    )
    cases = await catalog.list()

    layouts = DrawLayoutList(
        items=[
            DrawLayoutItem(
                layout_id=f.layout_id, map=f.map, source_wafer=f.source_wafer, rule=f.rule
            )
            for f in wafers.draw_layouts()
        ]
    )

    uploads = UploadService(
        MemoryUploads(),
        sensor_file=engines.sensor_file,
        wafer_file=engines.wafer_file,
        sensors=sensors,
        wafers=wafers,
    )
    sensor_example = await uploads.example("sensors", "csv")
    wafer_example = await uploads.example("wafers", "csv")
    upload_ok = await uploads.upload(undated_sensor_file(sensor_example.content), "secom-units.csv")
    upload_bad = await uploads.upload(broken_wafer_file(wafer_example.content), "wafer-lot.csv")
    if not upload_ok.runnable or upload_bad.runnable:
        raise SystemExit(
            f"upload summaries not as expected: {upload_ok.issues} {upload_bad.issues}"
        )

    gone = _expired("Run", RUN_ID, events[0].at).problem(instance=f"/api/v1/runs/{RUN_ID}")

    fixture = {
        "_about": (
            "Test-only: real runs made by build_fixture.py with the API's own run code on the real "
            "bundles. Never imported by product code."
        ),
        "created": dump(created),
        "events": [trim(dump(e)) for e in events],
        "sensorsOnly": {
            "created": dump(sensors_created),
            "events": [trim(dump(e)) for e in sensors_events],
        },
        "layouts": dump(layouts),
        "cases": dump(cases),
        "uploadOk": dump(upload_ok),
        "uploadBad": dump(upload_bad),
        "gone": dump(gone),
        "doneAt": events[-1].at.isoformat(),
    }
    OUT.write_text(
        json.dumps(fixture, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KiB): {len(events)} events, {kinds(events)}"
    )


if __name__ == "__main__":
    asyncio.run(main())
