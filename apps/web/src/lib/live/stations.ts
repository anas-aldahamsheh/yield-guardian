import type {
  LotItem,
  LotResult,
  RunAlarm,
  WaferPatternItem,
  WaferPatternResult,
} from "@yield-guardian/contracts";

import { formatInt, formatNumber, formatPercent, formatPValue, plural } from "@/lib/format";
import { patternName } from "@/lib/labels";

import { STAGES, stageResult, type RunState, type StageId } from "./run-state";
import type { Station } from "./url-state";

/**
 * What each station says under it: one sentence and one number, written by code from the
 * stage results. Grey "needs data" when its stages were skipped, amber while computing, calm
 * when done, red when one of its stages raised an alarm.
 */

export type StationTone = "idle" | "needs" | "working" | "ok" | "alarm" | "failed";

export interface StationNumber {
  value: string;
  label: string;
}

export interface StationSummary {
  station: Station;
  name: string;
  tone: StationTone;
  sentence: string;
  number: StationNumber | null;
}

export const STATION_NAME: Record<Station, string> = {
  manufacturing: "Manufacturing",
  monitoring: "Monitoring",
  wafer_test: "Wafer test",
  investigation: "Investigation",
  decision: "Decision",
};

/** Stages each line station draws. final_test belongs to both tracks; it is drawn by its stamp. */
export const STATION_STAGES: Record<
  "manufacturing" | "monitoring" | "wafer_test",
  readonly StageId[]
> = {
  manufacturing: ["intake"],
  monitoring: ["sensor_risk", "control_charts", "drift_health"],
  wafer_test: ["wafer_pattern", "wafer_similar", "lot"],
};

export interface SummaryView {
  /** Whether a stage's result is on screen yet (the animation reveals results in order). */
  shown?: (stage: StageId) => boolean;
  /** Whether an alarm is on screen yet. */
  alarmShown?: (alarm: RunAlarm) => boolean;
}

const always = () => true;

/**
 * Whether an alarm turns its station red. Warnings (a risk above the operating point of a weak
 * model, a slow drift) go to the rail without turning the station red, and an unknown pattern
 * never does: it is the model saying it has not seen this shape, a call for an engineer to look,
 * not a fault.
 */
export function turnsRed(alarm: RunAlarm): boolean {
  return alarm.severity === "alarm" && alarm.kind !== "unknown_pattern";
}

function lineStation(
  state: RunState,
  station: "manufacturing" | "monitoring" | "wafer_test",
  view: Required<SummaryView>,
): { tone: StationTone; needs: string | null; problem: string | null } {
  const stages = STATION_STAGES[station].map((s) => state.stages[s]);
  if (stages.every((s) => s.status === "skipped"))
    return { tone: "needs", needs: stages[0]!.needs, problem: null };
  const failed = stages.find((s) => s.status === "failed");
  const pending = stages.some(
    (s) =>
      s.status === "pending" ||
      s.status === "running" ||
      (s.status === "done" && !view.shown(s.stage)),
  );
  const alarmed = state.alarms.some(
    (a) => STATION_STAGES[station].includes(a.stage) && turnsRed(a) && view.alarmShown(a),
  );
  if (alarmed) return { tone: "alarm", needs: null, problem: failed?.problem?.title ?? null };
  if (pending && state.status !== "failed") return { tone: "working", needs: null, problem: null };
  if (failed)
    return {
      tone: "failed",
      needs: null,
      problem: failed.problem?.detail ?? failed.problem?.title ?? null,
    };
  return { tone: "ok", needs: null, problem: null };
}

function shownResult<S extends StageId>(state: RunState, stage: S, view: Required<SummaryView>) {
  return view.shown(stage) ? stageResult(state, stage) : null;
}

/**
 * A skipped stage's `needs` after its subject. The API writes either a phrase ("needs wafer
 * maps") or a sentence of its own ("Drift and sensor health need a timestamp on every unit; …");
 * a phrase follows the subject, a sentence stands as it is. No final full stop.
 */
export function needsText(
  subject: string,
  needs: string | null | undefined,
  fallback: string,
): string {
  const text = (needs ?? fallback).trim().replace(/\.$/, "");
  const phrase = /^needs\s+/i.exec(text);
  return phrase ? `${subject} needs ${text.slice(phrase[0].length)}` : text;
}

