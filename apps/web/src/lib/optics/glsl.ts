import { type SpectralSamples, spectralSamples } from "./spectral-samples";

const f = (v: number) => {
  const s = v.toPrecision(9);
  return s.includes(".") || s.includes("e") ? s : `${s}.0`;
};

/**
 * GLSL ES 3.0 chunk with the same thin-film physics as `filmReflectance` (Airy summation, s and p
 * averaged, SiO2 on Si). It defines:
 *
 *   void thinFilm(float thicknessNm, float cosIncidence, out vec3 whiteLight, out vec3 safelight)
 *
 * which returns the linear-sRGB colour of the film under D65 and under the yellow-room lamp.
 * Constants are generated from the TypeScript tables, so the shader and the unit-tested code
 * cannot drift apart.
 */
export function thinFilmGlsl(samples: SpectralSamples = spectralSamples()): string {
  const n = samples.lambda.length;
  const arr = (type: string, values: string[]) => `${type}[${n}](${values.join(", ")})`;
  const v3 = (w: readonly number[]) => `vec3(${w.map(f).join(", ")})`;
  return /* glsl */ `
const int TF_N = ${n};
const float TF_LAMBDA[${n}] = ${arr("float", samples.lambda.map(f))};
const float TF_FILM_N[${n}] = ${arr("float", samples.film.map(f))};
const vec2 TF_SUB_N[${n}] = ${arr(
    "vec2",
    samples.substrate.map(([re, im]) => `vec2(${f(re)}, ${f(im)})`),
  )};
const vec3 TF_W_WHITE[${n}] = ${arr("vec3", samples.white.map(v3))};
const vec3 TF_W_SAFE[${n}] = ${arr("vec3", samples.safelight.map(v3))};

vec2 tfMul(vec2 a, vec2 b) { return vec2(a.x * b.x - a.y * b.y, a.x * b.y + a.y * b.x); }
vec2 tfDiv(vec2 a, vec2 b) {
  float d = dot(b, b);
  return vec2(a.x * b.x + a.y * b.y, a.y * b.x - a.x * b.y) / d;
}
vec2 tfSqrt(vec2 a) {
  float r = length(a);
  float re = sqrt(max(0.0, 0.5 * (r + a.x)));
  float im = sqrt(max(0.0, 0.5 * (r - a.x)));
  return vec2(re, a.y < 0.0 ? -im : im);
}
float tfAiry(vec2 r01, vec2 r12, vec2 phase) {
  vec2 num = r01 + tfMul(r12, phase);
  vec2 den = vec2(1.0, 0.0) + tfMul(tfMul(r01, r12), phase);
  vec2 r = tfDiv(num, den);
  return dot(r, r);
}
float tfReflectance(float lambda, float n1, vec2 n2, float d, float cos0) {
  float sin2 = max(0.0, 1.0 - cos0 * cos0);
  float q1 = sqrt(n1 * n1 - sin2);
  vec2 n2sq = tfMul(n2, n2);
  vec2 q2 = tfSqrt(n2sq - vec2(sin2, 0.0));
  if (q2.y < 0.0) q2 = -q2;
  float beta2 = 12.566370614359172 * d * q1 / lambda;
  vec2 phase = vec2(cos(beta2), sin(beta2));
  vec2 rs01 = vec2((cos0 - q1) / (cos0 + q1), 0.0);
  vec2 rs12 = tfDiv(vec2(q1, 0.0) - q2, vec2(q1, 0.0) + q2);
  float a01 = n1 * n1 * cos0;
  vec2 rp01 = vec2((a01 - q1) / (a01 + q1), 0.0);
  vec2 a12 = n2sq * q1;
  vec2 b12 = (n1 * n1) * q2;
  vec2 rp12 = tfDiv(a12 - b12, a12 + b12);
  return 0.5 * (tfAiry(rs01, rs12, phase) + tfAiry(rp01, rp12, phase));
}
void thinFilm(float thicknessNm, float cosIncidence, out vec3 whiteLight, out vec3 safelight) {
  whiteLight = vec3(0.0);
  safelight = vec3(0.0);
  float c0 = clamp(cosIncidence, 0.0, 1.0);
  for (int i = 0; i < TF_N; i++) {
    float r = tfReflectance(TF_LAMBDA[i], TF_FILM_N[i], TF_SUB_N[i], thicknessNm, c0);
    whiteLight += r * TF_W_WHITE[i];
    safelight += r * TF_W_SAFE[i];
  }
}
`;
}
