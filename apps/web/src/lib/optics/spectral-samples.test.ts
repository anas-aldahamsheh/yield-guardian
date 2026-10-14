import { thinFilmGlsl } from "./glsl";
import { linearSrgbToOklab } from "./oklab";
import { safelightXyz } from "./safelight";
import { DEFAULT_SAMPLE_WAVELENGTHS, sampledFilmColor, spectralSamples } from "./spectral-samples";
import { filmColorLinear, xyzToLinearSrgb } from "./thinfilm";

const sum3 = (rows: readonly (readonly [number, number, number])[]) =>
  rows.reduce<[number, number, number]>(
    (acc, [r, g, b]) => [acc[0] + r, acc[1] + g, acc[2] + b],
    [0, 0, 0],
  );

describe("spectralSamples", () => {
  const samples = spectralSamples();

  it("samples 16 wavelengths from 400 to 700 nm", () => {
    expect(DEFAULT_SAMPLE_WAVELENGTHS).toHaveLength(16);
    expect(DEFAULT_SAMPLE_WAVELENGTHS[0]).toBe(400);
    expect(DEFAULT_SAMPLE_WAVELENGTHS.at(-1)).toBe(700);
  });

  it("integrates a perfect reflector to the D65 white point", () => {
    for (const channel of sum3(samples.white)) expect(channel).toBeCloseTo(1, 3);
  });

  it("integrates a perfect reflector under the safelight to the lamp's own colour", () => {
    const expected = xyzToLinearSrgb(safelightXyz());
    sum3(samples.safelight).forEach((channel, i) => expect(channel).toBeCloseTo(expected[i]!, 10));
  });

  it("carries no blue under the safelight (the filter cuts below 500 nm)", () => {
    samples.lambda.forEach((lambda, i) => {
      if (lambda < 490) expect(samples.safelight[i]).toEqual([0, 0, 0]);
    });
  });

  it("stays within a just-noticeable difference of the full 5 nm integration", () => {
    let worst = 0;
    let total = 0;
    let count = 0;
    for (let d = 0; d <= 800; d += 10) {
      for (const angle of [0, 20, 40, 60, 75]) {
        const full = linearSrgbToOklab(filmColorLinear(d, angle));
        const fast = linearSrgbToOklab(sampledFilmColor(samples, d, angle));
        const de = 100 * Math.hypot(full[0] - fast[0], full[1] - fast[1], full[2] - fast[2]);
        worst = Math.max(worst, de);
        total += de;
        count += 1;
      }
    }
    // OKLab ×100: about 2 is a just-noticeable difference.
    expect(worst).toBeLessThan(1.5);
    expect(total / count).toBeLessThan(0.6);
  });
});

describe("thinFilmGlsl", () => {
  const source = thinFilmGlsl();

  it("declares the entry point the wafer shader calls", () => {
    expect(source).toContain(
      "void thinFilm(float thicknessNm, float cosIncidence, out vec3 whiteLight, out vec3 safelight)",
    );
    expect(source).toContain("const int TF_N = 16;");
  });

  it("writes every constant table with 16 finite float literals", () => {
    for (const name of ["TF_LAMBDA", "TF_FILM_N"]) {
      const match = source.match(new RegExp(`${name}\\[16\\] = float\\[16\\]\\(([^)]*)\\)`));
      expect(match).not.toBeNull();
      const values = match![1]!.split(",").map((v) => v.trim());
      expect(values).toHaveLength(16);
      for (const v of values) {
        expect(v).toMatch(/^-?\d+\.\d*(e[+-]?\d+)?$|^-?\d+(\.\d+)?e[+-]?\d+$/);
        expect(Number.isFinite(Number(v))).toBe(true);
      }
    }
    expect(source).not.toMatch(/NaN|Infinity|undefined/);
  });

  it("embeds the same refractive indices as the TypeScript model", () => {
    const samples = spectralSamples();
    const first = samples.substrate[0]!;
    expect(source).toContain(`vec2(${first[0].toPrecision(9)}`);
  });
});
