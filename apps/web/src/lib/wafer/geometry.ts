import { WAFER_CELL } from "@yield-guardian/contracts";

/**
 * Geometry of a die map for drawing: die positions on a unit wafer, counts, and the exposure
 * fields a stepper would walk. Input is the decoded map: row-major cells, 0 no die, 1 pass,
 * 2 fail (WaferMap in the contracts).
 */

export interface DieGrid {
  height: number;
  width: number;
  cells: Uint8Array;
}

export interface Die {
  /** Index of the cell in the row-major map. */
  index: number;
  row: number;
  col: number;
  /** Centre on a wafer of radius 1, x to the right, y down the map (rows). */
  x: number;
  y: number;
  failed: boolean;
}

export interface DieLayout {
  dies: Die[];
  /** Die pitch on the unit wafer. */
  pitch: number;
  pass: number;
  fail: number;
}

/** Share of the wafer diameter the die map spans (WM-811K maps run edge to edge). */
const MAP_SPAN = 1.9;

export function layoutDies(grid: DieGrid): DieLayout {
  const { height, width, cells } = grid;
  if (cells.length !== height * width) {
    throw new Error(`Expected ${height * width} cells, got ${cells.length}`);
  }
  const pitch = MAP_SPAN / Math.max(height, width);
  const dies: Die[] = [];
  let pass = 0;
  let fail = 0;
  for (let row = 0; row < height; row += 1) {
    for (let col = 0; col < width; col += 1) {
      const index = row * width + col;
      const cell = cells[index]!;
      if (cell === WAFER_CELL.noDie) continue;
      const failed = cell === WAFER_CELL.fail;
      if (failed) fail += 1;
      else pass += 1;
      dies.push({
        index,
        row,
        col,
        x: (col + 0.5 - width / 2) * pitch,
        y: (row + 0.5 - height / 2) * pitch,
        failed,
      });
    }
  }
  return { dies, pitch, pass, fail };
}

export interface ExposureField {
  /** Order in which the stepper exposes this field (serpentine, row by row). */
  order: number;
  row: number;
  col: number;
  /** Centre and size on the unit wafer. */
  x: number;
  y: number;
  size: number;
}

export interface ExposurePlan {
  fields: ExposureField[];
  /** Field order of each die (same order as `layout.dies`). */
  dieField: Int32Array;
  /** Dies per field side. */
  diesPerField: number;
}

/**
 * Split the map into square fields of `diesPerField` dies and order the fields that contain at
 * least one die in a serpentine path, the way a step-and-repeat stepper walks a wafer.
 */
export function planExposure(grid: DieGrid, layout: DieLayout, fieldsAcross = 6): ExposurePlan {
  const span = Math.max(grid.height, grid.width);
  const diesPerField = Math.max(1, Math.ceil(span / fieldsAcross));
  const fieldRows = Math.ceil(grid.height / diesPerField);
  const fieldCols = Math.ceil(grid.width / diesPerField);
  const occupied = new Set<number>();
  for (const die of layout.dies) {
    occupied.add(
      Math.floor(die.row / diesPerField) * fieldCols + Math.floor(die.col / diesPerField),
    );
  }

  const fields: ExposureField[] = [];
  const orderOf = new Map<number, number>();
  for (let fr = 0; fr < fieldRows; fr += 1) {
    const cols = Array.from({ length: fieldCols }, (_, i) =>
      fr % 2 === 0 ? i : fieldCols - 1 - i,
    );
    for (const fc of cols) {
      const key = fr * fieldCols + fc;
      if (!occupied.has(key)) continue;
      const order = fields.length;
      orderOf.set(key, order);
      const size = diesPerField * layout.pitch;
      fields.push({
        order,
        row: fr,
        col: fc,
        x: (fc * diesPerField + diesPerField / 2 - grid.width / 2) * layout.pitch,
        y: (fr * diesPerField + diesPerField / 2 - grid.height / 2) * layout.pitch,
        size,
      });
    }
  }

  const dieField = new Int32Array(layout.dies.length);
  layout.dies.forEach((die, i) => {
    const key = Math.floor(die.row / diesPerField) * fieldCols + Math.floor(die.col / diesPerField);
    dieField[i] = orderOf.get(key)!;
  });
  return { fields, dieField, diesPerField };
}

/**
 * Oxide thickness across the wafer, nm. WM-811K records no film data, so the wafer is drawn with
 * an assumed film: `centreNm` at the centre, thinning by `edgeDrop` towards the edge (a typical
 * deposition profile). Used only for colour, and labelled as assumed where it is shown.
 */
export const FILM = { centreNm: 340, edgeDrop: 0.045 } as const;

export function filmThicknessAt(x: number, y: number): number {
  const r2 = Math.min(1, x * x + y * y);
  return FILM.centreNm * (1 - FILM.edgeDrop * r2);
}
