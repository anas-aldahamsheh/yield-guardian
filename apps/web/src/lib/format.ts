import type { Estimate } from "@yield-guardian/contracts";

/**
 * Formatting of readings. One place decides how a number looks, so the same value reads the same
 * on every screen. Missing values are a dash with a reason nearby, never a zero.
 */

export const DASH = "–";
const LOCALE = "en-US";

/** The decimal digits of a non-negative number as written in the shortest round-trip form. */
function shortestDigits(abs: number): [integer: string, fraction: string] {
  const m = /^(\d+)(?:\.(\d+))?(?:e([+-]\d+))?$/.exec(String(abs))!;
  let digits = m[1]! + (m[2] ?? "");
  let point = m[1]!.length + (m[3] ? Number(m[3]) : 0);
  if (point <= 0) {
    digits = "0".repeat(1 - point) + digits;
    point = 1;
  }
  if (point > digits.length) digits += "0".repeat(point - digits.length);
  return [digits.slice(0, point), digits.slice(point)];
}

/**
 * en-US with a fixed number of decimals, exactly as Intl.NumberFormat writes it: the shortest
 * round-trip decimal rounded half away from zero, comma-grouped, "-" before negatives (and -0).
 * Written out because the first Intl.NumberFormat a page makes costs tens of milliseconds of
 * ICU set-up on a phone, inside the hydration task. format.test.ts checks it against Intl.
 */
export function formatFixed(value: number, digits: number): string {
  if (Math.abs(value) >= 1e21) {
    return new Intl.NumberFormat(LOCALE, {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    }).format(value);
  }
  let [int, frac] = shortestDigits(Math.abs(value));
  if (frac.length > digits) {
    const kept = (int + frac.slice(0, digits)).split("");
    if (frac.charCodeAt(digits) >= 53 /* "5" */) {
      let k = kept.length - 1;
      while (k >= 0 && kept[k] === "9") kept[k--] = "0";
      if (k < 0) kept.unshift("1");
      else kept[k] = String(Number(kept[k]) + 1);
    }
    int = kept.slice(0, kept.length - digits).join("");
    frac = kept.slice(kept.length - digits).join("");
  } else {
    frac += "0".repeat(digits - frac.length);
  }
  const grouped = int.replace(/^0+(?=\d)/, "").replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${value < 0 || Object.is(value, -0) ? "-" : ""}${grouped}${digits ? `.${frac}` : ""}`;
}

export function formatInt(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? DASH : formatFixed(value, 0);
}

/** A decimal with a fixed number of digits (default 2). */
export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return DASH;
  return formatFixed(value, digits);
}

/** Significant figures for values whose scale varies (sensor readings, T², test statistics). */
export function formatReading(value: number | null | undefined, significant = 4): string {
  if (value == null || !Number.isFinite(value)) return DASH;
  if (value === 0) return "0";
  const abs = Math.abs(value);
  if (abs >= 1e6 || abs < 1e-4) return value.toExponential(significant - 1);
  const digits = Math.max(0, significant - 1 - Math.floor(Math.log10(abs)));
  return formatNumber(value, Math.min(digits, 6));
}

/** A share in [0, 1] as a percentage. */
export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return DASH;
  return `${formatNumber(value * 100, digits)}%`;
}

/** A probability: percent with one decimal, or a bound for tiny and near-certain values. */
export function formatProbability(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return DASH;
  if (value > 0 && value < 0.001) return "<0.1%";
  if (value < 1 && value > 0.999) return ">99.9%";
  return formatPercent(value, 1);
}

/** A p-value or q-value the way papers write it. */
export function formatPValue(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return DASH;
  if (value < 0.001) return "<0.001";
  if (value < 0.01) return formatNumber(value, 3);
  return formatNumber(value, 2);
}

/** Signed value for contributions in log-odds: always shows + or −. */
export function formatSigned(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return DASH;
  const s = formatNumber(Math.abs(value), digits);
  if (Number(s) === 0) return formatNumber(0, digits);
  return value < 0 ? `−${s}` : `+${s}`;
}

export type MetricFormat = "ratio" | "percent" | "count" | "number";

/** A metric value in the format the API names. */
export function formatMetric(value: number | null | undefined, format: MetricFormat): string {
  switch (format) {
    case "percent":
      return formatPercent(value, value != null && Math.abs(value) < 0.1 ? 1 : 0);
    case "count":
      return formatInt(value);
    case "ratio":
      return formatNumber(value, 2);
    case "number":
      return formatNumber(value, 1);
  }
}

/** "0.71–0.84" or "71–84%"; null when the interval cannot be computed. */
export function formatInterval(estimate: Estimate, format: MetricFormat = "ratio"): string | null {
  if (estimate.ci_low == null || estimate.ci_high == null) return null;
  if (format === "percent") {
    const digits = Math.abs(estimate.ci_high) < 0.1 ? 1 : 0;
    return `${formatNumber(estimate.ci_low * 100, digits)}–${formatNumber(estimate.ci_high * 100, digits)}%`;
  }
  return `${formatMetric(estimate.ci_low, format)}–${formatMetric(estimate.ci_high, format)}`;
}

/** The confidence level as written next to an interval: "95% CI". */
export function ciLabel(estimate: Estimate): string {
  return `${Math.round((estimate.ci_level ?? 0.95) * 100)}% CI`;
}

const pad = (n: number) => String(n).padStart(2, "0");

/**
 * Plant time as recorded (ISO date and minutes, no time-zone conversion): SECOM timestamps are
 * local plant times, so they are shown exactly as the record has them.
 */
export function formatPlantTime(iso: string | null | undefined, seconds = false): string {
  if (!iso) return DASH;
  const m = iso.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):?(\d{2})?/);
  if (!m) return iso;
  return `${m[1]} ${m[2]}:${m[3]}${seconds && m[4] ? `:${m[4]}` : ""}`;
}

/** A wall-clock moment in the viewer's time zone, for events in this product (audit, usage). */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/**
 * The same moment in UTC, marked as such: what the server renders, since it cannot know the
 * viewer's time zone. LocalDateTime swaps in the local time once the page has hydrated.
 */
export function formatDateTimeUtc(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`;
}

/** "3 min ago", for recent product events. */
export function formatRelative(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return DASH;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const s = Math.round((now - t) / 1000);
  if (s < 45) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  return formatDateTime(iso);
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms)) return DASH;
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${formatNumber(ms / 1000, ms < 10_000 ? 1 : 0)} s`;
}

/** Large counts in a compact form: 12.4k, 3.1M. */
export function formatCompact(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return DASH;
  compactFmt ??= new Intl.NumberFormat(LOCALE, { notation: "compact", maximumFractionDigits: 1 });
  return compactFmt.format(value);
}
let compactFmt: Intl.NumberFormat | undefined;

/** "1 unit", "3 units". */
export function plural(count: number, one: string, many = `${one}s`): string {
  return `${formatInt(count)} ${count === 1 ? one : many}`;
}

/** A count the model endpoint may not report: null reads "not reported", never 0. */
export function formatReported(
  value: number | null | undefined,
  format: (v: number) => string = formatInt,
): string {
  return value == null ? "not reported" : format(value);
}
