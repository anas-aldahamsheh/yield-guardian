import {
  WAFER_CELL,
  decodeWaferCells,
  type DrawLayoutList,
  type WaferInput,
} from "@yield-guardian/contracts";

/**
 * The drawing tool's model, kept pure so it is tested on its own: wafers painted on one real die
 * layout. Every die starts as pass; painting sets dies to fail, erasing sets them back to pass,
 * and positions without a die never change. The wafers go to the run as WM-811K maps (0 no die,
 * 1 pass, 2 fail) in one lot named for what they are: the user's drawing.
 */

export type DrawLayout = DrawLayoutList["items"][number];

export const DRAWING_LOT = "your drawing";
export const MAX_DRAWN_WAFERS = 25;

export interface Drawing {
  layout: DrawLayout;
  height: number;
  width: number;
  /** The layout's cells: which positions carry a die. */
  base: Uint8Array;
  /** One map per wafer, row-major, WM-811K values. */
  wafers: Uint8Array[];
  /** The wafer being painted. */
  current: number;
}

export type Brush = 1 | 3;
export type Paint = "fail" | "pass";

export function newDrawing(layout: DrawLayout): Drawing {
  const base = decodeWaferCells(layout.map);
  // A layout comes with every die set to pass; anything else on it is read as a die that passes.
  const clean = base.map((v) => (v === WAFER_CELL.noDie ? WAFER_CELL.noDie : WAFER_CELL.pass));
  return {
    layout,
    height: layout.map.height,
    width: layout.map.width,
    base: clean,
    wafers: [clean.slice()],
    current: 0,
  };
}

export function isDie(drawing: Drawing, index: number): boolean {
  return index >= 0 && index < drawing.base.length && drawing.base[index] !== WAFER_CELL.noDie;
}

/** Die positions a brush covers when centred on (row, col): the die itself, or a 3 by 3 block. */
export function brushCells(drawing: Drawing, row: number, col: number, brush: Brush): number[] {
  const out: number[] = [];
  const r = brush === 3 ? 1 : 0;
  for (let y = row - r; y <= row + r; y += 1) {
    if (y < 0 || y >= drawing.height) continue;
    for (let x = col - r; x <= col + r; x += 1) {
      if (x < 0 || x >= drawing.width) continue;
      const i = y * drawing.width + x;
      if (isDie(drawing, i)) out.push(i);
    }
  }
  return out;
}

/** Paints the cells on the current wafer; the same drawing when nothing changes. */
export function paint(drawing: Drawing, cells: readonly number[], value: Paint): Drawing {
  const map = drawing.wafers[drawing.current]!;
  const v = value === "fail" ? WAFER_CELL.fail : WAFER_CELL.pass;
  const changed = cells.filter((i) => isDie(drawing, i) && map[i] !== v);
  if (!changed.length) return drawing;
  const next = map.slice();
  for (const i of changed) next[i] = v;
  const wafers = drawing.wafers.slice();
  wafers[drawing.current] = next;
  return { ...drawing, wafers };
}

/** What a stroke started on this die paints: fail on a passing die, pass on a failing one. */
export function strokeValue(drawing: Drawing, index: number): Paint {
  return drawing.wafers[drawing.current]![index] === WAFER_CELL.fail ? "pass" : "fail";
}

export function clearWafer(drawing: Drawing): Drawing {
  const wafers = drawing.wafers.slice();
  wafers[drawing.current] = drawing.base.slice();
  return { ...drawing, wafers };
}

/** Adds a wafer after the current one, a copy of it (so a pattern can repeat through the lot). */
export function addWafer(drawing: Drawing, copy = true): Drawing {
  if (drawing.wafers.length >= MAX_DRAWN_WAFERS) return drawing;
  const wafers = drawing.wafers.slice();
  const map = copy ? drawing.wafers[drawing.current]!.slice() : drawing.base.slice();
  wafers.splice(drawing.current + 1, 0, map);
  return { ...drawing, wafers, current: drawing.current + 1 };
}