/** A skipped station's `needs` as a sentence: "needs wafer maps" reads "Needs wafer maps." */
export function needsSentence(needs: string | null | undefined, fallback: string): string {
  const text = (needs ?? fallback).trim().replace(/\.$/, "");
  return `${upperFirst(text)}.`;
}

function manufacturing(state: RunState, view: Required<SummaryView>): StationSummary {
  const base = lineStation(state, "manufacturing", view);
  const intake = shownResult(state, "intake", view);
  if (!intake) {
    return {
      station: "manufacturing",
      name: STATION_NAME.manufacturing,
      tone: base.tone,
      sentence: "Reading the input.",
      number: null,
    };
  }
  const parts: string[] = [];
  if (intake.units > 0) {
    parts.push(
      `${plural(intake.units, "unit")} of ${formatInt(intake.sensors)} sensors, ${formatPercent(intake.missing_share)} of readings missing`,
    );
  }
  if (intake.wafers > 0)
    parts.push(`${plural(intake.wafers, "wafer")} in ${plural(intake.lots, "lot")}`);
  const sentence = `${parts.join("; ")}.`;
  const number: StationNumber =
    intake.units > 0
      ? { value: formatInt(intake.units), label: intake.units === 1 ? "unit read" : "units read" }
      : {
          value: formatInt(intake.wafers),
          label: intake.wafers === 1 ? "wafer read" : "wafers read",
        };
  return {
    station: "manufacturing",
    name: STATION_NAME.manufacturing,
    tone: base.tone,
    sentence,
    number,
  };
}

function monitoring(state: RunState, view: Required<SummaryView>): StationSummary {
  const base = lineStation(state, "monitoring", view);
  const name = STATION_NAME.monitoring;
  if (base.tone === "needs")
    return {
      station: "monitoring",
      name,
      tone: "needs",
      sentence: needsSentence(base.needs, "needs sensor data"),
      number: null,
    };
  const charts = shownResult(state, "control_charts", view);
  const risk = shownResult(state, "sensor_risk", view);
  const drift = shownResult(state, "drift_health", view);
  const parts: string[] = [];
  let number: StationNumber | null = null;
  if (charts) {
    const out = charts.units.filter((u) => u.level === "alarm").length;
    const total = charts.units.length;
    parts.push(
      out === 0
        ? `All ${plural(total, "unit")} within the 99.9% control limits`
        : `${formatInt(out)} of ${plural(total, "unit")} beyond the 99.9% control limits`,
    );
    number = {
      value: formatInt(out),
      label: out === 1 ? "unit out of control" : "units out of control",
    };
  }
  if (risk) {
    const above = risk.units.filter((u) => u.above_threshold).length;
    parts.push(`${plural(above, "unit")} above the risk threshold (weak model)`);
    number ??= {
      value: formatInt(above),
      label: above === 1 ? "unit above risk threshold" : "units above risk threshold",
    };
  }
  if (drift) {
    const drifting = drift.groups.filter(
      (g) => g.first_ewma_alarm != null || g.first_cusum_alarm != null,
    ).length;
    parts.push(
      drifting === 0
        ? "no drift in the leading sensor groups"
        : `drift in ${plural(drifting, "sensor group")}`,
    );
  } else if (state.stages.drift_health.status === "skipped" && state.stages.drift_health.needs) {
    parts.push(
      lowerFirst(needsText("drift", state.stages.drift_health.needs, "needs units in time order")),
    );
  }
  const sentence = parts.length
    ? `${upperFirst(parts.join("; "))}.`
    : (base.problem ?? "Computing.");
  return { station: "monitoring", name, tone: base.tone, sentence, number };
}

