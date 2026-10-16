import { WAFER_CELL, decodeWaferCells, type WaferMap } from "@yield-guardian/contracts";

import type { DieGrid } from "@/lib/wafer/geometry";

/**
 * The order the prober visits the dies of a map: row by row from the top, left to right on even
 * rows and right to left on odd rows (a serpentine, how a prober steps to keep moves short).
 * WM-811K records results, not the probe sequence, so this is the order drawn, and it is the
 * order of planExposure with one die per field.
 */
export function probeOrder(grid: DieGrid): Int32Array {
  const out: number[] = [];
  for (let row = 0; row < grid.height; row += 1) {
    const even = row % 2 === 0;
    for (let k = 0; k < grid.width; k += 1) {
      const col = even ? k : grid.width - 1 - k;
      const index = row * grid.width + col;
      if (grid.cells[index] !== WAFER_CELL.noDie) out.push(index);
    }
  }
  return Int32Array.from(out);
}

export function gridOf(map: WaferMap): DieGrid {
  return { height: map.height, width: map.width, cells: decodeWaferCells(map) };
}

/** Running count of failed dies along the probe order (fails[i] = failed among the first i dies). */
export function failsAlong(grid: DieGrid, order: Int32Array): Int32Array {
  const fails = new Int32Array(order.length + 1);
  for (let i = 0; i < order.length; i += 1) {
    fails[i + 1] = fails[i]! + (grid.cells[order[i]!] === WAFER_CELL.fail ? 1 : 0);
  }
  return fails;
}
