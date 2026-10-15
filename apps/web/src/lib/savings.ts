import type { Estimate } from "@yield-guardian/contracts";

/**
 * The savings calculator (PLAN_V2 §9), as pure functions. Everything the user did not type is a
 * measured rate read from the API with its confidence interval; nothing has a default. A line is
 * computed only when every number it needs is there, and its range comes from the ends of the
 * rate's interval (the user's own numbers are taken as exact).
 */

/** A month is counted as this many days of production; the page says so next to the results. */
export const DAYS_PER_MONTH = 30;
/** Inputs larger than this are refused: no fab has a trillion of anything per day. */
export const INPUT_MAX = 1e12;

export const INPUTS = ["waferCost", "engineerHourCost", "downtimeHourCost", "wafersPerDay", "minutesPerMap"] as const;
export type InputName = (typeof INPUTS)[number];
export type Inputs = Record<InputName, number | null>;

export type Parsed = { value: number | null; error: string | null };

/**
 * A typed number: empty is null (not zero), "1,250.5" and "1250.5" are the same, and negative,
 * malformed or absurdly large values are refused with a sentence that says what to type.
 */
export function parseInput(raw: string): Parsed {
  const text = raw.trim();
  if (text === "") return { value: null, error: null };
  const plain = /^\d{1,3}(,\d{3})+(\.\d+)?$/.test(text) ? text.replaceAll(",", "") : text;
  if (/^-/.test(plain)) return { value: null, error: "Enter 0 or more." };
  if (!/^(\d+\.?\d*|\.\d+)$/.test(plain)) return { value: null, error: "Enter a number, such as 1250 or 2.5." };
  const value = Number(plain);
  if (!Number.isFinite(value) || value > INPUT_MAX) return { value: null, error: "This number is too large." };
  return { value, error: null };
}

/** The point value and the two ends of its interval; the ends are null when the rate has none. */
export interface Range {
  value: number;
  low: number | null;
  high: number | null;
}

/** A rate measured on held-out data, as the API reports it. */
export interface Rate {
  estimate: Estimate;
  label: string;
  data: string;
  source: string;
}

export interface Rates {
  /** Share of wafer maps classified automatically at the 99% precision target. */
  autoShare: Rate | null;
  /** Share of in-control units that raise a control-chart alarm at the 99% limit. */
  falseAlarmRate: Rate | null;
}

export type LineId = "maps" | "hours" | "engineerMoney" | "falseAlarms" | "downtimeMoney" | "waferMoney";
export type Need = InputName | "autoShare" | "falseAlarmRate";

export interface Line {
  id: LineId;
  /** null until every input and rate it needs is there. */
  range: Range | null;
  /** What is still missing, in the order the formula reads. */
  needs: Need[];
}

/** f(rate) for every end of the rate's interval; a missing end stays missing. */
function scale(rate: Estimate, factor: number): Range {
  return {
    value: rate.value * factor,
    low: rate.ci_low == null ? null : rate.ci_low * factor,
    high: rate.ci_high == null ? null : rate.ci_high * factor,
  };
}

function line(id: LineId, needs: [Need, number | null | undefined][], rate: Rate | null, rateNeed: Need, factor: (n: Record<string, number>) => number): Line {
  const missing = needs.filter(([, v]) => v == null).map(([k]) => k);
  if (!rate) missing.push(rateNeed);
  if (missing.length || !rate) return { id, range: null, needs: missing };
  const values = Object.fromEntries(needs.map(([k, v]) => [k, v as number]));
  return { id, range: scale(rate.estimate, factor(values)), needs: [] };
}

/**
 * The calculator's lines:
 *   maps           = wafers per day × days × auto share
 *   hours          = maps × minutes per map ÷ 60
 *   engineerMoney  = hours × engineer hour cost
 *   falseAlarms    = wafers per day × days × false-alarm rate
 *   downtimeMoney  = false alarms × downtime hour cost      (for each hour a false alarm stops a tool)
 *   waferMoney     = false alarms × wafer cost              (for each wafer a false alarm scraps)
 */
export function computeSavings(inputs: Inputs, rates: Rates): Line[] {
  const n = inputs.wafersPerDay;
  const m = inputs.minutesPerMap;
  const s = rates.autoShare;
  const f = rates.falseAlarmRate;
  return [
    line("maps", [["wafersPerDay", n]], s, "autoShare", (v) => v.wafersPerDay! * DAYS_PER_MONTH),
    line("hours", [["wafersPerDay", n], ["minutesPerMap", m]], s, "autoShare", (v) => (v.wafersPerDay! * DAYS_PER_MONTH * v.minutesPerMap!) / 60),
    line(
      "engineerMoney",
      [["wafersPerDay", n], ["minutesPerMap", m], ["engineerHourCost", inputs.engineerHourCost]],
      s,
      "autoShare",
      (v) => ((v.wafersPerDay! * DAYS_PER_MONTH * v.minutesPerMap!) / 60) * v.engineerHourCost!,
    ),
    line("falseAlarms", [["wafersPerDay", n]], f, "falseAlarmRate", (v) => v.wafersPerDay! * DAYS_PER_MONTH),
    line("downtimeMoney", [["wafersPerDay", n], ["downtimeHourCost", inputs.downtimeHourCost]], f, "falseAlarmRate", (v) => v.wafersPerDay! * DAYS_PER_MONTH * v.downtimeHourCost!),
    line("waferMoney", [["wafersPerDay", n], ["waferCost", inputs.waferCost]], f, "falseAlarmRate", (v) => v.wafersPerDay! * DAYS_PER_MONTH * v.waferCost!),
  ];
}

/** True when the user has typed nothing at all: the calculator then shows no result. */
export function isEmpty(inputs: Inputs): boolean {
  return INPUTS.every((k) => inputs[k] == null);
}

const MONEY = new Set<LineId>(["engineerMoney", "downtimeMoney", "waferMoney"]);

/**
 * Rounding as the page states it: money to whole units of the user's currency; hours and counts
 * to whole numbers, with one decimal below 10 so a small line does not round to nothing.
 */
export function roundFor(id: LineId, value: number): { value: number; digits: number } {
  if (MONEY.has(id) || value >= 10) return { value: Math.round(value), digits: 0 };
  return { value: Math.round(value * 10) / 10, digits: 1 };
}

export const isMoney = (id: LineId) => MONEY.has(id);