function waferTest(state: RunState, view: Required<SummaryView>): StationSummary {
  const base = lineStation(state, "wafer_test", view);
  const name = STATION_NAME.wafer_test;
  if (base.tone === "needs")
    return {
      station: "wafer_test",
      name,
      tone: "needs",
      sentence: needsSentence(base.needs, "needs wafer maps"),
      number: null,
    };
  const pattern = shownResult(state, "wafer_pattern", view);
  const lot = shownResult(state, "lot", view);
  const parts: string[] = [];
  let number: StationNumber | null = null;
  if (lot) {
    for (const item of lot.lots) {
      const repeated = item.tests.filter((t) => t.flagged && t.label !== "none");
      for (const t of repeated) {
        parts.push(
          `${patternName(t.label)} repeats across ${item.lot} (q ${formatPValue(t.q_value)})`,
        );
      }
    }
    const flagged = lot.lots.filter((l) => l.flagged).length;
    number = { value: formatInt(flagged), label: flagged === 1 ? "lot flagged" : "lots flagged" };
  } else if (state.stages.lot.status === "skipped" && pattern) {
    parts.push(
      lowerFirst(
        needsText(
          "the lot test",
          state.stages.lot.needs,
          "needs at least two wafers of the same lot",
        ),
      ),
    );
  }
  let caution = "";
  if (pattern) {
    // The counts follow the lot test, so the station and the lot's alarm say the same; until
    // the lot test has answered, the station only says how many maps were read.
    const lotSettled =
      lot != null || state.stages.lot.status === "skipped" || state.stages.lot.status === "failed";
    if (lotSettled) {
      const counts = patternCounts(pattern.wafers, lot);
      const defect = counts.reduce((n, [, c]) => n + c, 0);
      parts.push(patternClause(defect, pattern.wafers.length, counts));
      number ??= {
        value: formatInt(defect),
        label: defect === 1 ? "wafer with a defect pattern" : "wafers with a defect pattern",
      };
    } else {
      parts.push(`${plural(pattern.wafers.length, "wafer map")} read`);
    }
    const unknown = pattern.wafers.filter((w) => w.is_unknown).length;
    if (unknown) caution = ` ${unknownSentence(unknown)}`;
  }
  const sentence = parts.length
    ? `${upperFirst(parts.join("; "))}.${caution}`
    : (base.problem ?? "Computing.");
  return { station: "wafer_test", name, tone: base.tone, sentence, number };
}

type WaferLabel = WaferPatternItem["top_label"];

/**
 * Wafers by pattern as the lot test counts them, most frequent first: the model's predicted
 * pattern, except that in a tested lot a wafer whose energy score is above the bundle's threshold
 * counts as unknown (the lot test's rule; its method says so). A wafer of a lot the test did not
 * cover counts as its predicted pattern. The Mahalanobis unknown score shown with each wafer is a
 * caution next to the prediction (check the map by eye), not a replacement.
 */
export function patternCounts(
  wafers: readonly WaferPatternItem[],
  lot?: LotResult | null,
): [WaferLabel, number][] {
  const counts = new Map<WaferLabel, number>();
  const add = (label: WaferLabel, n: number) => {
    if (label !== "none" && n > 0) counts.set(label, (counts.get(label) ?? 0) + n);
  };
  const tested = new Set(lot?.lots.map((l) => l.lot) ?? []);
  for (const item of lot?.lots ?? []) {
    for (const [label, n] of Object.entries(item.pattern_counts)) add(label as WaferLabel, n);
  }
  for (const w of wafers) if (!tested.has(w.lot)) add(w.top_label, 1);
  return [...counts].sort(
    (a, b) => b[1] - a[1] || patternName(a[0]).localeCompare(patternName(b[0])),
  );
}

/**
 * Whether the lot test counts this wafer as unknown, not as the defect pattern the model
 * predicted: its energy score is above the result's energy threshold (the lot test's rule, as
 * the training-period reference rates had it). Only a wafer of a lot the test covered is
 * counted at all.
 */
export function countsAsUnknown(w: WaferPatternItem, pattern: WaferPatternResult): boolean {
  return w.top_label !== "none" && w.energy_score > pattern.energy_threshold;
}

/** Wafers of a lot the lot test counts as unknown although the model predicted a defect pattern. */
export function energyUnknown(pattern: WaferPatternResult, item: LotItem): number {
  return pattern.wafers.filter((w) => w.lot === item.lot && countsAsUnknown(w, pattern)).length;
}

/** The lots the lot test covered, once its result is in. */
export function testedLots(lot: LotResult | null | undefined): ReadonlySet<string> {
  return new Set(lot?.lots.map((l) => l.lot) ?? []);
}

/**
 * Two numbers with as few decimals (2 to 6) as keep them apart, so "a is above b" never reads
 * as two equal numbers.
 */
