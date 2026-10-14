import { CIE_START_NM, CIE_STEP_NM, CMF_1931_2DEG, ILLUMINANT_FL11 } from "./cie";
import { linearSrgbToOklab, maxChroma, oklabToOklch, oklchToHex } from "./oklab";
import { xyzToLinearSrgb } from "./thinfilm";

/**
 * The yellow-room light. Lithography bays filter their lamps so that no light below about 500 nm
 * (where photoresist is sensitive) reaches the wafers. Model: CIE illuminant FL11 (narrow-band
 * tri-phosphor fluorescent tube) behind an ideal long-pass filter.
 */
export const SAFELIGHT_CUTOFF_NM = 500;

/** Spectral power of the safelight on the CIE 5 nm grid (380 to 780 nm). */
export const SAFELIGHT_SPECTRUM: readonly number[] = ILLUMINANT_FL11.map((power, i) =>
  CIE_START_NM + i * CIE_STEP_NM >= SAFELIGHT_CUTOFF_NM ? power : 0,
);

/** CIE XYZ of the safelight, normalised to Y = 1. */
export function safelightXyz(): [number, number, number] {
  let x = 0;
  let y = 0;
  let z = 0;
  CMF_1931_2DEG.forEach(([xb, yb, zb], i) => {
    const s = SAFELIGHT_SPECTRUM[i]!;
    x += s * xb;
    y += s * yb;
    z += s * zb;
  });
  return [x / y, 1, z / y];
}

/** Chromaticity (x, y) of the safelight. */
export function safelightChromaticity(): [number, number] {
  const [x, y, z] = safelightXyz();
  const sum = x + y + z;
  return [x / sum, y / sum];
}

/** OKLCH hue of the safelight in degrees. */
export function safelightHue(): number {
  return oklabToOklch(linearSrgbToOklab(xyzToLinearSrgb(safelightXyz())))[2];
}

/** Lightness of the safelight token in the dark theme (a light source, so near the top). */
export const SAFELIGHT_TOKEN_LIGHTNESS = 0.87;
/** Share of the largest in-gamut chroma the token uses (stays clear of clipping at the edge). */
export const SAFELIGHT_TOKEN_CHROMA_SHARE = 0.96;

/**
 * The design token: the safelight's hue at the token lightness, with chroma mapped into sRGB.
 * `--safelight-lamp` in globals.css must equal this value (a unit test checks it).
 */
export function safelightTokenHex(): string {
  const h = safelightHue();
  const c = maxChroma(SAFELIGHT_TOKEN_LIGHTNESS, h) * SAFELIGHT_TOKEN_CHROMA_SHARE;
  return oklchToHex(SAFELIGHT_TOKEN_LIGHTNESS, c, h);
}
