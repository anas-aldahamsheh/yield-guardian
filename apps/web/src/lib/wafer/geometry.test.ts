import { decodeWaferCells } from "@yield-guardian/contracts";

import { FILM, filmThicknessAt, layoutDies, planExposure } from "./geometry";

function grid(rows: string[]) {
  const height = rows.length;
  const width = rows[0]!.length;
  const cells = Uint8Array.from(rows.join("").split("").map(Number));
  return { height, width, cells };
}

describe("decodeWaferCells", () => {
  it("decodes base64 row-major bytes", () => {
    const cells = decodeWaferCells({
      encoding: "uint8-base64",
      height: 2,
      width: 3,
      cells: btoa("\x00\x01\x02\x01\x01\x00"),
    });
    expect(Array.from(cells)).toEqual([0, 1, 2, 1, 1, 0]);
  });

  it("rejects a map whose size does not match", () => {
    expect(() =>
      decodeWaferCells({ encoding: "uint8-base64", height: 2, width: 2, cells: btoa("\x00\x01") }),
    ).toThrow();
  });

  it("rejects values other than 0, 1 and 2", () => {
    expect(() =>
      decodeWaferCells({ encoding: "uint8-base64", height: 1, width: 1, cells: btoa("\x03") }),
    ).toThrow();
  });
});

describe("layoutDies", () => {
  const map = grid(["0110", "1221", "1111", "0110"]);
  const layout = layoutDies(map);

  it("keeps every die and counts pass and fail", () => {
    expect(layout.dies).toHaveLength(12);
    expect(layout.pass).toBe(10);
    expect(layout.fail).toBe(2);
  });

  it("centres the map on the wafer", () => {
    const xs = layout.dies.map((d) => d.x);
    expect(Math.min(...xs) + Math.max(...xs)).toBeCloseTo(0, 12);
    expect(layout.dies.every((d) => Math.hypot(d.x, d.y) < 1)).toBe(true);
  });

  it("marks failed dies", () => {
    expect(layout.dies.filter((d) => d.failed).map((d) => [d.row, d.col])).toEqual([
      [1, 1],
      [1, 2],
    ]);
  });

  it("refuses cells that do not match the size", () => {
    expect(() => layoutDies({ height: 2, width: 2, cells: new Uint8Array(3) })).toThrow();
  });
});

describe("planExposure", () => {
  const map = grid(["01110", "11111", "11211", "11111", "01110"]);
  const layout = layoutDies(map);
  const plan = planExposure(map, layout, 3);

  it("walks the fields that hold dies in a serpentine path", () => {
    expect(plan.diesPerField).toBe(2);
    expect(plan.fields.map((f) => [f.row, f.col])).toEqual([
      [0, 0],
      [0, 1],
      [0, 2],
      [1, 2],
      [1, 1],
      [1, 0],
      [2, 0],
      [2, 1],
    ]);
  });

  it("assigns every die to the field that covers it", () => {
    layout.dies.forEach((die, i) => {
      const field = plan.fields[plan.dieField[i]!]!;
      expect(Math.abs(die.x - field.x)).toBeLessThanOrEqual(field.size / 2);
      expect(Math.abs(die.y - field.y)).toBeLessThanOrEqual(field.size / 2);
    });
  });

  it("skips fields without dies", () => {
    const sparse = grid(["1000", "0000", "0000", "0001"]);
    const sparsePlan = planExposure(sparse, layoutDies(sparse), 2);
    expect(sparsePlan.fields).toHaveLength(2);
  });
});

describe("filmThicknessAt", () => {
  it("is thickest at the centre and thins towards the edge", () => {
    expect(filmThicknessAt(0, 0)).toBe(FILM.centreNm);
    expect(filmThicknessAt(1, 0)).toBeCloseTo(FILM.centreNm * (1 - FILM.edgeDrop), 10);
    expect(filmThicknessAt(0.5, 0)).toBeGreaterThan(filmThicknessAt(0.9, 0));
  });
});