export function formatApart(a: number, b: number): [string, string] {
  for (let digits = 2; digits < 6; digits += 1) {
    const pair: [string, string] = [formatNumber(a, digits), formatNumber(b, digits)];
    if (pair[0] !== pair[1]) return pair;
  }
  return [formatNumber(a, 6), formatNumber(b, 6)];
}

function patternClause(defect: number, total: number, counts: [WaferLabel, number][]): string {
  if (!defect)
    return total === 1
      ? "the wafer shows no defect pattern"
      : `none of the ${formatInt(total)} wafers shows a defect pattern`;
  const of = `${formatInt(defect)} of ${plural(total, "wafer")} ${defect === 1 ? "shows" : "show"}`;
  const named = (items: [WaferLabel, number][]) =>
    listJoin(items.map(([label, n]) => `${patternName(label)} (${formatInt(n)})`));
  if (counts.length === 1) return `${of} ${patternName(counts[0]![0])}`;
  if (counts.length <= 3) return `${of} a defect pattern: ${named(counts)}`;
  const top = counts.filter(([, n]) => n === counts[0]![1]);
  const each = top.length > 1 ? " each" : "";
  return `${of} a defect pattern, most often ${listJoin(top.map(([label]) => patternName(label)))} (${formatInt(counts[0]![1])}${each})`;
}

function listJoin(items: string[]): string {
  return items.length <= 1
    ? (items[0] ?? "")
    : `${items.slice(0, -1).join(", ")} and ${items.at(-1)}`;
}

/** The caution for maps that score unknown, as a sentence. */
export function unknownSentence(unknown: number): string {
  return unknown === 1
    ? "1 wafer looks unlike the maps the model learned from, so check it by eye."
    : `${formatInt(unknown)} wafers look unlike the maps the model learned from, so check those by eye.`;
}

function upperFirst(s: string): string {
  return s ? s[0]!.toUpperCase() + s.slice(1) : s;
}

function lowerFirst(s: string): string {
  return s ? s[0]!.toLowerCase() + s.slice(1) : s;
}

/** The three line stations (investigation and decision are summarised by their own panel). */
export function summarizeLine(state: RunState | null, view: SummaryView = {}): StationSummary[] {
  const v: Required<SummaryView> = {
    shown: view.shown ?? always,
    alarmShown: view.alarmShown ?? always,
  };
  if (!state) {
    return (["manufacturing", "monitoring", "wafer_test"] as const).map((station) => ({
      station,
      name: STATION_NAME[station],
      tone: "idle" as const,
      sentence: IDLE_SENTENCE[station],
      number: null,
    }));
  }
  return [manufacturing(state, v), monitoring(state, v), waferTest(state, v)];
}

/** What a station says while the run's stored results are read (a reload of a large run). */
export const READING_SENTENCE = "Reading this run's stored result.";

/**
 * The three line stations while the run's stored state is read: nothing is computing, so no
 * station says it is, nor that it is waiting for the input.
 */
export function readingLine(): StationSummary[] {
  return (["manufacturing", "monitoring", "wafer_test"] as const).map((station) => ({
    station,
    name: STATION_NAME[station],
    tone: "idle" as const,
    sentence: READING_SENTENCE,
    number: null,
  }));
}

const IDLE_SENTENCE: Record<"manufacturing" | "monitoring" | "wafer_test", string> = {
  manufacturing: "Waiting for input: sensor units, wafer maps or both.",
  monitoring: "Scores each unit for failure risk and charts its sensors against control limits.",
  wafer_test: "Reads each wafer map for a defect pattern and tests the lot for repeats.",
};

/** Every stage whose result has arrived, in contract order. */
export function arrivedStages(state: RunState): StageId[] {
  return STAGES.filter((s) => state.stages[s].status === "done");
}

/** What the line is doing, in one calm line under the stations; it says when nothing more will arrive. */
export function lineStatus(state: RunState, over: boolean): string {
  if (!over) return "Running: each station shows its result as it arrives.";
  if (state.status === "failed") {
    const problem = Object.values(state.stages).find((stage) => stage.status === "failed")?.problem;
    const why = problem?.detail ?? problem?.title;
    return `The run stopped${why ? `: ${why.replace(/\.$/, "")}` : ""}. Nothing more will arrive; the stations keep what finished.`;
  }
  return "The run is finished: every station has its result, and nothing more will arrive.";
}
