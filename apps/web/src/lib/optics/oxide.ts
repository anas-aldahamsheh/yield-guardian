import { linearSrgbToOklab, maxChroma, oklabToOklch, oklchToHex, type Vec3 } from "./oklab";
import { filmColorLinear } from "./thinfilm";

/**
 * The oxide film as design tokens (docs/DESIGN.md, "the one light"). A thermal oxide on silicon
 * shows interference colours that cycle as the film thickens; fabs read a film's thickness by eye
 * from that sequence. The interface's one chromatic signature is its second order, violet to
 * green, 280 to 362 nm. Each stop takes the hue the physics gives at its thickness (normal
 * incidence under D65, Airy summation in thinfilm.ts); lightness and chroma are fixed per theme,
 * so the stops are equally light and equally vivid and only the hue is measured.
 */

export type Theme = "light" | "dark";

/** Film thicknesses of the six stops, nm. */
export const FILM_THICKNESS_NM = [280, 296, 310, 324, 340, 362] as const;

/** Lightness of the stops: light enough to glow on dark glass, dark enough to read on white. */
export const FILM_LIGHTNESS: Record<Theme, number> = { light: 0.56, dark: 0.76 };

/** Share of the largest chroma sRGB holds at each stop's hue and lightness. */
export const FILM_CHROMA_SHARE = 0.86;

/** OKLCH hue of the oxide film at a thickness, degrees. */
export function filmHue(thicknessNm: number): number {
  const linear = filmColorLinear(thicknessNm, 0).map((c) => Math.max(0, c)) as Vec3;
  return oklabToOklch(linearSrgbToOklab(linear))[2];
}

/** A film stop as a token: `--film-1` to `--film-6` in globals.css equal these values. */
export function filmTokenHex(thicknessNm: number, theme: Theme): string {
  const L = FILM_LIGHTNESS[theme];
  const h = filmHue(thicknessNm);
  return oklchToHex(L, maxChroma(L, h) * FILM_CHROMA_SHARE, h);
}

/** The signal colour (focus, selection, live) is the film's hue at this thickness: its blue. */
export const SIGNAL_THICKNESS_NM = 310;

/** Lightness and chroma of the signal, per theme; chroma is capped to 98% of what sRGB holds. */
export const SIGNAL_TONE: Record<Theme, { L: number; C: number }> = {
  light: { L: 0.53, C: 0.18 },
  dark: { L: 0.79, C: 0.12 },
};

/** `--signal` in globals.css equals this value in each theme. */
export function signalTokenHex(theme: Theme): string {
  const { L, C } = SIGNAL_TONE[theme];
  const h = filmHue(SIGNAL_THICKNESS_NM);
  return oklchToHex(L, Math.min(C, maxChroma(L, h) * 0.98), h);
}
