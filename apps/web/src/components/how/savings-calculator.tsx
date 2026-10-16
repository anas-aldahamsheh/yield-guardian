"use client";

import { useQuery } from "@tanstack/react-query";
import type { MeasuredResult } from "@yield-guardian/contracts";
import { Fragment, useEffect, useId, useMemo, useState } from "react";

import { Panel } from "@/components/page";
import { ErrorState, PendingState, Placeholder } from "@/components/states";
import { Button } from "@/components/ui/button";
import { useApi } from "@/lib/api/context";
import { ciLabel, formatFixed, formatInt, formatPercent } from "@/lib/format";
import { q } from "@/lib/api/queries";
import {
  computeSavings,
  DAYS_PER_MONTH,
  type InputName,
  INPUTS,
  type Inputs,
  isEmpty,
  type Line,
  type LineId,
  type Need,
  parseInput,
  type Rate,
  type Rates,
  roundFor,
} from "@/lib/savings";
import { cn } from "@/lib/utils";

/** The fields in the order a fab would think of them: volume and time first, then costs. */
const FIELDS: { name: InputName; label: string; unit: string; hint?: string }[] = [
  { name: "wafersPerDay", label: "Wafers per day", unit: "wafers a day" },
  { name: "minutesPerMap", label: "Minutes an engineer spends per wafer map", unit: "min per map" },
  { name: "engineerHourCost", label: "Engineer hour cost", unit: "per engineer hour" },
  { name: "downtimeHourCost", label: "Downtime hour cost", unit: "per downtime hour" },
  { name: "waferCost", label: "Wafer cost", unit: "per wafer" },
];
const FIELD = Object.fromEntries(FIELDS.map((f) => [f.name, f])) as Record<
  InputName,
  (typeof FIELDS)[number]
>;

type RateName = keyof Rates;
type Term = { input: InputName } | { rate: RateName } | { text: string };
const X: Term = { text: "×" };
const DAYS: Term = { text: `${DAYS_PER_MONTH} days` };
const REVIEW: Term[] = [{ input: "wafersPerDay" }, X, DAYS, X, { rate: "autoShare" }];
const ALARMS: Term[] = [{ input: "wafersPerDay" }, X, DAYS, X, { rate: "falseAlarmRate" }];
const HOURS: Term[] = [...REVIEW, X, { input: "minutesPerMap" }, { text: "÷ 60" }];

const LINES: Record<LineId, { title: string; unit: string; detail?: string; formula: Term[] }> = {
  maps: { title: "Wafer maps classified automatically", unit: "maps a month", formula: REVIEW },
  hours: { title: "Engineer hours freed from map review", unit: "h a month", formula: HOURS },
  engineerMoney: {
    title: "Engineer cost freed",
    unit: "a month",
    formula: [...HOURS, X, { input: "engineerHourCost" }],
  },
  falseAlarms: { title: "False alarms from the control charts", unit: "a month", formula: ALARMS },
  downtimeMoney: {
    title: "Downtime cost of those false alarms",
    unit: "a month",
    detail: "for each hour one false alarm keeps a tool stopped",
    formula: [...ALARMS, X, { input: "downtimeHourCost" }],
  },
  waferMoney: {
    title: "Wafer cost of those false alarms",
    unit: "a month",
    detail: "for each wafer one false alarm scraps",
    formula: [...ALARMS, X, { input: "waferCost" }],
  },
};

const RATE_NAME: Record<RateName, string> = {
  autoShare: "share classified automatically",
  falseAlarmRate: "false-alarm rate",
};
const NEED_NAME = (need: Need) =>
  need === "autoShare" || need === "falseAlarmRate"
    ? `the measured ${RATE_NAME[need]}`
    : FIELD[need].label.toLowerCase();

/** The two measured rates, from the API's measured-results table (computed from the bundles). */
function ratesFrom(results: MeasuredResult[]): Rates {
  const rate = (id: string): Rate | null => {
    const row = results.find((r) => r.id === id);
    return row?.estimate
      ? { estimate: row.estimate, label: row.label, data: row.data, source: row.source }
      : null;
  };
  return { autoShare: rate("auto_classified_share"), falseAlarmRate: rate("fdc_false_alarm_rate") };
}

const empty = (): Record<InputName, string> => ({
  waferCost: "",
  engineerHourCost: "",
  downtimeHourCost: "",
  wafersPerDay: "",
  minutesPerMap: "",
});

/**
 * What the product would change for a fab, from the fab's own numbers and our measured rates.
 * Nothing is filled in: a line appears when every number it needs has been typed, as the value
 * with the range from the rate's confidence interval, and its formula reads the typed numbers.
 */
