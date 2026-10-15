import type { RunEvent } from "@yield-guardian/contracts";

import { restScene } from "@/components/story/scene";

import { RUN_ID, sampleEvents, snapshotOf } from "../../../e2e/story/fixture";

import { glanceOf } from "./glance";
import { drawerUnit, drawerWafer, restUnit, restWafer } from "./rest";
import {
  applyRunEvent,
  applyRunGlance,
  emptyRunState,
  fillIn,
  runStateFrom,
  stageResult,
} from "./run-state";

const events = sampleEvents as RunEvent[];
const run = snapshotOf(events);
const full = runStateFrom(run);
const AT_REST = { station: null, focus: null };

/** The rows of a list without the fields a glance may leave out, to compare what it keeps. */
function without<T extends object>(rows: readonly T[], keys: readonly string[]) {
  return rows.map((row) =>
    Object.fromEntries(Object.entries(row).filter(([key]) => !keys.includes(key))),
  );
}

describe("the compact first paint of a stored run", () => {
  it("keeps every stage, count and alarm, and every unit's and wafer's own values", () => {
    const { run: glance } = glanceOf(run, AT_REST);
    expect(glance.alarms).toEqual(run.alarms);
    expect({ ...glance, stages: null }).toEqual({ ...run, stages: null });
    expect(glance.stages.map((s) => [s.stage, s.status])).toEqual(
      run.stages.map((s) => [s.stage, s.status]),
    );
    const state = applyRunGlance(emptyRunState(RUN_ID), glance, []);
    const risk = ["top"];
    const charts = ["top_t2", "top_spe", "z"];
    const maps = ["map", "probabilities"];
    expect(without(stageResult(state, "sensor_risk")!.units, risk)).toEqual(
      without(stageResult(full, "sensor_risk")!.units, risk),
    );
    expect(without(stageResult(state, "control_charts")!.units, charts)).toEqual(
      without(stageResult(full, "control_charts")!.units, charts),
    );
    expect(without(stageResult(state, "wafer_pattern")!.wafers, maps)).toEqual(
      without(stageResult(full, "wafer_pattern")!.wafers, maps),
    );
    for (const stage of ["intake", "drift_health", "final_test"] as const) {
      expect(stageResult(state, stage)).toEqual(stageResult(full, stage));
    }
  });

  it("keeps the details of the unit and the wafer the instruments rest on, and only those", () => {
    const { run: glance, partial } = glanceOf(run, AT_REST);
    const state = applyRunGlance(emptyRunState(RUN_ID), glance, partial);
    const unit = restUnit(full, null)!;
    const wafer = restWafer(full, null)!;
    expect(restUnit(state, null)).toBe(unit);
    expect(restWafer(state, null)).toBe(wafer);
    const risk = stageResult(state, "sensor_risk")!.units;
    expect(risk[unit]).toEqual(stageResult(full, "sensor_risk")!.units[unit]);
    expect(risk.filter((u) => u.top != null)).toHaveLength(1);
    const charts = stageResult(state, "control_charts")!.units;
    expect(charts[unit]).toEqual(stageResult(full, "control_charts")!.units[unit]);
    expect(charts.filter((u) => u.top_t2 != null || u.z != null)).toHaveLength(1);
    const wafers = stageResult(state, "wafer_pattern")!.wafers;
    expect(wafers[wafer]).toEqual(stageResult(full, "wafer_pattern")!.wafers[wafer]);
    expect(wafers.filter((w) => w.map != null)).toHaveLength(1);
    // The similar wafers of the wafer shown are listed (their maps come after); no others yet.
    const similar = stageResult(state, "wafer_similar")!.wafers;
    const shown = similar.find((w) => w.index === wafer)!;
    expect(shown.similar!.map((s) => ({ ...s, map: null }))).toEqual(
      stageResult(full, "wafer_similar")!
        .wafers.find((w) => w.index === wafer)!
        .similar!.map((s) => ({ ...s, map: null })),
    );
    expect(similar.filter((w) => w.similar != null)).toHaveLength(1);
    expect(partial.sort()).toEqual(
      ["control_charts", "lot", "sensor_risk", "wafer_pattern", "wafer_similar"].sort(),
    );
  });

  it("keeps what the open drawer shows: its unit or its wafer", () => {
    const station2 = glanceOf(run, { station: 2, focus: null }).run;
    const unit = drawerUnit(full, null)!;
    const s2 = applyRunGlance(emptyRunState(RUN_ID), station2, []);
    expect(stageResult(s2, "control_charts")!.units[unit]).toEqual(
      stageResult(full, "control_charts")!.units[unit],
    );
    expect(stageResult(s2, "sensor_risk")!.units[unit]).toEqual(
      stageResult(full, "sensor_risk")!.units[unit],
    );

    const focus = { kind: "wafer" as const, index: 2 };
    const station3 = glanceOf(run, { station: 3, focus }).run;
    const s3 = applyRunGlance(emptyRunState(RUN_ID), station3, []);
    expect(drawerWafer(s3, focus)).toBe(2);
    expect(stageResult(s3, "wafer_pattern")!.wafers[2]).toEqual(
      stageResult(full, "wafer_pattern")!.wafers[2],
    );
    // Without a wafer chosen, the drawer's own first wafer is kept as well.
    const opened = glanceOf(run, { station: 3, focus: null }).run;
    const s4 = applyRunGlance(emptyRunState(RUN_ID), opened, []);
    const first = drawerWafer(full, null)!;
    expect(stageResult(s4, "wafer_pattern")!.wafers[first]!.map).not.toBeNull();
  });

  it("keeps the stacked maps' highest share, where the legend ends", () => {
    const state = applyRunGlance(emptyRunState(RUN_ID), glanceOf(run, AT_REST).run, []);
    const lots = stageResult(state, "lot")!.lots.filter((l) => l.stacked);
    expect(lots.length).toBeGreaterThan(0);
    for (const lot of lots) {
      const whole = stageResult(full, "lot")!.lots.find((l) => l.lot === lot.lot)!.stacked!;
      expect(lot.stacked!.frequencies).toBeNull();
      expect(lot.stacked!.peak).toBe(Math.max(0, ...whole.frequencies!.map((v) => v ?? 0)));
    }
  });

  it("draws the line at rest exactly as the full run does", () => {
    for (const view of [
      AT_REST,
      { station: 2, focus: { kind: "unit" as const, index: 7 } },
      { station: 3, focus: { kind: "wafer" as const, index: 4 } },
    ]) {
      const glance = glanceOf(run, view);
      const state = applyRunGlance(emptyRunState(RUN_ID), glance.run, glance.partial);
      expect(restScene(state, view.focus)).toEqual(restScene(full, view.focus));
    }
  });

  it("is a small part of the run", () => {
    const glance = glanceOf(run, AT_REST);
    const size = JSON.stringify(glance).length;
    expect(size).toBeLessThan(JSON.stringify(run).length / 3);
  });

  it("leaves a run with nothing to leave out as it is", () => {
    const early = snapshotOf(events.slice(0, 3));
    const glance = glanceOf(early, AT_REST);
    expect(glance.partial).toEqual([]);
    expect(glance.run).toEqual(early);
  });
});

