/**
 * Scales of the line's instruments. Every mark on the line is a computed value placed by one of
 * these functions, and every instrument prints its scale, so a reading can be checked by eye.
 */

/** Sensor lights: brightness is |z|, the standardised reading, from 0 to Z_FULL or more. */
export const Z_FULL = 4;

/** Light level of a sensor lamp, 0 (off) to 1 (full), for a standardised reading. */
export function lampLevel(z: number | null): number {
  if (z == null || !Number.isFinite(z)) return 0;
  return Math.min(1, Math.abs(z) / Z_FULL);
}

/** A log-scale gauge over whole decades [10^lo, 10^hi]. */
export interface LogScale {
  lo: number;
  hi: number;
}

/**
 * Decades that hold every value and both limits, with a decade of room below the 99% limit, so
 * the limits never sit at the very end of the dial.
 */
export function logDomain(values: readonly number[], limits: readonly number[]): LogScale {
  const positive = [...values, ...limits].filter((v) => Number.isFinite(v) && v > 0);
  if (!positive.length) return { lo: 0, hi: 1 };
  const lowest = limits.filter((v) => Number.isFinite(v) && v > 0);
  const min = Math.min(...positive, ...(lowest.length ? [Math.min(...lowest) / 10] : []));
  const max = Math.max(...positive);
  const lo = Math.floor(Math.log10(min));
  let hi = Math.ceil(Math.log10(max));
  if (hi <= lo) hi = lo + 1;
  return { lo, hi };
}

/** Position of a value on a log scale, 0 to 1 (clamped; 0 for values at or below zero). */
export function logPosition(value: number | null, scale: LogScale): number {
  if (value == null || !Number.isFinite(value) || value <= 0) return 0;
  const t = (Math.log10(value) - scale.lo) / (scale.hi - scale.lo);
  return Math.min(1, Math.max(0, t));
}

export function decades(scale: LogScale): number[] {
  const out: number[] = [];
  for (let e = scale.lo; e <= scale.hi; e += 1) out.push(e);
  return out;
}

/** "10", "1k", "1M", "1G": decade labels as engineers write them. */
export function decadeLabel(exponent: number): string {
  if (exponent < 0) return `10${superscript(exponent)}`;
  const units = ["", "k", "M", "G", "T", "P"];
  const group = Math.floor(exponent / 3);
  if (group >= units.length) return `10${superscript(exponent)}`;
  return `${10 ** (exponent - group * 3)}${units[group]}`;
}

const SUPERSCRIPT: Record<string, string> = {
  "-": "⁻",
  "0": "⁰",
  "1": "¹",
  "2": "²",
  "3": "³",
  "4": "⁴",
  "5": "⁵",
  "6": "⁶",
  "7": "⁷",
  "8": "⁸",
  "9": "⁹",
};

function superscript(n: number): string {
  return String(n)
    .split("")
    .map((c) => SUPERSCRIPT[c] ?? c)
    .join("");
}

/**
 * The risk dial's range: 0 to the first of 10%, 20%, 25%, 50% or 100% that holds every risk
 * and the threshold with room to spare. Calibrated risks of SECOM units are small, so a 0 to
 * 100% dial would put every unit at its foot.
 */
export function riskDomain(risks: readonly number[], threshold: number): number {
  const top = Math.max(threshold, ...risks.filter((r) => Number.isFinite(r)));
  return [0.1, 0.2, 0.25, 0.5, 1].find((d) => top <= d * 0.85) ?? 1;
}

/** A dial's angle, in degrees, for a position 0 to 1 over a sweep centred on 12 o'clock. */
export function dialAngle(t: number, sweep = 240): number {
  return -sweep / 2 + sweep * Math.min(1, Math.max(0, t));
}

/** Point on a circle of radius r around (cx, cy), at an angle in degrees from 12 o'clock. */
export function polar(cx: number, cy: number, r: number, degrees: number): [number, number] {
  const a = ((degrees - 90) * Math.PI) / 180;
  return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
}

/** SVG arc path from angle a0 to a1 (degrees from 12 o'clock, clockwise). */
export function arcPath(cx: number, cy: number, r: number, a0: number, a1: number): string {
  const [x0, y0] = polar(cx, cy, r, a0);
  const [x1, y1] = polar(cx, cy, r, a1);
  const large = Math.abs(a1 - a0) > 180 ? 1 : 0;
  const sweep = a1 >= a0 ? 1 : 0;
  return `M ${fixed(x0)} ${fixed(y0)} A ${r} ${r} 0 ${large} ${sweep} ${fixed(x1)} ${fixed(y1)}`;
}

/** Two decimals, without "-0.00". */
export function fixed(v: number): string {
  return (Math.abs(v) < 0.005 ? 0 : v).toFixed(2);
}

/**
 * How many units the line walks through one by one. Above `max`, it shows every k-th unit plus
 * every unit that raised an alarm, and says so; the drawer always lists all of them.
 */
export function unitsToShow(
  count: number,
  alarmUnits: ReadonlySet<number>,
  max = 120,
): { units: number[]; step: number } {
  if (count <= max) return { units: Array.from({ length: count }, (_, i) => i), step: 1 };
  const step = Math.ceil(count / max);
  const set = new Set<number>(alarmUnits);
  for (let i = 0; i < count; i += step) set.add(i);
  set.add(count - 1);
  return { units: [...set].filter((i) => i >= 0 && i < count).sort((a, b) => a - b), step };
}
