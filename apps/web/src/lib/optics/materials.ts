import { type Complex, complex } from "./complex";

/**
 * Optical constants of the wafer's materials.
 *
 * Silicon (substrate): M. A. Green, "Self-consistent optical parameters of intrinsic silicon at
 * 300 K including temperature coefficients", Solar Energy Materials and Solar Cells 92 (2008)
 * 1305-1310, doi:10.1016/j.solmat.2008.06.009. Tabulated n and k every 10 nm, copied from the
 * refractiveindex.info database (main/Si/nk/Green-2008.yml, CC0).
 *
 * Silicon dioxide (film): I. H. Malitson, "Interspecimen comparison of the refractive index of
 * fused silica", J. Opt. Soc. Am. 55 (1965) 1205-1209, doi:10.1364/JOSA.55.001205. Three-term
 * Sellmeier formula, valid 0.21 to 3.71 µm. Thermal oxide is within about 0.01 of fused silica
 * in the visible, and absorbs nothing there (k = 0).
 */

/** Green (2008): [wavelength nm, n, k] for crystalline silicon at 300 K, 380 to 780 nm. */
export const SILICON_GREEN_2008: readonly (readonly [number, number, number])[] = [
  [380, 6.616, 0.946],
  [390, 6.039, 0.445],
  [400, 5.613, 0.296],
  [410, 5.33, 0.227],
  [420, 5.119, 0.176],
  [430, 4.949, 0.138],
  [440, 4.812, 0.107],
  [450, 4.691, 0.086302],
  [460, 4.587, 0.071381],
  [470, 4.497, 0.062086],
  [480, 4.419, 0.055004],
  [490, 4.35, 0.049131],
  [500, 4.294, 0.044165],
  [510, 4.241, 0.039367],
  [520, 4.193, 0.036415],
  [530, 4.151, 0.033108],
  [540, 4.112, 0.030295],
  [550, 4.077, 0.027968],
  [560, 4.045, 0.025758],
  [570, 4.015, 0.024131],
  [580, 3.988, 0.022524],
  [590, 3.963, 0.021081],
  [600, 3.94, 0.019934],
  [610, 3.918, 0.018446],
  [620, 3.898, 0.017367],
  [630, 3.879, 0.016444],
  [640, 3.861, 0.015432],
  [650, 3.844, 0.014431],
  [660, 3.828, 0.013498],
  [670, 3.813, 0.012743],
  [680, 3.798, 0.011905],
  [690, 3.784, 0.011201],
  [700, 3.772, 0.010528],
  [710, 3.759, 0.010057],
  [720, 3.748, 0.0096257],
  [730, 3.737, 0.0089461],
  [740, 3.727, 0.008362],
  [750, 3.717, 0.0078185],
  [760, 3.708, 0.007197],
  [770, 3.699, 0.0067402],
  [780, 3.691, 0.0063933],
];

/** Complex refractive index n + ik of silicon, linearly interpolated in wavelength. */
export function siliconIndex(lambdaNm: number): Complex {
  const table = SILICON_GREEN_2008;
  const first = table[0]!;
  const last = table[table.length - 1]!;
  if (lambdaNm <= first[0]) return complex(first[1], first[2]);
  if (lambdaNm >= last[0]) return complex(last[1], last[2]);
  const i = Math.floor((lambdaNm - first[0]) / 10);
  const a = table[i]!;
  const b = table[i + 1]!;
  const t = (lambdaNm - a[0]) / (b[0] - a[0]);
  return complex(a[1] + t * (b[1] - a[1]), a[2] + t * (b[2] - a[2]));
}

/** Malitson (1965) Sellmeier coefficients: B_i and C_i (µm). */
const MALITSON: readonly (readonly [number, number])[] = [
  [0.6961663, 0.0684043],
  [0.4079426, 0.1162414],
  [0.8974794, 9.896161],
];

/** Refractive index of SiO2 (real; no absorption in the visible). */
export function silicaIndex(lambdaNm: number): number {
  const l2 = (lambdaNm / 1000) ** 2;
  let n2 = 1;
  for (const [b, c] of MALITSON) n2 += (b * l2) / (l2 - c * c);
  return Math.sqrt(n2);
}
