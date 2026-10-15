import { WAFER_CELL, decodeWaferCells } from "@yield-guardian/contracts";
import { describe, expect, it } from "vitest";

import { fixture } from "../../../e2e/story/fixture";

import {
  DRAWING_LOT,
  MAX_DRAWN_WAFERS,
  addWafer,
  brushCells,
  centreDie,
  clearWafer,
  dieCount,
  drawnWafers,
  failCount,
  isDie,
  moveCursor,
  newDrawing,
  paint,
  removeWafer,
  selectWafer,
  strokeValue,
} from "./draw-model";

// Real WM-811K die layouts from the wafer engine, every die set to pass.
const layouts = fixture.layouts.items;
const layout = layouts[0]!;

/** The outermost ring of dies: dies with a no-die position (or the map edge) next to them. */
function outerRing(d: ReturnType<typeof newDrawing>): number[] {
  const out: number[] = [];
  for (let i = 0; i < d.base.length; i += 1) {
    if (!isDie(d, i)) continue;
    const r = Math.floor(i / d.width);
    const c = i % d.width;
    const edge = [
      [r - 1, c],
      [r + 1, c],
      [r, c - 1],
      [r, c + 1],
    ].some(
      ([y, x]) =>
        y! < 0 || y! >= d.height || x! < 0 || x! >= d.width || !isDie(d, y! * d.width + x!),
    );
    if (edge) out.push(i);
  }
  return out;
}

describe("the drawing tool", () => {
  it("starts with every die of the real layout passing", () => {
    for (const l of layouts) {
      const d = newDrawing(l);
      const source = decodeWaferCells(l.map);
      expect(d.wafers).toHaveLength(1);
      expect(failCount(d.wafers[0]!)).toBe(0);
      expect(dieCount(d)).toBe(source.filter((v) => v !== WAFER_CELL.noDie).length);
      expect(
        Array.from(d.wafers[0]!).every(
          (v, i) => (v === WAFER_CELL.noDie) === (source[i] === WAFER_CELL.noDie),
        ),
      ).toBe(true);
    }
  });

  it("paints fail and erases to pass, and never puts a die where the layout has none", () => {
    let d = newDrawing(layout);
    const noDie = Array.from(d.base).findIndex((v) => v === WAFER_CELL.noDie);
    const die = centreDie(d);
    expect(noDie).toBeGreaterThanOrEqual(0);
    expect(strokeValue(d, die)).toBe("fail");
    d = paint(d, [die, noDie], "fail");
    expect(d.wafers[0]![die]).toBe(WAFER_CELL.fail);
    expect(d.wafers[0]![noDie]).toBe(WAFER_CELL.noDie);
    expect(strokeValue(d, die)).toBe("pass");
    const same = paint(d, [die], "fail");
    expect(same).toBe(d);
    d = paint(d, [die], "pass");
    expect(d.wafers[0]![die]).toBe(WAFER_CELL.pass);
    expect(failCount(d.wafers[0]!)).toBe(0);
  });

  it("covers a 3 by 3 block with the wide brush, clipped to the layout's dies", () => {
    const d = newDrawing(layout);
    const die = centreDie(d);
    const r = Math.floor(die / d.width);
    const c = die % d.width;
    expect(brushCells(d, r, c, 1)).toEqual([die]);
    expect(brushCells(d, r, c, 3)).toHaveLength(9);
    const corner = brushCells(d, 0, 0, 3);
    expect(corner.every((i) => isDie(d, i))).toBe(true);
    expect(corner.length).toBeLessThan(9);
  });

  it("moves the keyboard cursor die by die and stops at the edge", () => {
    const d = newDrawing(layout);
    let i = centreDie(d);
    const row = Math.floor(i / d.width);
    for (let k = 0; k < d.width; k += 1) i = moveCursor(d, i, "left");
    expect(Math.floor(i / d.width)).toBe(row);
    expect(isDie(d, i)).toBe(true);
    expect(i % d.width === 0 || !isDie(d, i - 1)).toBe(true);
    expect(moveCursor(d, i, "left")).toBe(i);
    const right = moveCursor(d, i, "right");
    expect(right).toBe(i + 1);
  });

  it("keeps 1 to 25 wafers, each painted on its own", () => {
    let d = newDrawing(layout);
    d = paint(d, [centreDie(d)], "fail");
    d = addWafer(d);
    expect(d.wafers).toHaveLength(2);
    expect(d.current).toBe(1);
    expect(failCount(d.wafers[1]!)).toBe(1);
    d = clearWafer(d);
    expect(failCount(d.wafers[1]!)).toBe(0);
    expect(failCount(d.wafers[0]!)).toBe(1);
    d = addWafer(d, false);
    expect(d.wafers).toHaveLength(3);
    for (let k = 0; k < 40; k += 1) d = addWafer(d);
    expect(d.wafers).toHaveLength(MAX_DRAWN_WAFERS);
    d = selectWafer(d, 0);
    for (let k = 0; k < 40; k += 1) d = removeWafer(d);
    expect(d.wafers).toHaveLength(1);
  });

  it("sends the outer ring of every real layout as WM-811K maps labelled as the drawing", () => {
    for (const l of layouts) {
      let d = newDrawing(l);
      const ring = outerRing(d);
      d = paint(d, ring, "fail");
      d = addWafer(d);
      const wafers = drawnWafers(d);
      expect(wafers).toHaveLength(2);
      wafers.forEach((w, k) => {
        expect(w.lot).toBe(DRAWING_LOT);
        expect(w.wafer).toBe(k + 1);
        expect(w.label).toBeNull();
        expect(w.source_wafer).toBeNull();
        const cells = decodeWaferCells(w.map);
        expect(cells).toEqual(d.wafers[k]);
        expect(failCount(cells)).toBe(ring.length);
      });
    }
  });
});
