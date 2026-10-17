import { describe, expect, it } from "vitest";

import { formatCompact, formatFixed, formatInt, formatNumber } from "./format";

/** Values that exercise ties, carries, signs, -0 and exponent forms of the shortest decimal. */
function samples(): number[] {
  const out = [
    0, -0, 0.5, 1.5, 2.5, -0.5, -2.5, 1.005, 1.015, 0.045, -0.001, -0.004, 999.995, 99.5, 999_999.5,
    0.0005,
  ];
  out.push(1e-7, 5e-7, 9.5e-7, 1.5e-10, 123_456.789, 1e20, 9.99e20, -2_048_784.0255, 16_995.445);
  // A fixed pseudo-random sequence, so a failure is reproducible.
  let seed = 7;
  const rand = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
  for (let k = 0; k < 20_000; k += 1) {
    let v = (rand() - 0.5) * 10 ** (Math.floor(rand() * 28) - 10);
    if (k % 3 === 0) v = Math.round(v * 1000) / 1000 + (rand() < 0.5 ? 0.0005 : 0.005);
    if (k % 5 === 0) v = Math.round(v * 2) / 2;
    out.push(v);
  }
  return out;
}

describe("formatFixed", () => {
  it(
    "writes exactly what Intl.NumberFormat en-US writes",
    () => {
      for (const digits of [0, 1, 2, 3, 4, 6]) {
        const intl = new Intl.NumberFormat("en-US", {
          minimumFractionDigits: digits,
          maximumFractionDigits: digits,
        });
        for (const v of samples())
          expect(formatFixed(v, digits), `${v} to ${digits}`).toBe(intl.format(v));
      }
    },
    15000,
  );

  it("matches Intl's integer formatting for formatInt", () => {
    const intl = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
    for (const v of samples()) expect(formatInt(v), String(v)).toBe(intl.format(v));
  });

  it("matches Intl's compact notation for formatCompact", () => {
    const intl = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
    const edges = [
      999.95, 999.94, 999_950, 999_949, 999_999, 1050, 1250, 1e12, 999_999_999_999_999,
    ];
    for (const v of [...samples(), ...edges, ...edges.map((e) => -e)])
      expect(formatCompact(v), String(v)).toBe(intl.format(v));
    expect(formatCompact(48_364)).toBe("48.4K");
    expect(formatCompact(undefined)).toBe("–");
  });

  it("keeps the dash for missing values", () => {
    expect(formatNumber(null)).toBe("–");
    expect(formatInt(Number.NaN)).toBe("–");
    expect(formatNumber(1234.5678)).toBe("1,234.57");
  });
});
