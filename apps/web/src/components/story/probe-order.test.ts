import { layoutDies, planExposure } from "@/lib/wafer/geometry";

import { sampleEvents } from "../../../e2e/story/fixture";

import { failsAlong, gridOf, probeOrder } from "./probe-order";

function realGrid() {
  const result = sampleEvents.find((e) => e.type === "stage_result" && e.stage === "wafer_pattern");
  if (result?.type !== "stage_result" || result.result.stage !== "wafer_pattern")
    throw new Error("no wafers");
  return gridOf(result.result.wafers[0]!.map);
}

describe("probe order", () => {
  it("visits every die once, in a serpentine by rows", () => {
    const grid = { height: 2, width: 3, cells: Uint8Array.from([0, 1, 2, 1, 1, 0]) };
    expect([...probeOrder(grid)]).toEqual([1, 2, 4, 3]);
  });

  it("is the order of the 3D wafer's fields with one die per field", () => {
    const grid = realGrid();
    const layout = layoutDies(grid);
    const plan = planExposure(grid, layout, Math.max(grid.height, grid.width));
    expect(plan.diesPerField).toBe(1);
    const byField = new Array<number>(plan.fields.length);
    layout.dies.forEach((die, i) => {
      byField[plan.dieField[i]!] = die.index;
    });
    expect([...probeOrder(grid)]).toEqual(byField);
  });

  it("counts the failed dies of the real map along the way", () => {
    const grid = realGrid();
    const order = probeOrder(grid);
    const fails = failsAlong(grid, order);
    expect(fails[order.length]).toBe(layoutDies(grid).fail);
  });
});
