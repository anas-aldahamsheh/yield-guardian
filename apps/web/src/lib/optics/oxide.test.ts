import { paletteHex } from "@/test/palettes";

import { contrastRatio } from "./oklab";
import { FILM_THICKNESS_NM, filmHue, filmTokenHex, signalTokenHex } from "./oxide";

describe("the oxide film tokens", () => {
  it("run violet to green through the second order, as the oxide colour chart does", () => {
    const hues = FILM_THICKNESS_NM.map(filmHue);
    // Hue falls monotonically from violet (about 300 degrees) to green (about 155).
    for (let i = 1; i < hues.length; i += 1) expect(hues[i]!).toBeLessThan(hues[i - 1]!);
    expect(hues[0]!).toBeGreaterThan(290);
    expect(hues.at(-1)!).toBeLessThan(170);
  });

  it.each(["light", "dark"] as const)("are the computed values in the %s palette", (theme) => {
    FILM_THICKNESS_NM.forEach((nm, i) => {
      expect(paletteHex(`film-${i + 1}`, theme)).toBe(filmTokenHex(nm, theme));
    });
  });

  it.each(["light", "dark"] as const)("read as marks on the %s canvas (3:1)", (theme) => {
    for (const nm of FILM_THICKNESS_NM) {
      expect(contrastRatio(filmTokenHex(nm, theme), paletteHex("canvas", theme))).toBeGreaterThan(
        3,
      );
    }
  });
});

describe("the signal colour", () => {
  it.each(["light", "dark"] as const)("is the film's 310 nm hue in the %s palette", (theme) => {
    expect(paletteHex("signal", theme)).toBe(signalTokenHex(theme));
  });
});