export function SavingsCalculator() {
  const api = useApi();
  const results = useQuery(q.results(api));
  const [raw, setRaw] = useState(empty);
  const [focused, setFocused] = useState<InputName | null>(null);
  const parsed = useMemo(
    () =>
      Object.fromEntries(INPUTS.map((k) => [k, parseInput(raw[k])])) as Record<
        InputName,
        ReturnType<typeof parseInput>
      >,
    [raw],
  );
  const inputs = Object.fromEntries(INPUTS.map((k) => [k, parsed[k].value])) as Inputs;
  const rates = results.data ? ratesFrom(results.data.results) : null;
  const lines = rates ? computeSavings(inputs, rates) : null;
  const typedNothing = isEmpty(inputs);

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-street lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] content-start gap-street">
        <Panel
          title="Your numbers"
          description="In your own currency; the money lines use the same one. Nothing is stored or sent anywhere."
        >
          <form
            className="grid grid-cols-[minmax(0,1fr)] gap-4"
            onSubmit={(e) => e.preventDefault()}
            aria-label="Your numbers"
          >
            {FIELDS.map((f) => (
              <Field
                key={f.name}
                field={f}
                value={raw[f.name]}
                error={parsed[f.name].error}
                onChange={(v) => setRaw((r) => ({ ...r, [f.name]: v }))}
                onFocus={() => setFocused(f.name)}
                onBlur={() => setFocused((cur) => (cur === f.name ? null : cur))}
              />
            ))}
            <div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={INPUTS.every((k) => raw[k] === "")}
                onClick={() => setRaw(empty())}
              >
                Clear
              </Button>
            </div>
          </form>
        </Panel>
        <Panel
          title="Measured rates"
          description="Read from the API when this page loads; each was measured on data the models never saw."
        >
          {results.isError ? (
            <ErrorState compact error={results.error} onRetry={() => void results.refetch()} />
          ) : !rates ? (
            <Placeholder className="h-28" label="Loading the measured rates" />
          ) : (
            <dl className="grid grid-cols-[minmax(0,1fr)] gap-4 text-[14px] leading-5">
              <RateRow
                name="autoShare"
                rate={rates.autoShare}
                fallback="Wafer maps classified automatically at 99% precision"
              />
              <RateRow
                name="falseAlarmRate"
                rate={rates.falseAlarmRate}
                fallback="Control-chart false-alarm rate on in-control units"
              />
            </dl>
          )}
        </Panel>
      </div>

      <Panel
        title="Per month"
        description="Each line as a value, with the range from the two ends of the measured rate's confidence interval under it."
        className="min-w-0"
      >
        {!lines ? (
          <Placeholder className="h-72" label="Loading the calculator" />
        ) : (
          <Results
            lines={lines}
            inputs={inputs}
            rates={rates!}
            focused={focused}
            typedNothing={typedNothing}
          />
        )}
      </Panel>

      <Panel title="Assumptions" className="lg:col-span-2">
        <Assumptions rates={rates} />
      </Panel>
    </div>
  );
}

