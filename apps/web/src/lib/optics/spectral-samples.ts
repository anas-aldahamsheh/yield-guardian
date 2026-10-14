import { CIE_START_NM, CIE_STEP_NM, CMF_1931_2DEG, ILLUMINANT_D65 } from "./cie";
import { siliconIndex, silicaIndex } from "./materials";
import { SAFELIGHT_SPECTRUM } from "./safelight";
import { filmReflectance, xyzToLinearSrgb } from "./thinfilm";

/**
 * The shader evaluates the Airy reflectance at a few wavelengths and sums them with weights that
 * already contain the CIE observer, the illuminant and the XYZ to linear-sRGB matrix. Each sample
 * stands for a band of the 5 nm CIE grid (box quadrature; the end samples also take the tails to
 * 380 and 780 nm), so a perfect reflector still integrates to the illuminant's exact colour.
 */
export interface SpectralSamples {
  /** Sample wavelengths, nm. */
  readonly lambda: readonly number[];
  /** Refractive index of SiO2 at each sample. */
  readonly film: readonly number[];
  /** Complex index (n, k) of silicon at each sample. */
  readonly substrate: readonly (readonly [number, number])[];
  /** Linear-sRGB weight per unit reflectance under D65 (white inspection light). */
  readonly white: readonly (readonly [number, number, number])[];
  /** Linear-sRGB weight per unit reflectance under the safelight (yellow-room lamp). */
  readonly safelight: readonly (readonly [number, number, number])[];
}

export const DEFAULT_SAMPLE_WAVELENGTHS: readonly number[] = Array.from(
  { length: 16 },
  (_, i) => 400 + 20 * i,
);

function bandWeights(
  sampleLambdas: readonly number[],
  illuminant: readonly number[],
): [number, number, number][] {
  const xyz = sampleLambdas.map(() => [0, 0, 0] as [number, number, number]);
  let norm = 0;
  CMF_1931_2DEG.forEach(([xb, yb, zb], i) => {
    const lambda = CIE_START_NM + i * CIE_STEP_NM;
    const s = illuminant[i]!;
    norm += s * yb;
    // Nearest sample owns this grid point (ties go to the shorter wavelength).
    let best = 0;
    for (let j = 1; j < sampleLambdas.length; j += 1) {
      if (Math.abs(sampleLambdas[j]! - lambda) < Math.abs(sampleLambdas[best]! - lambda)) best = j;
    }
    const acc = xyz[best]!;
    acc[0] += s * xb;
    acc[1] += s * yb;
    acc[2] += s * zb;
  });
  return xyz.map(([x, y, z]) => xyzToLinearSrgb([x / norm, y / norm, z / norm]));
}

export function spectralSamples(
  sampleLambdas: readonly number[] = DEFAULT_SAMPLE_WAVELENGTHS,
): SpectralSamples {
  return {
    lambda: sampleLambdas,
    film: sampleLambdas.map(silicaIndex),
    substrate: sampleLambdas.map((l) => {
      const n = siliconIndex(l);
      return [n.re, n.im] as const;
    }),
    white: bandWeights(sampleLambdas, ILLUMINANT_D65),
    safelight: bandWeights(sampleLambdas, SAFELIGHT_SPECTRUM),
  };
}

/** The colour the shader computes (same samples, same weights), for tests and 2D fallbacks. */
export function sampledFilmColor(
  samples: SpectralSamples,
  thicknessNm: number,
  angleDeg: number,
  light: "white" | "safelight" = "white",
): [number, number, number] {
  const weights = samples[light];
  const rgb: [number, number, number] = [0, 0, 0];
  samples.lambda.forEach((lambda, i) => {
    const r = filmReflectance(lambda, thicknessNm, angleDeg);
    const w = weights[i]!;
    rgb[0] += r * w[0];
    rgb[1] += r * w[1];
    rgb[2] += r * w[2];
  });
  return rgb;
}