export function removeWafer(drawing: Drawing): Drawing {
  if (drawing.wafers.length <= 1) return drawing;
  const wafers = drawing.wafers.filter((_, i) => i !== drawing.current);
  return { ...drawing, wafers, current: Math.min(drawing.current, wafers.length - 1) };
}

export function selectWafer(drawing: Drawing, index: number): Drawing {
  if (index < 0 || index >= drawing.wafers.length || index === drawing.current) return drawing;
  return { ...drawing, current: index };
}

export function failCount(map: Uint8Array): number {
  let n = 0;
  for (const v of map) if (v === WAFER_CELL.fail) n += 1;
  return n;
}

export function dieCount(drawing: Drawing): number {
  let n = 0;
  for (const v of drawing.base) if (v !== WAFER_CELL.noDie) n += 1;
  return n;
}

export type Direction = "up" | "down" | "left" | "right";

/**
 * The keyboard cursor's next die: the nearest die in that direction along the row or column,
 * or the same place at the edge of the layout.
 */
export function moveCursor(drawing: Drawing, index: number, direction: Direction): number {
  const { width, height } = drawing;
  let row = Math.floor(index / width);
  let col = index % width;
  const dr = direction === "up" ? -1 : direction === "down" ? 1 : 0;
  const dc = direction === "left" ? -1 : direction === "right" ? 1 : 0;
  for (;;) {
    row += dr;
    col += dc;
    if (row < 0 || row >= height || col < 0 || col >= width) return index;
    const i = row * width + col;
    if (isDie(drawing, i)) return i;
  }
}

/** The die nearest the layout's centre, where the keyboard cursor starts. */
export function centreDie(drawing: Drawing): number {
  const cy = (drawing.height - 1) / 2;
  const cx = (drawing.width - 1) / 2;
  let best = -1;
  let bestD = Infinity;
  for (let i = 0; i < drawing.base.length; i += 1) {
    if (!isDie(drawing, i)) continue;
    const d = (Math.floor(i / drawing.width) - cy) ** 2 + ((i % drawing.width) - cx) ** 2;
    if (d < bestD) {
      bestD = d;
      best = i;
    }
  }
  return best;
}

function toBase64(bytes: Uint8Array): string {
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000)
    s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

/** A drawing as kept between reloads of the tab (lib/live/drafts.ts): its maps in base64. */
export function drawingDraft(drawing: Drawing): { wafers: string[]; current: number } {
  return { wafers: drawing.wafers.map(toBase64), current: drawing.current };
}

/**
 * A drawing back from its draft on its layout, or null when the draft does not fit the layout:
 * every map has the layout's size, no die where the layout has none, and pass or fail on a die.
 */
export function restoreDrawing(
  layout: DrawLayout,
  draft: { wafers: readonly string[]; current: number },
): Drawing | null {
  if (!draft.wafers.length || draft.wafers.length > MAX_DRAWN_WAFERS) return null;
  const drawing = newDrawing(layout);
  const wafers: Uint8Array[] = [];
  for (const cells of draft.wafers) {
    let map: Uint8Array;
    try {
      map = decodeWaferCells({ ...layout.map, encoding: "uint8-base64", cells });
    } catch {
      return null;
    }
    for (let i = 0; i < map.length; i += 1) {
      const fits =
        drawing.base[i] === WAFER_CELL.noDie
          ? map[i] === WAFER_CELL.noDie
          : map[i] === WAFER_CELL.pass || map[i] === WAFER_CELL.fail;
      if (!fits) return null;
    }
    wafers.push(map);
  }
  const current = Math.min(Math.max(0, Math.trunc(draft.current)), wafers.length - 1);
  return { ...drawing, wafers, current };
}

/** The wafers as the run's input: lot "your drawing", wafers numbered from 1, no recorded label. */
export function drawnWafers(drawing: Drawing): WaferInput[] {
  return drawing.wafers.map((map, i) => ({
    lot: DRAWING_LOT,
    wafer: i + 1,
    map: {
      height: drawing.height,
      width: drawing.width,
      encoding: "uint8-base64",
      cells: toBase64(map),
    },
    label: null,
    source_wafer: null,
  }));
}