describe("filling in a compact first paint", () => {
  it("becomes the full run, with nothing queued to play", () => {
    const glance = glanceOf(run, AT_REST);
    const shown = applyRunGlance(emptyRunState(RUN_ID), glance.run, glance.partial);
    const filled = fillIn(shown, run);
    expect(filled.partial.size).toBe(0);
    expect(filled.stages).toEqual(full.stages);
    expect(filled.alarms).toEqual(full.alarms);
    expect(filled.arrivals).toEqual([]);
    // A second read changes nothing.
    expect(fillIn(filled, run)).toBe(filled);
  });

  it("changes only the stages left out, whatever the stream has brought since", () => {
    const cut = 14;
    const early = snapshotOf(events.slice(0, cut));
    const glance = glanceOf(early, AT_REST);
    let state = applyRunGlance(emptyRunState(RUN_ID), glance.run, glance.partial);
    for (const event of events.slice(cut)) state = applyRunEvent(state, event);
    const arrivals = state.arrivals;
    const filled = fillIn(state, run);
    expect(filled.arrivals).toBe(arrivals);
    expect(filled.contiguousSeq).toBe(state.contiguousSeq);
    expect(filled.stages.drift_health).toBe(state.stages.drift_health);
    expect(filled.stages.wafer_pattern).toBe(state.stages.wafer_pattern);
    expect(filled.stages.sensor_risk.result).toEqual(full.stages.sensor_risk.result);
    expect(filled.stages.control_charts.result).toEqual(full.stages.control_charts.result);
  });

  it("does not mark a stage the page already holds in full", () => {
    const glance = glanceOf(run, AT_REST);
    const state = applyRunGlance(full, glance.run, glance.partial);
    expect(state.partial.size).toBe(0);
    expect(state.stages).toEqual(full.stages);
  });
});
