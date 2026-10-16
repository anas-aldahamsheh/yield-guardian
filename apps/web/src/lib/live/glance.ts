import type { Run } from "@yield-guardian/contracts";

import { drawerUnit, drawerWafer, leadingDrift, restUnit, restWafer } from "./rest";
import {
  runStateFrom,
  type ControlChartsView,
  type DriftHealthView,
  type LotView,
  type SensorRiskView,
  type StageId,
  type StageResults,
  type StoredRunData,
  type WaferPatternView,
  type WaferSimilarView,
} from "./run-state";
import type { LineUrlState } from "./url-state";

/**
 * A run's stored state in the compact form the Line page's first paint carries (a reload, a
 * link, another device of the workspace), so the page arrives showing it whatever the run's
 * size, without putting megabytes into the HTML.
 *
 * Every stage, every count and every alarm (with its investigation) is there as stored, and so
 * is everything about the unit and the wafer the page shows: the instruments' rest unit and
 * wafer, and the item the open drawer shows. Left out (null) are the bulk of the run, which is
 * read just after the page has loaded and drawn in place, with nothing replayed: the per-die
 * arrays (every other wafer's map and probabilities, the similar wafers' maps, the lots'
 * stacked maps), every other unit's details (its largest contributions and readings), and the
 * drift series no station draws then (the CUSUM series, and the EWMA of every group but the one
 * the console draws, unless the monitoring drawer is open).
 */
export interface Glance {
  run: StoredRunData;
  /** The stages whose result was made compact: the page reads them in full after hydration. */
  partial: StageId[];
}

export type GlanceView = Pick<LineUrlState, "station" | "focus">;

/** Station numbers of the drawers that show one unit or one wafer in detail. */
const MONITORING = 2;
const WAFER_TEST = 3;

export function glanceOf(run: Run, view: GlanceView): Glance {
  const state = runStateFrom(run);
  const units = kept(
    restUnit(state, view.focus),
    view.station === MONITORING ? drawerUnit(state, view.focus) : null,
  );
  const wafers = kept(
    restWafer(state, view.focus),
    view.station === WAFER_TEST ? drawerWafer(state, view.focus) : null,
  );
  const keep: Keep = { units, wafers, drift: view.station === MONITORING };
  const partial: StageId[] = [];
  const stages = run.stages.map((stage) => {
    if (stage.status !== "done" || !stage.result) return stage;
    const result = compact(stage.result as StageResults[StageId], keep);
    if (result === stage.result) return stage;
    partial.push(stage.stage);
    return { ...stage, result };
  });
  return { run: { ...run, stages }, partial };
}

/** What the first paint shows in full: these units and wafers, and every drift series or not. */
interface Keep {
  units: ReadonlySet<number>;
  wafers: ReadonlySet<number>;
  drift: boolean;
}

function kept(...indexes: (number | null)[]): ReadonlySet<number> {
  return new Set(indexes.filter((i): i is number => i != null));
}

/** The stage's result without what the first paint does not show; the same object if nothing. */
function compact(result: StageResults[StageId], keep: Keep): StageResults[StageId] {
  switch (result.stage) {
    case "sensor_risk":
      return sensorRisk(result, keep.units);
    case "control_charts":
      return controlCharts(result, keep.units);
    case "drift_health":
      return driftHealth(result, keep.drift);
    case "wafer_pattern":
      return waferPattern(result, keep.wafers);
    case "wafer_similar":
      return waferSimilar(result, keep.wafers);
    case "lot":
      return lot(result);
    default:
      return result;
  }
}

/** `list` with `change` applied to each item, or `list` itself when no item changed. */
function mapped<T>(list: T[], change: (item: T, i: number) => T): T[] {
  let changed = false;
  const out = list.map((item, i) => {
    const next = change(item, i);
    if (next !== item) changed = true;
    return next;
  });
  return changed ? out : list;
}

function sensorRisk(result: SensorRiskView, units: ReadonlySet<number>): SensorRiskView {
  const list = mapped(result.units, (u, i) =>
    units.has(i) || u.top == null ? u : { ...u, top: null },
  );
  return list === result.units ? result : { ...result, units: list };
}

function controlCharts(result: ControlChartsView, units: ReadonlySet<number>): ControlChartsView {
  const list = mapped(result.units, (u, i) =>
    units.has(i) || (u.top_t2 == null && u.top_spe == null && u.z == null)
      ? u
      : { ...u, top_t2: null, top_spe: null, z: null },
  );
  return list === result.units ? result : { ...result, units: list };
}

/**
 * The CUSUM series are drawn nowhere (their first signal is); of the EWMA series, the console
 * draws the leading group's, and the monitoring drawer every group's.
 */
function driftHealth(result: DriftHealthView, all: boolean): DriftHealthView {
  const leading = leadingDrift(result);
  const list = mapped(result.groups, (g) => {
    const ewma = all || g === leading ? g.ewma : null;
    if (ewma === g.ewma && g.cusum_upper == null && g.cusum_lower == null) return g;
    return { ...g, ewma, cusum_upper: null, cusum_lower: null };
  });
  return list === result.groups ? result : { ...result, groups: list };
}

function waferPattern(result: WaferPatternView, wafers: ReadonlySet<number>): WaferPatternView {
  const list = mapped(result.wafers, (w, i) =>
    wafers.has(i) || (w.map == null && w.probabilities == null)
      ? w
      : { ...w, map: null, probabilities: null },
  );
  return list === result.wafers ? result : { ...result, wafers: list };
}

/** The shown wafers keep their similar wafers (without the maps); the others list none yet. */
function waferSimilar(result: WaferSimilarView, wafers: ReadonlySet<number>): WaferSimilarView {
  const list = mapped(result.wafers, (w) => {
    if (w.similar == null) return w;
    if (!wafers.has(w.index)) return { ...w, similar: null };
    const similar = mapped(w.similar, (s) => (s.map == null ? s : { ...s, map: null }));
    return similar === w.similar ? w : { ...w, similar };
  });
  return list === result.wafers ? result : { ...result, wafers: list };
}

/** Stacked maps without their frequencies; `peak` keeps the legend's end where it will be. */
function lot(result: LotView): LotView {
  const list = mapped(result.lots, (l) => {
    const stacked = l.stacked;
    if (!stacked?.frequencies) return l;
    let peak = 0;
    for (const v of stacked.frequencies) if (v != null && v > peak) peak = v;
    return { ...l, stacked: { ...stacked, frequencies: null, peak } };
  });
  return list === result.lots ? result : { ...result, lots: list };
}
