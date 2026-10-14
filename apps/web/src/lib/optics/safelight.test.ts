import { globalsCss, paletteHex } from "@/test/palettes";

import { contrastRatio, deltaEOk } from "./oklab";
import {
  SAFELIGHT_SPECTRUM,
  safelightChromaticity,
  safelightHue,
  safelightTokenHex,
} from "./safelight";

describe("safelight", () => {
  it("has no power below the 500 nm cut-off", () => {
    SAFELIGHT_SPECTRUM.forEach((power, i) => {
      if (380 + 5 * i < 500) expect(power).toBe(0);
    });
  });

  it("matches colour-science for FL11 behind a 500 nm long-pass filter", () => {
    // colour-science 0.4.7: xy (0.4798, 0.5116), OKLCH hue 96.8°.
    const [x, y] = safelightChromaticity();
    expect(x).toBeCloseTo(0.4798, 3);
    expect(y).toBeCloseTo(0.5116, 3);
    expect(safelightHue()).toBeCloseTo(96.8, 1);
  });

  it("is a golden yellow, not an orange amber", () => {
    const hue = safelightHue();
    expect(hue).toBeGreaterThan(90);
    expect(hue).toBeLessThan(105);
  });

  it("is the value of --safelight-lamp and of the dark --safelight token", () => {
    const token = safelightTokenHex();
    expect(globalsCss).toContain(`--safelight-lamp: ${token};`);
    expect(paletteHex("safelight", "dark")).toBe(token);
  });

  it("reads as light on the dark room (well above 3:1)", () => {
    expect(contrastRatio(safelightTokenHex(), paletteHex("room", "dark"))).toBeGreaterThan(10);
  });

  it("stays distinct from the fail colour, so light never reads as an error", () => {
    expect(deltaEOk(safelightTokenHex(), "#eb556e")).toBeGreaterThan(30);
  });
});