function Field({
  field,
  value,
  error,
  onChange,
  onFocus,
  onBlur,
}: {
  field: (typeof FIELDS)[number];
  value: string;
  error: string | null;
  onChange: (value: string) => void;
  onFocus: () => void;
  onBlur: () => void;
}) {
  const id = useId();
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-1.5">
      <label htmlFor={id} className="text-[14px] leading-5 font-[560] text-ink">
        {field.label}
      </label>
      <div className="flex min-w-0 items-center gap-2.5">
        <input
          id={id}
          type="text"
          inputMode="decimal"
          autoComplete="off"
          spellCheck={false}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onFocus={onFocus}
          onBlur={onBlur}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : `${id}-unit`}
          className="tnum h-10 w-full max-w-[12rem] min-w-0 rounded-md border border-input bg-surface-2 px-3 text-[16px] text-ink aria-invalid:border-fail"
        />
        <span id={`${id}-unit`} className="text-[13px] leading-5 text-ink-3">
          {field.unit}
        </span>
      </div>
      {error ? (
        <p id={`${id}-error`} className="text-[13px] leading-5 text-fail">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function RateRow({
  name,
  rate,
  fallback,
}: {
  name: RateName;
  rate: Rate | null;
  fallback: string;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-ink-2">{rate?.label ?? fallback}</dt>
      <dd className="mt-0.5">
        {rate && rate.estimate.value != null ? (
          <>
            <span className="tnum text-[17px] leading-6 text-ink">
              {formatPercent(rate.estimate.value, 1)}
            </span>
            {rate.estimate.ci_low != null && rate.estimate.ci_high != null ? (
              <span className="tnum text-ink-3">
                {" "}
                {ciLabel(rate.estimate)} {formatPercent(rate.estimate.ci_low, 1)} to{" "}
                {formatPercent(rate.estimate.ci_high, 1)}
              </span>
            ) : (
              <span className="text-ink-3"> (no interval reported)</span>
            )}
            <span className="tnum mt-0.5 block text-[12px] leading-4 text-ink-3">
              {rate.data}
              {rate.estimate.n != null ? `, n = ${formatInt(rate.estimate.n)}` : ""}. {rate.source}
              {rate.estimate.method ? `. Interval: ${rate.estimate.method}` : ""}.
            </span>
          </>
        ) : (
          <span className="text-ink-3">
            Not measured yet, so the {RATE_NAME[name]} lines stay empty.
          </span>
        )}
      </dd>
    </div>
  );
}

const show = (id: LineId, v: number) => {
  const r = roundFor(id, v);
  return formatFixed(r.value, r.digits);
};

function Results({
  lines,
  inputs,
  rates,
  focused,
  typedNothing,
}: {
  lines: Line[];
  inputs: Inputs;
  rates: Rates;
  focused: InputName | null;
  typedNothing: boolean;
}) {
  const byId = Object.fromEntries(lines.map((l) => [l.id, l])) as Record<LineId, Line>;
  const groups: { title: string; ids: LineId[] }[] = [
    { title: "Time saved on wafer-map review", ids: ["maps", "hours", "engineerMoney"] },
    {
      title: "False alarms to weigh against it",
      ids: ["falseAlarms", "downtimeMoney", "waferMoney"],
    },
  ];
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6">
      {typedNothing ? (
        <PendingState compact title="Nothing to compute yet">
          Type your fab&rsquo;s numbers on the left. Nothing is filled in for you, and a line shows
          a result only when the numbers it needs are in.
        </PendingState>
      ) : null}
      {groups.map((g) => (
        <section key={g.title} aria-label={g.title} className="min-w-0">
          <h3 className="border-b border-hairline pb-1.5 text-[14px] leading-5 font-[620] text-ink">
            {g.title}
          </h3>
          <ul className="grid grid-cols-[minmax(0,1fr)]">
            {g.ids.map((id) => (
              <ResultLine
                key={id}
                line={byId[id]}
                inputs={inputs}
                rates={rates}
                focused={focused}
              />
            ))}
          </ul>
        </section>
      ))}
      <SpokenSummary line={byId.hours} />
    </div>
  );
}

function ResultLine({
  line,
  inputs,
  rates,
  focused,
}: {
  line: Line;
  inputs: Inputs;
  rates: Rates;
  focused: InputName | null;
}) {
  const meta = LINES[line.id];
  const r = line.range;
  return (
    <li
      className="grid grid-cols-[minmax(0,1fr)] gap-x-6 gap-y-1 border-b border-hairline py-3 last:border-b-0 sm:grid-cols-[minmax(0,1fr)_auto]"
      data-line={line.id}
    >
      <div className="min-w-0">
        <p className="text-[14px] leading-5 text-ink">{meta.title}</p>
        {meta.detail ? <p className="text-[12px] leading-4 text-ink-3">{meta.detail}</p> : null}
      </div>
      <p className="tnum min-w-0 sm:text-right" data-value>
        {r ? (
          <>
            <span className="readout text-[26px] leading-8 text-ink">{show(line.id, r.value)}</span>{" "}
            <span className="text-[13px] text-ink-2">{meta.unit}</span>
            <span className="block text-[13px] leading-5 text-ink-2">
              {r.low != null && r.high != null
                ? `${show(line.id, r.low)} to ${show(line.id, r.high)}`
                : "no interval for this rate"}
            </span>
          </>
        ) : (
          <span className="text-[13px] leading-5 text-ink-3">
            Needs {line.needs.map(NEED_NAME).join(", ")}
          </span>
        )}
      </p>
      <p className="tnum text-[12px] leading-5 text-ink-2 sm:col-span-2">
        {/* Read as one sentence; the chips below are the same terms, drawn. */}
        <span className="sr-only" data-formula>
          Formula: {formulaText(meta.formula, inputs, rates)}
        </span>
        <span aria-hidden="true">
          <span className="text-ink-3">= </span>
          {meta.formula.map((t, i) => (
            <Fragment key={i}>
              {i > 0 ? " " : null}
              <TermView
                term={t}
                inputs={inputs}
                rates={rates}
                lit={"input" in t && t.input === focused}
              />
            </Fragment>
          ))}
        </span>
      </p>
    </li>
  );
}

function termText(t: Term, inputs: Inputs, rates: Rates): string {
  if ("text" in t) return t.text;
  if ("input" in t) {
    const v = inputs[t.input];
    return v == null
      ? FIELD[t.input].unit.replace(/^per /, "cost per ")
      : `${formatFixed(v, Number.isInteger(v) ? 0 : 2)} ${FIELD[t.input].unit}`;
  }
  const e = rates[t.rate]?.estimate;
  return e?.value != null ? formatPercent(e.value, 1) : RATE_NAME[t.rate];
}

function formulaText(terms: Term[], inputs: Inputs, rates: Rates): string {
  return terms.map((t) => termText(t, inputs, rates)).join(" ");
}

/** One term: a typed number (lit while its field has focus), a measured rate or a constant. */
function TermView({
  term,
  inputs,
  rates,
  lit,
}: {
  term: Term;
  inputs: Inputs;
  rates: Rates;
  lit: boolean;
}) {
  const text = termText(term, inputs, rates);
  if ("text" in term) return <span className="text-ink-3">{text}</span>;
  const missing =
    "input" in term ? inputs[term.input] == null : rates[term.rate]?.estimate.value == null;
  return (
    <span
      className={cn(
        "rounded-[14px] px-1 py-px whitespace-nowrap",
        missing
          ? "border border-dashed border-hairline-strong text-ink-3"
          : "bg-surface-2 text-ink",
        "rate" in term &&
          !missing &&
          "underline decoration-hairline-strong decoration-dotted underline-offset-4",
        lit && "lit",
      )}
    >
      {text}
    </span>
  );
}

/** The main line in words for screen readers, once typing pauses (the readouts change with every key). */
function SpokenSummary({ line }: { line: Line }) {
  const [said, setSaid] = useState("");
  const r = line.range;
  const text = r
    ? `${LINES.hours.title}: ${show("hours", r.value)} hours a month${r.low != null && r.high != null ? `, from ${show("hours", r.low)} to ${show("hours", r.high)}` : ""}.`
    : "";
  useEffect(() => {
    const id = window.setTimeout(() => setSaid(text), 700);
    return () => window.clearTimeout(id);
  }, [text]);
  return (
    <p className="sr-only" role="status">
      {said}
    </p>
  );
}

function Assumptions({ rates }: { rates: Rates | null }) {
  const n = rates?.falseAlarmRate?.estimate.n;
  return (
    <ul className="grid max-w-[90ch] list-disc grid-cols-[minmax(0,1fr)] gap-1.5 pl-5 text-[14px] leading-6 text-ink-2 marker:text-ink-3">
      <li>A month is {DAYS_PER_MONTH} days of production at the wafers per day you typed.</li>
      <li>
        Today an engineer looks at every wafer map for the minutes you typed. With the classifier,
        maps classified automatically at the 99% precision target need no review; the rest, and
        every map flagged as an unknown pattern, still do.
      </li>
      <li>
        The share classified automatically was measured on held-out WM-811K lots. On another
        fab&rsquo;s wafers it can be lower until the classifier is retrained, as the limits above
        say.
      </li>
      <li>
        Each wafer passes the control charts once, as a SECOM unit does, and the line runs in
        control: an alarm on a wafer that really drifted is not a false alarm, so this counts the
        false alarms of a healthy line.
      </li>
      <li>
        The false-alarm rate was measured on {n != null ? `${formatInt(n)} ` : ""}held-out
        in-control SECOM units, so its interval is wide and the false-alarm lines spread widely.
      </li>
      <li>
        What a false alarm costs depends on what your fab does with one. The downtime and wafer
        lines give the cost for each hour of stop and for each wafer scrapped per false alarm:
        multiply by your own figure. The time an engineer spends checking an alarm is not counted.
      </li>
      <li>
        Wafers saved and downtime avoided by an earlier warning are not computed: neither dataset
        records when a problem would have been found without the product, so there is no measured
        rate for them.
      </li>
      <li>
        Ranges come from the two ends of the measured rates&rsquo; confidence intervals
        {rates?.autoShare ? ` (${ciLabel(rates.autoShare.estimate)})` : ""}, computed with the
        unrounded rates. Your own numbers are taken as exact.
      </li>
      <li>
        Money is rounded to whole units of your currency; hours and counts to whole numbers, with
        one decimal below 10.
      </li>
    </ul>
  );
}
