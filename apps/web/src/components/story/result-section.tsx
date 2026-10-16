"use client";

import {
  decodeWaferCells,
  type FinalTestResult,
  type FinalTestUnit,
  type RunAlarm,
} from "@yield-guardian/contracts";
import { CheckIcon, XIcon } from "lucide-react";
import { useMemo, useState } from "react";

import { ScrollRegion } from "@/components/scroll-region";
import { formatInt, formatPercent, formatProbability, plural } from "@/lib/format";
import { patternName } from "@/lib/labels";
import {
  stageResult,
  type RunState,
  type SensorRiskView,
  type StageId,
  type WaferItem,
} from "@/lib/live/run-state";
import { turnsRed } from "@/lib/live/stations";
import { cn } from "@/lib/utils";

import { alarmPlace, Investigate, lotName, type OnLinked } from "./alarms-rail";

/** Problems listed before "Show all". */
const FIRST_PROBLEMS = 6;

const H3 = "text-[16px] leading-6 font-[630] tracking-[-0.01em] text-ink";
const NOTE = "text-[14px] leading-[22px] text-ink-2";
const SMALL = "text-[12.5px] leading-[18px] text-ink-3";
const ACTION =
  "press inline-flex h-7 items-center gap-1.5 rounded-full px-3 text-[12.5px] leading-none font-[560] text-ink shadow-[inset_0_0_0_1px_var(--hairline-strong)] hover:bg-surface hover:shadow-[inset_0_0_0_1px_var(--edge)]";

/**
 * The run's result under the line: the problems the alarms found, checked against the recorded
 * results where the input has them, then each dataset on its own (SECOM units and WM-811K
 * wafers are never joined): did the warnings predict the units that failed final test, and did
 * the predicted pattern name the recorded one. Every number is the run's; each part fills as the
 * line shows its stage, and nothing on it moves.
 */
export function ResultSection({
  state,
  revealed,
  alarmsShown,
  over,
  onLinked,
  onShowUnit,
}: {
  state: RunState;
  revealed: ReadonlySet<StageId>;
  alarmsShown: ReadonlySet<string>;
  over: boolean;
  onLinked: OnLinked;
  /** Opens the Failure risk station's details on the unit. */
  onShowUnit: (index: number) => void;
}) {
  const finalStage = state.stages.final_test;
  const final = revealed.has("final_test") ? stageResult(state, "final_test") : null;
  // The recorded results are known once final test is shown, or once the line is over without it.
  const finalKnown = final != null || over;
  const risk = revealed.has("sensor_risk") ? stageResult(state, "sensor_risk") : null;
  const pattern = revealed.has("wafer_pattern") ? stageResult(state, "wafer_pattern") : null;
  const hasUnits = (state.units ?? risk?.units.length ?? 0) > 0;
  const hasWafers = (state.wafers ?? pattern?.wafers.length ?? 0) > 0;
  const [tab, setTab] = useState<"problems" | "units" | "wafers">("problems");
  const tabs = [
    { id: "problems" as const, label: "Problems" },
    ...(hasUnits ? [{ id: "units" as const, label: "Units (SECOM)" }] : []),
    ...(hasWafers ? [{ id: "wafers" as const, label: "Wafers (WM-811K)" }] : []),
  ];

  return (
    <section
      aria-labelledby="result-title"
      className="mt-12 border-t border-hairline pt-8 sm:mt-16"
    >
      <h2
        id="result-title"
        className="text-[26px] leading-8 font-[640] tracking-[-0.02em] text-ink [font-stretch:108%] sm:text-[30px] sm:leading-9"
      >
        Result
      </h2>
      <p className={cn(NOTE, "mt-1.5 max-w-[80ch]")}>
        What the line found, next to what really happened. The sensor units and the wafers come from
        different datasets, so each is checked on its own.
      </p>
      {/* One part at a time: a tab per part, the problems first. */}
      <div role="tablist" aria-label="Result" className="mt-6 flex flex-wrap gap-2">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              "press inline-flex h-9 items-center rounded-full px-4 text-[13.5px] font-[560] text-ink-2 shadow-[inset_0_0_0_1px_var(--hairline-strong)] hover:bg-surface-2 hover:text-ink",
              tab === t.id && "lit text-ink",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="mt-4 grid grid-cols-[minmax(0,1fr)] gap-4">
        {tab === "problems" ? (
          <Problems
            state={state}
            alarms={state.alarms.filter((a) => alarmsShown.has(a.alarm_id))}
            final={final}
            finalKnown={finalKnown}
            over={over}
            onLinked={onLinked}
          />
        ) : null}
        {tab === "units" && hasUnits ? (
          <Units
            risk={risk}
            final={final}
            finalKnown={finalKnown}
            stopped={finalStage.status === "failed"}
            onShowUnit={onShowUnit}
          />
        ) : null}
        {tab === "wafers" && hasWafers ? <Wafers wafers={pattern?.wafers ?? null} /> : null}
      </div>
    </section>
  );
}

