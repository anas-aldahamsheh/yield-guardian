/**
 * OKLab and OKLCH (B. Ottosson, "A perceptual color space for image processing", 2020) to and
 * from linear sRGB, plus hex helpers. Used to derive design tokens from computed spectra.
 */

export type Vec3 = [number, number, number];

export function linearSrgbToOklab([r, g, b]: Vec3): Vec3 {
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

export function oklabToLinearSrgb([L, a, b]: Vec3): Vec3 {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
}

export function oklchToOklab(L: number, C: number, hDeg: number): Vec3 {
  const h = (hDeg * Math.PI) / 180;
  return [L, C * Math.cos(h), C * Math.sin(h)];
}

export function oklabToOklch([L, a, b]: Vec3): Vec3 {
  const h = (Math.atan2(b, a) * 180) / Math.PI;
  return [L, Math.hypot(a, b), (h + 360) % 360];
}

export function inSrgbGamut([r, g, b]: Vec3, epsilon = 1e-6): boolean {
  return [r, g, b].every((c) => c >= -epsilon && c <= 1 + epsilon);
}

/** Largest OKLCH chroma at this lightness and hue that still fits in sRGB. */
export function maxChroma(L: number, hDeg: number): number {
  let lo = 0;
  let hi = 0.5;
  for (let i = 0; i < 40; i += 1) {
    const mid = (lo + hi) / 2;
    if (inSrgbGamut(oklabToLinearSrgb(oklchToOklab(L, mid, hDeg)))) lo = mid;
    else hi = mid;
  }
  return lo;
}

function encode(c: number): number {
  const v = Math.min(1, Math.max(0, c));
  return v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055;
}

function decode(c: number): number {
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

export function linearSrgbToHex(rgb: Vec3): string {
  return `#${rgb
    .map((c) =>
      Math.round(encode(c) * 255)
        .toString(16)
        .padStart(2, "0"),
    )
    .join("")}`;
}

export function hexToLinearSrgb(hex: string): Vec3 {
  const h = hex.replace(/^#/, "");
  return [0, 2, 4].map((i) => decode(parseInt(h.slice(i, i + 2), 16) / 255)) as Vec3;
}

export function oklchToHex(L: number, C: number, hDeg: number): string {
  return linearSrgbToHex(oklabToLinearSrgb(oklchToOklab(L, C, hDeg)));
}

/** Euclidean distance in OKLab, ×100 (the ΔE the dataviz validator uses). */
export function deltaEOk(hexA: string, hexB: string): number {
  const a = linearSrgbToOklab(hexToLinearSrgb(hexA));
  const b = linearSrgbToOklab(hexToLinearSrgb(hexB));
  return 100 * Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

/** WCAG 2.x contrast ratio between two hex colours. */
export function contrastRatio(hexA: string, hexB: string): number {
  const lum = (hex: string) => {
    const [r, g, b] = hexToLinearSrgb(hex);
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const [hi, lo] = [lum(hexA), lum(hexB)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}
