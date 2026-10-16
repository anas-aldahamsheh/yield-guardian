/**
 * A lossless, compact JSON form for the run's stored state in the Line page: every list of like
 * objects (a run's units, wafers, alarms, drift groups) as columns, so a field's name is written
 * once instead of once per row, and a column holding one value throughout (every unit's details
 * left out, a model's base value) as that value once. A run of the whole SECOM data set (1,567
 * units) takes about half the room it would as plain JSON, and less again once React has
 * escaped it into the page.
 *
 * Only the transport changes: unpack(pack(x)) is x, field for field.
 */

declare const PACKED: unique symbol;
/** `T` in packed form: only `unpack` reads it. */
export type Packed<T> = { readonly [PACKED]: T };

type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
type JsonObject = { [key: string]: Json };

/** Marks a list of like objects: `{ "~rows": keys, n, cols }`, one column per key. */
const ROWS = "~rows";
/** Marks a list of one value throughout: `{ "~same": value, n }`. */
const SAME = "~same";
/** Shorter lists are kept as they are: their keys cost less than the columns' frame. */
const MIN_ROWS = 4;

export function pack<T>(value: T): Packed<T> {
  return packValue(value as Json) as unknown as Packed<T>;
}

export function unpack<T>(packed: Packed<T>): T {
  return unpackValue(packed as unknown as Json) as T;
}

function isObject(value: Json | undefined): value is JsonObject {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function packValue(value: Json): Json {
  if (Array.isArray(value)) return packList(value);
  if (isObject(value)) {
    const out: JsonObject = {};
    for (const [key, v] of Object.entries(value)) if (v !== undefined) out[key] = packValue(v);
    return out;
  }
  return value;
}

function keysOf(row: JsonObject): string[] {
  return Object.keys(row).filter((key) => row[key] !== undefined);
}

function packList(list: Json[]): Json {
  if (list.length >= MIN_ROWS) {
    const first = list[0]!;
    if (first === null || typeof first !== "object") {
      if (list.every((v) => v === first)) return { [SAME]: first, n: list.length };
    } else if (isObject(first)) {
      const keys = keysOf(first);
      const alike = list.every(
        (row) => isObject(row) && keysOf(row).length === keys.length && keys.every((k) => k in row),
      );
      if (alike) {
        const rows = list as JsonObject[];
        return {
          [ROWS]: keys,
          n: rows.length,
          cols: keys.map((key) => packList(rows.map((row) => row[key]!))),
        };
      }
    }
  }
  return list.map(packValue);
}

function unpackValue(value: Json): Json {
  if (Array.isArray(value)) return value.map(unpackValue);
  if (!isObject(value)) return value;
  if (SAME in value) {
    const same = value[SAME]!;
    return Array.from({ length: value.n as number }, () => same);
  }
  if (ROWS in value) {
    const keys = value[ROWS] as string[];
    const n = value.n as number;
    const cols = (value.cols as Json[]).map((col) => unpackValue(col) as Json[]);
    return Array.from({ length: n }, (_, i) => {
      const row: JsonObject = {};
      keys.forEach((key, k) => {
        row[key] = cols[k]![i]!;
      });
      return row;
    });
  }
  const out: JsonObject = {};
  for (const [key, v] of Object.entries(value)) out[key] = unpackValue(v);
  return out;
}