function Panel({
  id,
  title,
  className,
  children,
}: {
  id: string;
  title: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section
      aria-labelledby={id}
      className={cn(
        "min-w-0 rounded-[24px] bg-surface px-4 py-5 shadow-[inset_0_0_0_1px_var(--hairline),var(--highlight)] sm:px-6",
        className,
      )}
    >
      <h3 id={id} className={H3}>
        {title}
      </h3>
      {children}
    </section>
  );
}

/* Problems found ------------------------------------------------------------------------------ */

type Check =
  | { kind: "confirmed"; detail: string }
  | { kind: "not_confirmed"; detail: string }
  | { kind: "no_record"; detail: string | null }
  | { kind: "waiting" };

const CHECK_WORDS: Record<Check["kind"], string> = {
  confirmed: "Confirmed by final test",
  not_confirmed: "Not confirmed",
  no_record: "No record to check against",
  waiting: "Waiting for final test",
};

/** How far past its limit an alarm is: the larger, the more serious. */
function excess(alarm: RunAlarm): number {
  const { value, limit } = alarm;
  if (value == null || limit == null || limit === 0) return 0;
  // A q-value is more serious the further below its limit it is.
  if (alarm.kind === "lot_excursion") return value > 0 ? limit / value : Infinity;
  return Math.abs(value) / Math.abs(limit);
}

/** Alarms that turn a station red first, then by how far past the limit; ties in raised order. */
function bySeriousness(alarms: RunAlarm[]): RunAlarm[] {
  return alarms
    .map((alarm, order) => ({ alarm, order }))
    .sort(
      (a, b) =>
        Number(turnsRed(b.alarm)) - Number(turnsRed(a.alarm)) ||
        Number(b.alarm.severity === "alarm") - Number(a.alarm.severity === "alarm") ||
        excess(b.alarm) - excess(a.alarm) ||
        a.order - b.order,
    )
    .map((x) => x.alarm);
}

function lowerFirst(s: string): string {
  return s ? s[0]!.toLowerCase() + s.slice(1) : s;
}

/** The pattern a lot alarm is about: the lot test it reports (matched by its q-value). */
function lotLabel(state: RunState, alarm: RunAlarm): string | null {
  const lot = stageResult(state, "lot")?.lots.find((l) => l.lot === alarm.lot);
  if (!lot) return null;
  const test =
    lot.tests.find((t) => t.flagged && t.q_value === alarm.value) ??
    lot.tests.find((t) => t.flagged);
  return test ? patternName(test.label) : null;
}

/** The alarm in plain words, from what it carries and the stage result it points at. */
function problemText(state: RunState, alarm: RunAlarm): string {
  const place = alarmPlace(state, alarm);
  // The control limits' level, as the control-chart stage raises it: 99.9% for an alarm, 99% for
  // a warning.
  const level = alarm.severity === "alarm" ? "99.9%" : "99%";
  const sensors = alarm.sensors?.length ? plural(alarm.sensors.length, "sensor") : "sensors";
  switch (alarm.kind) {
    case "lot_excursion": {
      const label = lotLabel(state, alarm);
      const lot = alarm.lot ? lotName(alarm.lot) : "a lot";
      return label ? `${label} repeats across ${lot}` : `A defect pattern repeats across ${lot}`;
    }
    case "wafer_pattern": {
      const w =
        alarm.wafer_index != null
          ? stageResult(state, "wafer_pattern")?.wafers[alarm.wafer_index]
          : null;
      return w
        ? `${patternName(w.top_label)} pattern on ${lowerFirst(place)}`
        : `A defect pattern on ${lowerFirst(place)}`;
    }
    case "unknown_pattern":
      return `${place} shows a pattern unlike any the model learned`;
    case "t2":
      return `${place} drifted beyond the ${level} control limits`;
    case "spe":
      return `${place}: its sensors stopped moving together, beyond the ${level} control limits`;
    case "risk":
      return `${place} has a raised failure risk${alarm.value != null ? ` of ${formatProbability(alarm.value)}` : ""}`;
    case "ewma":
      return `Slow drift in ${sensors}, first seen at ${lowerFirst(place)}`;
    case "cusum":
      return `Sustained shift in ${sensors}, from ${lowerFirst(place)}`;
    default:
      return alarm.title;
  }
}

