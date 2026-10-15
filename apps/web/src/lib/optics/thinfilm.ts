import { CIE_START_NM, CIE_STEP_NM, CMF_1931_2DEG, ILLUMINANT_D65 } from "./cie";
import { type Complex, abs2, add, complex, div, expi, mul, scale, sqrt, sub } from "./complex";
import { siliconIndex, silicaIndex } from "./materials";

/**
 * Reflectance of a single transparent film on an absorbing substrate (SiO2 on Si), from the
 * Airy summation of multiple reflections:
 *
 *   r = (r01 + r12·e^{2iβ}) / (1 + r01·r12·e^{2iβ}),   β = 2π·d·n1·cosθ1 / λ
 *
 * with Fresnel amplitude coefficients r01 (air to film) and r12 (film to substrate) for s and p
 * polarisation, and R = |r|². Unpolarised light averages Rs and Rp. Convention: complex index
 * N = n + ik (e^{-iωt} time dependence), so the substrate's normal wave-vector component takes
 * the root with a positive imaginary part. Reference: M. Born and E. Wolf, Principles of Optics,
 * 7th ed., §1.6.4; O. S. Heavens, Optical Properties of Thin Solid Films (1955).
 */

export type Polarisation = "s" | "p" | "unpolarised";

/** n·cosθ inside a medium of complex index N, for incidence from air at sinθ0 (Snell's law). */
function normalComponent(n: Complex, sin0: number): Complex {
  const q = sqrt(sub(mul(n, n), complex(sin0 * sin0)));
  // Choose the decaying (or forward-propagating) branch.
  return q.im < 0 || (q.im === 0 && q.re < 0) ? scale(q, -1) : q;
}

function fresnelS(qi: Complex, qj: Complex): Complex {
  return div(sub(qi, qj), add(qi, qj));
}

function fresnelP(ni: Complex, qi: Complex, nj: Complex, qj: Complex): Complex {
  const a = mul(mul(nj, nj), qi);
  const b = mul(mul(ni, ni), qj);
  return div(sub(a, b), add(a, b));
}

/**
 * Reflectance of SiO2 (thickness `thicknessNm`) on silicon at `lambdaNm`, for light arriving
 * from air at `angleDeg` from the surface normal.
 */
export function filmReflectance(
  lambdaNm: number,
  thicknessNm: number,
  angleDeg: number,
  polarisation: Polarisation = "unpolarised",
): number {
  const sin0 = Math.sin((angleDeg * Math.PI) / 180);
  const n0 = complex(1);
  const n1 = complex(silicaIndex(lambdaNm));
  const n2 = siliconIndex(lambdaNm);
  const q0 = complex(Math.cos((angleDeg * Math.PI) / 180));
  const q1 = normalComponent(n1, sin0);
  const q2 = normalComponent(n2, sin0);
  const phase = expi(scale(q1, (4 * Math.PI * thicknessNm) / lambdaNm)); // e^{2iβ}

  const airy = (r01: Complex, r12: Complex): number => {
    const num = add(r01, mul(r12, phase));
    const den = add(complex(1), mul(mul(r01, r12), phase));
    return abs2(div(num, den));
  };

  const rs = () => airy(fresnelS(q0, q1), fresnelS(q1, q2));
  const rp = () => airy(fresnelP(n0, q0, n1, q1), fresnelP(n1, q1, n2, q2));
  if (polarisation === "s") return rs();
  if (polarisation === "p") return rp();
  return (rs() + rp()) / 2;
}

/** IEC 61966-2-1 (sRGB): CIE XYZ (D65 white, Y = 1) to linear sRGB. */
export function xyzToLinearSrgb([x, y, z]: readonly [number, number, number]): [
  number,
  number,
  number,
] {
  return [
    3.2406 * x - 1.5372 * y - 0.4986 * z,
    -0.9689 * x + 1.8758 * y + 0.0415 * z,
    0.0557 * x - 0.204 * y + 1.057 * z,
  ];
}

/** sRGB transfer function (IEC 61966-2-1) for one channel in [0, 1]. */
export function encodeSrgb(linear: number): number {
  const v = Math.min(1, Math.max(0, linear));
  return v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055;
}

/**
 * CIE XYZ of a reflectance spectrum under an illuminant, normalised so that a perfect reflector
 * has Y = 1. Integrated on the CIE 5 nm grid from 380 to 780 nm.
 */
export function reflectedXyz(
  reflectance: (lambdaNm: number) => number,
  illuminant: readonly number[] = ILLUMINANT_D65,
): [number, number, number] {
  let x = 0;
  let y = 0;
  let z = 0;
  let norm = 0;
  for (let i = 0; i < CMF_1931_2DEG.length; i += 1) {
    const lambda = CIE_START_NM + i * CIE_STEP_NM;
    const [xb, yb, zb] = CMF_1931_2DEG[i]!;
    const s = illuminant[i]!;
    const r = reflectance(lambda);
    x += r * s * xb;
    y += r * s * yb;
    z += r * s * zb;
    norm += s * yb;
  }
  return [x / norm, y / norm, z / norm];
}

/** Linear sRGB of the oxide film seen under D65 at a given thickness and viewing angle. */
export function filmColorLinear(thicknessNm: number, angleDeg: number): [number, number, number] {
  return xyzToLinearSrgb(reflectedXyz((l) => filmReflectance(l, thicknessNm, angleDeg)));
}

/** Gamma-encoded sRGB hex of the film colour (channels clipped to [0, 1]). */
export function filmColorHex(thicknessNm: number, angleDeg: number): string {
  const rgb = filmColorLinear(thicknessNm, angleDeg).map(encodeSrgb);
  return `#${rgb
    .map((c) =>
      Math.round(c * 255)
        .toString(16)
        .padStart(2, "0"),
    )
    .join("")}`;
}
