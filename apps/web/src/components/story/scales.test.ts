import {
  arcPath,
  decadeLabel,
  dialAngle,
  lampLevel,
  logDomain,
  logPosition,
  polar,
  riskDomain,
  unitsToShow,
} from "./scales";

describe("instrument scales", () => {
  it("lights a sensor by |z| up to 4, and leaves missing readings dark", () => {
    expect(lampLevel(0)).toBe(0);
    expect(lampLevel(-2)).toBe(0.5);
    expect(lampLevel(9)).toBe(1);
    expect(lampLevel(null)).toBe(0);
    expect(lampLevel(Number.NaN)).toBe(0);
  });

  it("spans whole decades that hold the values and limits of the real T² and SPE", () => {
    // SECOM v1 limits (fdc_model.npz) and the extremes of the story fixture's units.
    const t2 = logDomain([19.3, 2177.4, 1.909e8], [228.33, 285.01]);
    expect(t2).toEqual({ lo: 1, hi: 9 });
    const spe = logDomain([198.7, 2.3187e9], [33919.7, 97088.7]);
    expect(spe).toEqual({ lo: 2, hi: 10 });
    expect(logPosition(285.01, t2)).toBeCloseTo((Math.log10(285.01) - 1) / 8, 10);
    expect(logPosition(1e12, t2)).toBe(1);
    expect(logPosition(0, t2)).toBe(0);
  });

  it("keeps a decade below the 99% limit", () => {
    expect(logDomain([300], [250, 300]).lo).toBe(1);
  });

  it("writes decades as engineers do", () => {
    expect([0, 1, 2, 3, 4, 6, 9].map(decadeLabel)).toEqual([
      "1",
      "10",
      "100",
      "1k",
      "10k",
      "1M",
      "1G",
    ]);
    expect(decadeLabel(-2)).toBe("10⁻²");
  });

  it("sizes the risk dial to the calibrated risks", () => {
    expect(riskDomain([0.01, 0.133], 0.0787)).toBe(0.2);
    expect(riskDomain([0.05], 0.0787)).toBe(0.1);
    expect(riskDomain([0.9], 0.0787)).toBe(1);
  });

  it("draws dial geometry from 12 o'clock", () => {
    expect(dialAngle(0)).toBe(-120);
    expect(dialAngle(0.5)).toBe(0);
    expect(dialAngle(2)).toBe(120);
    const [x, y] = polar(0, 0, 10, 90);
    expect(x).toBeCloseTo(10);
    expect(y).toBeCloseTo(0);
    expect(arcPath(0, 0, 10, -90, 90)).toBe("M -10.00 0.00 A 10 10 0 0 1 10.00 0.00");
  });

  it("walks every unit up to 120, then every k-th unit plus every alarm", () => {
    expect(unitsToShow(30, new Set()).units).toHaveLength(30);
    const many = unitsToShow(600, new Set([7, 333]));
    expect(many.step).toBe(5);
    expect(many.units).toContain(7);
    expect(many.units).toContain(333);
    expect(many.units).toContain(599);
    expect(many.units.length).toBeLessThanOrEqual(123);
  });
});
