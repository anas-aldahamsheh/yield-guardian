import { paletteHex as token, palettes, systemDarkPalette, type Theme } from "@/test/palettes";

import { contrastRatio, hexToLinearSrgb, linearSrgbToOklab, type Vec3 } from "./optics/oklab";

/**
 * WCAG 2.2 contrast of the colour tokens in both themes, read from globals.css so that a token
 * change that breaks accessibility fails the build. Text needs 4.5:1 (1.4.3); marks, focus
 * outlines and control edges need 3:1 (1.4.11).
 */

describe("palettes", () => {
  it("define the same tokens in both themes", () => {
    expect([...palettes.dark.keys()].sort()).toEqual([...palettes.light.keys()].sort());
  });

  it("write the yellow room identically for the system preference", () => {
    expect(Object.fromEntries(systemDarkPalette)).toEqual(Object.fromEntries(palettes.dark));
  });
});

const SURFACES = ["room", "die", "die-2"] as const;
const THEMES: Theme[] = ["light", "dark"];

const REQUIREMENTS: [name: string, minimum: number, job: string][] = [
  ["ink", 7, "body text (AAA)"],
  ["ink-2", 4.5, "secondary text"],
  ["ink-3", 4.5, "muted text and axis labels"],
  ["safelight", 3, "focus outline and selection marks"],
  ["pass", 3, "pass marks"],
  ["fail", 3, "fail marks"],
  ["concern", 3, "elevated-risk marks"],
  ["mark-muted", 3, "baseline series"],
  ["edge", 3, "control edges"],
];

describe.each(THEMES)("%s theme", (theme) => {
  it.each(REQUIREMENTS)("%s reaches %d:1 on every surface (%s)", (name, minimum) => {
    for (const surface of SURFACES) {
      expect(contrastRatio(token(name, theme), token(surface, theme))).toBeGreaterThanOrEqual(
        minimum,
      );
    }
  });

  it("keeps pass and fail apart for readers with colour-vision deficiency", () => {
    const pass = token("pass", theme);
    const fail = token("fail", theme);
    // OKLab ΔE ×100: at least 8 under protan and deutan simulation, 15 for normal vision.
    expect(cvdDeltaE(pass, fail, "protan")).toBeGreaterThanOrEqual(8);
    expect(cvdDeltaE(pass, fail, "deutan")).toBeGreaterThanOrEqual(8);
    expect(cvdDeltaE(pass, fail, "tritan")).toBeGreaterThanOrEqual(8);
    expect(cvdDeltaE(pass, fail)).toBeGreaterThanOrEqual(15);
  });
});

/** Machado, Oliveira and Fernandes (2009) dichromacy simulation, severity 1, linear sRGB. */
const MACHADO = {
  protan: [
    [0.152286, 1.052583, -0.204868],
    [0.114503, 0.786281, 0.099216],
    [-0.003882, -0.048116, 1.051998],
  ],
  deutan: [
    [0.367322, 0.860646, -0.227968],
    [0.280085, 0.672501, 0.047413],
    [-0.01182, 0.04294, 0.968881],
  ],
  tritan: [
    [1.255528, -0.076749, -0.178779],
    [-0.078411, 0.930809, 0.147602],
    [0.004733, 0.691367, 0.3039],
  ],
} as const;

function cvdDeltaE(hexA: string, hexB: string, kind?: keyof typeof MACHADO): number {
  const see = (hex: string): Vec3 => {
    const rgb = hexToLinearSrgb(hex);
    if (!kind) return linearSrgbToOklab(rgb);
    const m = MACHADO[kind];
    const clamp = (c: number) => Math.min(1, Math.max(0, c));
    return linearSrgbToOklab(
      m.map((row) => clamp(row[0] * rgb[0] + row[1] * rgb[1] + row[2] * rgb[2])) as Vec3,
    );
  };
  const a = see(hexA);
  const b = see(hexB);
  return 100 * Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}