/** Alarm kinds about one unit's own result: final test can confirm them. */
const UNIT_KINDS: ReadonlySet<RunAlarm["kind"]> = new Set(["risk", "t2", "spe"]);

/**
 * The alarm against the recorded results: a unit alarm on a unit that failed final test is
 * confirmed, on one that passed it is not; a wafer's pattern is confirmed when the recorded
 * WM-811K label is the same. Drift in a sensor group, a lot and an unknown map have no record.
 */
function checkOf(alarm: RunAlarm, final: FinalTestResult | null, finalKnown: boolean): Check {
  if (!finalKnown) return { kind: "waiting" };
  if (UNIT_KINDS.has(alarm.kind) && alarm.unit_index != null) {
    const row = final?.units.find((u) => u.index === alarm.unit_index);
    if (!row) return { kind: "no_record", detail: "the unit has no recorded final-test result" };
    return row.result === "fail"
      ? { kind: "confirmed", detail: "the unit failed final test" }
      : { kind: "not_confirmed", detail: "the unit passed final test" };
  }
  if (alarm.kind === "wafer_pattern" && alarm.wafer_index != null) {
    const row = final?.wafers.find((w) => w.index === alarm.wafer_index);
    if (!row) return { kind: "no_record", detail: "the wafer has no recorded label" };
    return row.agrees
      ? { kind: "confirmed", detail: `recorded as ${patternName(row.recorded_label)} in WM-811K` }
      : {
          kind: "not_confirmed",
          detail: `recorded as ${patternName(row.recorded_label)} in WM-811K`,
        };
  }
  return { kind: "no_record", detail: null };
}

function CheckMark({ check }: { check: Check }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-block size-2 shrink-0 rounded-full",
        check.kind === "confirmed" && "bg-fail",
        check.kind === "not_confirmed" && "bg-pass",
        check.kind === "no_record" && "shadow-[inset_0_0_0_1.5px_var(--hairline-strong)]",
        check.kind === "waiting" && "bg-ink-3",
      )}
    />
  );
}

function Problems({
  state,
  alarms,
  final,
  finalKnown,
  over,
  onLinked,
  className,
}: {
  state: RunState;
  alarms: RunAlarm[];
  final: FinalTestResult | null;
  finalKnown: boolean;
  over: boolean;
  onLinked: OnLinked;
  className?: string;
}) {
  const [all, setAll] = useState(false);
  const sorted = useMemo(() => bySeriousness(alarms), [alarms]);
  const listed = all ? sorted : sorted.slice(0, FIRST_PROBLEMS);
  const confirmed = finalKnown
    ? sorted.filter((a) => checkOf(a, final, true).kind === "confirmed").length
    : null;
  return (
    <Panel id="problems-title" title="Problems found" className={className}>
      {!sorted.length ? (
        <p className={cn(NOTE, "mt-1.5")}>
          {over ? "No station raised an alarm on this input." : "No alarm so far."}
        </p>
      ) : (
        <>
          <p className={cn(NOTE, "tnum mt-1.5")}>
            {`${plural(sorted.length, "problem")}, most serious first`}
            {confirmed != null ? `; ${formatInt(confirmed)} confirmed by final test.` : "."}
          </p>
          <ol className="mt-3 flex flex-col">
            {listed.map((alarm, i) => {
              const check = checkOf(alarm, final, finalKnown);
              return (
                <li
                  key={alarm.alarm_id}
                  className={cn("flex flex-col gap-2 py-3", i > 0 && "border-t border-hairline")}
                >
                  <div className="flex min-w-0 items-start gap-3">
                    <span
                      aria-hidden="true"
                      className={cn(
                        "mt-[5px] size-2.5 shrink-0 rounded-full",
                        turnsRed(alarm)
                          ? "bg-fail shadow-[0_0_0_3px_var(--fail-wash)]"
                          : "shadow-[inset_0_0_0_1.75px_var(--concern)]",
                      )}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="text-[14.5px] leading-5 font-[600] break-words text-ink">
                        <span className="sr-only">{turnsRed(alarm) ? "Alarm: " : "Warning: "}</span>
                        {problemText(state, alarm)}
                      </p>
                      <p className="mt-1 flex flex-wrap items-center gap-x-2 text-[13px] leading-5 text-ink-2">
                        <CheckMark check={check} />
                        <span className="font-[560] text-ink">{CHECK_WORDS[check.kind]}</span>
                        {"detail" in check && check.detail ? (
                          <span className="text-ink-3">{check.detail}</span>
                        ) : null}
                        <span className="tnum text-ink-3">{alarm.alarm_id}</span>
                      </p>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5 pl-[22px]">
                    <Investigate runId={state.runId} alarm={alarm} onLinked={onLinked} />
                  </div>
                </li>
              );
            })}
          </ol>
          {sorted.length > FIRST_PROBLEMS ? (
            <button
              type="button"
              aria-expanded={all}
              onClick={() => setAll(!all)}
              className={cn(ACTION, "mt-1")}
            >
              {all ? "Show the first few" : `Show all ${formatInt(sorted.length)}`}
            </button>
          ) : null}
        </>
      )}
    </Panel>
  );
}

