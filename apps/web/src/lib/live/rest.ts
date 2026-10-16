import {
  stageResult,
  type ControlChartsView,
  type DriftHealthView,
  type GroupDriftView,
  type RunState,
  type SensorRiskView,
  type WaferPatternView,
} from "./run-state";
import type { Focus } from "./url-state";

/**
 * Which unit and which wafer the Line page shows of a run when nothing moves: the instruments'
 * rest unit and wafer, the item a station's drawer opens on, and the drift group the console
 * draws. The page draws them, and the server, sending the run's stored state with the page,
 * keeps their details in it.
 */

/** Severity order of the line's statistics against their limits, for choosing a unit to show. */
function chartSeverity(state: RunState, index: number): number {
  const charts = stageResult(state, "control_charts");
  const unit = charts?.units[index];
  if (!unit || !charts) return 0;
  return Math.max(unit.t2 / charts.limits.t2_999, unit.spe / charts.limits.spe_999);
}

/**
 * The unit the instruments rest on: the one asked for, else the unit of the first sensor alarm
 * of the most severe kind, else the last unit.
 */
export function restUnit(state: RunState, focus: Focus): number | null {
  const units = state.units ?? stageResult(state, "intake")?.units ?? 0;
  const count =
    stageResult(state, "control_charts")?.units.length ??
    stageResult(state, "sensor_risk")?.units.length ??
    units;
  if (!count) return null;
  if (focus?.kind === "unit" && focus.index < count) return focus.index;
  const sensorAlarms = state.alarms.filter((a) => a.unit_index != null);
  const severe = sensorAlarms.filter((a) => a.severity === "alarm");
  const pick = (severe.length ? severe : sensorAlarms)
    .map((a) => a.unit_index!)
    .sort((a, b) => chartSeverity(state, b) - chartSeverity(state, a) || a - b)[0];
  return pick ?? count - 1;
}

/** The wafer the prober rests on: the one asked for, else the first unknown-pattern or flagged wafer, else the last. */
export function restWafer(state: RunState, focus: Focus): number | null {
  const pattern = stageResult(state, "wafer_pattern");
  const count = pattern?.wafers.length ?? 0;
  if (!count || !pattern) return null;
  if (focus?.kind === "wafer" && focus.index < count) return focus.index;
  const flagged = new Set(
    stageResult(state, "lot")?.lots.flatMap((l) =>
      l.tests.filter((t) => t.flagged).map((t) => t.label),
    ) ?? [],
  );
  const repeat = pattern.wafers.find((w) => flagged.has(w.top_label) && !w.is_unknown);
  return repeat?.index ?? count - 1;
}

/**
 * The unit the monitoring drawer opens on without one chosen: the first unit beyond the 99.9%
 * limits, else the unit with the highest risk.
 */
export function defaultUnit(charts: ControlChartsView | null, risk: SensorRiskView | null): number {
  const alarm = charts?.units.findIndex((u) => u.level === "alarm") ?? -1;
  if (alarm !== -1) return alarm;
  if (!risk?.units.length) return 0;
  return risk.units.reduce((best, u, i, all) => (u.risk > all[best]!.risk ? i : best), 0);
}

/** The wafer the wafer-test drawer opens on without one chosen: the first with a pattern, known or not. */
export function defaultWafer(pattern: WaferPatternView): number | null {
  if (!pattern.wafers.length) return null;
  const marked = pattern.wafers.findIndex((w) => w.is_unknown || w.top_label !== "none");
  return marked === -1 ? 0 : marked;
}

/** The unit the monitoring drawer shows: the one asked for, else its default. */
export function drawerUnit(state: RunState, focus: Focus): number | null {
  const charts = stageResult(state, "control_charts");
  const risk = stageResult(state, "sensor_risk");
  const count = charts?.units.length ?? risk?.units.length ?? 0;
  if (!count) return null;
  return focus?.kind === "unit" && focus.index < count ? focus.index : defaultUnit(charts, risk);
}

/** The wafer the wafer-test drawer shows: the one asked for, else its default. */
export function drawerWafer(state: RunState, focus: Focus): number | null {
  const pattern = stageResult(state, "wafer_pattern");
  if (!pattern) return null;
  return focus?.kind === "wafer" && focus.index < pattern.wafers.length
    ? focus.index
    : defaultWafer(pattern);
}

/** The leading group whose EWMA moved furthest relative to its limit (the console draws it). */
export function leadingDrift(drift: DriftHealthView | null): GroupDriftView | null {
  if (!drift?.groups.length) return null;
  const score = (g: GroupDriftView) =>
    Math.max(0, ...(g.ewma ?? []).map((v) => Math.abs(v))) / g.ewma_limit;
  return drift.groups.reduce((best, g) => (score(g) > score(best) ? g : best));
}