/* Units (SECOM) ------------------------------------------------------------------------------- */

interface UnitRow extends FinalTestUnit {
  risk: number | null;
  validity: SensorRiskView["units"][number]["validity"] | null;
}

function Units({
  risk,
  final,
  finalKnown,
  stopped,
  onShowUnit,
}: {
  risk: SensorRiskView | null;
  final: FinalTestResult | null;
  finalKnown: boolean;
  stopped: boolean;
  onShowUnit: (index: number) => void;
}) {
  const rows = useMemo<UnitRow[]>(() => {
    const byIndex = new Map(risk?.units.map((u) => [u.index, u]) ?? []);
    return (final?.units ?? []).map((u) => ({
      ...u,
      risk: byIndex.get(u.index)?.risk ?? null,
      validity: byIndex.get(u.index)?.validity ?? null,
    }));
  }, [risk, final]);
  // Only units the model never saw are counted: its own training units say nothing of how it
  // predicts.
  const unseen = rows.filter((u) => u.validity !== "in_training");
  const seen = rows.filter((u) => u.validity === "in_training");
  const failed = unseen.filter((u) => u.result === "fail");
  const passed = unseen.filter((u) => u.result === "pass");
  const caught = failed.filter((u) => u.flagged).length;
  const falseAlarm = passed.filter((u) => u.flagged).length;
  const clear = passed.length - falseAlarm;
  // One row per unit that failed or was warned, failed first, then by risk; the rest are one row.
  const listed = unseen
    .filter((u) => u.result === "fail" || u.flagged)
    .sort(
      (a, b) =>
        Number(b.result === "fail") - Number(a.result === "fail") ||
        (b.risk ?? -1) - (a.risk ?? -1),
    );
  const alarms = falseAlarm ? plural(falseAlarm, "false alarm") : "no false alarm";
  const onPassed = passed.length
    ? ` on the ${passed.length === 1 ? "1 unit" : formatInt(passed.length)} that passed`
    : "";
  const headline = failed.length
    ? `Caught ${formatInt(caught)} of ${plural(failed.length, "unit")} that failed final test, with ${alarms}${onPassed}.`
    : `No unit failed final test, so only false alarms can be judged: ${alarms}${onPassed}.`;

  return (
    <Panel id="units-result-title" title="Units (SECOM): did we predict the failures?">
      {!finalKnown ? (
        <p className={cn(NOTE, "mt-1.5")}>Waiting for final test.</p>
      ) : !rows.length ? (
        <p className={cn(NOTE, "mt-1.5")}>
          {stopped
            ? "Final test stopped, so the warnings cannot be checked."
            : "None of these units has a recorded final-test result, so the warnings cannot be checked."}
        </p>
      ) : (
        <>
          {!unseen.length ? (
            <p className={cn(NOTE, "mt-1.5")}>
              Every unit with a recorded result was seen in training, so none is counted: the
              model&apos;s own training units say nothing about how it predicts.
            </p>
          ) : (
            <>
              <p className="tnum mt-1.5 text-[15px] leading-6 font-[560] text-ink">{headline}</p>
              <ScrollRegion label="Units, our prediction and final test" className="mt-3">
                <div className="max-h-[440px] overflow-y-auto">
                  <table className="w-full text-left text-[13px] leading-5">
                    <caption className="sr-only">
                      Our prediction and the final-test result per unit
                    </caption>
                    <thead>
                      <tr className="border-b border-hairline">
                        {["Unit", "Our prediction", "Final test", "Result"].map((h) => (
                          <th
                            key={h}
                            scope="col"
                            className="h-9 pr-3 text-[12px] leading-4 font-[560] whitespace-nowrap text-ink-3 last:pr-0"
                          >
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {listed.map((u) => (
                        <tr key={u.index} className="border-b border-hairline">
                          <td className="py-2 pr-3 align-top">
                            <button
                              type="button"
                              onClick={() => onShowUnit(u.index)}
                              aria-label={`Unit ${u.unit_id}: show its failure risk`}
                              className="tnum rounded-[4px] font-[560] whitespace-nowrap text-ink underline decoration-[var(--hairline-strong)] underline-offset-[3px] hover:decoration-current"
                            >
                              {`Unit ${u.unit_id}`}
                            </button>
                          </td>
                          <td className="tnum py-2 pr-3 align-top text-ink">
                            <span className="whitespace-nowrap">
                              {u.flagged ? "Warned" : "Not warned"}
                            </span>
                            {u.risk != null ? (
                              <>
                                {" "}
                                <span className="whitespace-nowrap text-ink-3">{`(risk ${formatProbability(u.risk)})`}</span>
                              </>
                            ) : null}
                          </td>
                          <td className="py-2 pr-3 align-top text-ink-2">
                            {u.result === "fail" ? "Failed" : "Passed"}
                          </td>
                          <td className="py-2 align-top">
                            <UnitOutcome
                              kind={
                                u.result === "fail"
                                  ? u.flagged
                                    ? "caught"
                                    : "missed"
                                  : "false_alarm"
                              }
                            />
                          </td>
                        </tr>
                      ))}
                      {clear ? (
                        <tr className="border-b border-hairline">
                          <td className="tnum py-2 pr-3 align-top font-[560] text-ink">
                            {plural(clear, "other unit")}
                          </td>
                          <td className="py-2 pr-3 align-top text-ink">Not warned</td>
                          <td className="py-2 pr-3 align-top text-ink-2">Passed</td>
                          <td className="py-2 align-top">
                            <UnitOutcome kind="clear" />
                          </td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              </ScrollRegion>
              <p className={cn(SMALL, "tnum mt-2")}>
                {[
                  risk
                    ? `Warned means the failure risk was above the ${formatProbability(risk.threshold)} threshold (${risk.operating_point}), the rule final test uses.`
                    : null,
                  `Counting the ${plural(unseen.length, "unit")} with a recorded result that the model never saw.`,
                ]
                  .filter(Boolean)
                  .join(" ")}
              </p>
            </>
          )}
          {seen.length ? (
            <>
              <h4 className="mt-5 text-[13.5px] leading-5 font-[600] text-ink">
                Seen in training, not counted
              </h4>
              <UnitList units={seen} withResult />
            </>
          ) : null}
        </>
      )}
    </Panel>
  );
}

type UnitOutcomeKind = "caught" | "missed" | "false_alarm" | "clear";

const UNIT_OUTCOME: Record<UnitOutcomeKind, { word: string; right: boolean }> = {
  caught: { word: "Caught", right: true },
  missed: { word: "Missed", right: false },
  false_alarm: { word: "False alarm", right: false },
  clear: { word: "Correctly clear", right: true },
};

function UnitOutcome({ kind }: { kind: UnitOutcomeKind }) {
  const { word, right } = UNIT_OUTCOME[kind];
  const Icon = right ? CheckIcon : XIcon;
  return (
    <span
      className={cn("inline-flex items-start gap-1 font-[560]", right ? "text-ink" : "text-fail")}
    >
      <Icon
        aria-hidden="true"
        className={cn("mt-0.5 size-4 shrink-0", right ? "text-pass" : "text-fail")}
        strokeWidth={2.5}
      />
      {word}
    </span>
  );
}

function UnitList({ units, withResult = false }: { units: UnitRow[]; withResult?: boolean }) {
  const sorted = [...units].sort((a, b) => (b.risk ?? -1) - (a.risk ?? -1));
  return (
    <ul className="mt-2 flex max-h-[220px] flex-wrap gap-1.5 overflow-y-auto">
      {sorted.map((u) => (
        <li
          key={u.index}
          className="tnum inline-flex items-center gap-1.5 rounded-full bg-surface-2 px-2.5 py-1 text-[12.5px] leading-4 text-ink-2"
        >
          <span className="font-[560] text-ink">{`Unit ${u.unit_id}`}</span>
          <span>{`risk ${formatProbability(u.risk)}`}</span>
          <span className="text-ink-3">
            {[
              withResult ? (u.result === "fail" ? "failed" : "passed") : null,
              u.flagged ? "warned" : "not warned",
            ]
              .filter(Boolean)
              .join(", ")}
          </span>
        </li>
      ))}
    </ul>
  );
}

/* Wafers (WM-811K) ---------------------------------------------------------------------------- */

/** Good dies over probed dies, counted on the map; null until the map is read. */
function waferYield(w: WaferItem): number | null {
  if (!w.map) return null;
  const cells = decodeWaferCells(w.map);
  let good = 0;
  let probed = 0;
  for (const c of cells) {
    if (c === 1) good++;
    if (c === 1 || c === 2) probed++;
  }
  return probed ? good / probed : null;
}

function Wafers({ wafers }: { wafers: WaferItem[] | null }) {
  const rows = useMemo(
    () =>
      [...(wafers ?? [])]
        .sort((a, b) => a.index - b.index)
        .map((w) => ({
          w,
          yield: waferYield(w),
          agrees: w.recorded_label != null ? w.top_label === w.recorded_label : null,
        })),
    [wafers],
  );
  const labelled = rows.filter((r) => r.agrees != null);
  const agreeing = labelled.filter((r) => r.agrees).length;
  const unlabelled = rows.length - labelled.length;

  return (
    <Panel id="wafers-result-title" title="Wafers (WM-811K): did we name the defect?">
      {!wafers ? (
        <p className={cn(NOTE, "mt-1.5")}>Waiting for wafer test.</p>
      ) : (
        <>
          <p className="tnum mt-1.5 text-[15px] leading-6 font-[560] text-ink">
            {labelled.length
              ? `The predicted pattern matched the recorded one on ${formatInt(agreeing)} of ${plural(labelled.length, "labelled wafer")}.`
              : "No wafer here has a recorded WM-811K label, so the predictions cannot be checked."}
            {labelled.length && unlabelled
              ? ` ${plural(unlabelled, "wafer")} without a recorded label ${unlabelled === 1 ? "is" : "are"} left out.`
              : ""}
          </p>
          <p className={cn(SMALL, "mt-1")}>
            Every wafer has some failed dies: they are normal and are discarded at sort. What
            matters is whether they form a pattern, because a pattern points to a cause on the line.
          </p>
          <ScrollRegion label="Wafers, predicted and recorded patterns" className="mt-3">
            <div className="max-h-[440px] overflow-y-auto">
              <table className="w-full text-left text-[13px] leading-5">
                <caption className="sr-only">Predicted and recorded pattern per wafer</caption>
                <thead>
                  <tr className="border-b border-hairline">
                    {["Wafer", "Yield", "Predicted", "Recorded", "Match"].map((h, i) => (
                      <th
                        key={h}
                        scope="col"
                        className={cn(
                          "h-9 pr-3 text-[12px] leading-4 font-[560] whitespace-nowrap text-ink-3",
                          i === 1 && "text-right",
                          i === 4 && "pr-0 text-center",
                        )}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map(({ w, yield: y, agrees }) => (
                    <tr key={w.index} className="border-b border-hairline">
                      <td className="py-2 pr-3 align-top">
                        <span className="tnum block font-[560] whitespace-nowrap text-ink">{`Wafer ${w.wafer}`}</span>
                        <span className="block text-[12px] leading-4 break-all text-ink-3">
                          {lotName(w.lot)}
                        </span>
                      </td>
                      <td className="tnum py-2 pr-3 text-right align-top whitespace-nowrap text-ink-2">
                        {formatPercent(y, 1)}
                      </td>
                      <td className="py-2 pr-3 align-top text-ink">{patternName(w.top_label)}</td>
                      <td className="py-2 pr-3 align-top text-ink-2">
                        {w.recorded_label != null ? (
                          patternName(w.recorded_label)
                        ) : (
                          <span className="text-ink-3">No recorded label</span>
                        )}
                      </td>
                      <td className="py-2 text-center align-top">
                        {agrees == null ? (
                          <span className="text-ink-3" aria-label="Not counted">
                            –
                          </span>
                        ) : agrees ? (
                          <CheckIcon
                            role="img"
                            aria-label="Matches"
                            className="inline size-4 text-pass"
                            strokeWidth={2.5}
                          />
                        ) : (
                          <XIcon
                            role="img"
                            aria-label="Does not match"
                            className="inline size-4 text-fail"
                            strokeWidth={2.5}
                          />
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </ScrollRegion>
        </>
      )}
    </Panel>
  );
}
