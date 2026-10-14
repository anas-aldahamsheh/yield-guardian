import { abs2, add, complex, div, sub } from "./complex";
import { siliconIndex, silicaIndex } from "./materials";
import { linearSrgbToOklab, oklabToOklch, type Vec3 } from "./oklab";
import { filmColorLinear, filmReflectance, reflectedXyz, xyzToLinearSrgb } from "./thinfilm";

/*
 * Reference values from an independent implementation: S. J. Byrnes' transfer-matrix package
 * `tmm` (Python) for reflectance, and `colour-science` 0.4.7 with 1 nm CIE 1931 2° and D65 tables
 * for the colours. Same optical constants (Green 2008 silicon, Malitson 1965 silica).
 */

// lambda_nm, d_nm, theta_deg, R (unpolarised), Rs, Rp
const TMM_POINTS: readonly (readonly [number, number, number, number, number, number])[] = [
  [450, 0, 0, 0.4207735421, 0.4207735421, 0.4207735421],
  [450, 0, 30, 0.4200562347, 0.4718349726, 0.3682774969],
  [450, 0, 60, 0.4073955676, 0.6470355446, 0.1677555907],
  [450, 100, 0, 0.2200698036, 0.2200698036, 0.2200698036],
  [450, 100, 30, 0.1883495043, 0.194452987, 0.1822460217],
  [450, 100, 60, 0.1536760364, 0.0713211376, 0.2360309351],
  [450, 250, 0, 0.2002821531, 0.2002821531, 0.2002821531],
  [450, 250, 30, 0.1429920119, 0.136064709, 0.1499193147],
  [450, 250, 60, 0.2952334843, 0.3732205693, 0.2172463994],
  [450, 500, 0, 0.2996432187, 0.2996432187, 0.2996432187],
  [450, 500, 30, 0.4126886467, 0.4636123134, 0.36176498],
  [450, 500, 60, 0.2398567152, 0.2532613689, 0.2264520615],
  [550, 0, 0, 0.3673358922, 0.3673358922, 0.3673358922],
  [550, 0, 30, 0.3670430908, 0.4191482139, 0.3149379677],
  [550, 0, 60, 0.3637966208, 0.603718766, 0.1238744756],
  [550, 100, 0, 0.102024617, 0.102024617, 0.102024617],
  [550, 100, 30, 0.098344847, 0.0908143361, 0.1058753579],
  [550, 100, 60, 0.1419202975, 0.0979300583, 0.1859105368],
  [550, 250, 0, 0.1893959019, 0.1893959019, 0.1893959019],
  [550, 250, 30, 0.2594735854, 0.293332928, 0.2256142428],
  [550, 250, 60, 0.3598476768, 0.5925312029, 0.1271641507],
  [550, 500, 0, 0.175295827, 0.175295827, 0.175295827],
  [550, 500, 30, 0.098451899, 0.0909559147, 0.1059478833],
  [550, 500, 60, 0.3469912762, 0.5578796374, 0.136102915],
  [633, 0, 0, 0.3476656665, 0.3476656665, 0.3476656665],
  [633, 0, 30, 0.3475434463, 0.3994866087, 0.2956002838],
  [633, 0, 60, 0.3480698188, 0.5869338777, 0.1092057598],
  [633, 100, 0, 0.0907267516, 0.0907267516, 0.0907267516],
  [633, 100, 30, 0.1015407374, 0.0992457335, 0.1038357413],
  [633, 100, 60, 0.1795664129, 0.1958017265, 0.1633310992],
  [633, 250, 0, 0.3058839051, 0.3058839051, 0.3058839051],
  [633, 250, 30, 0.3355304192, 0.3857417836, 0.2853190548],
  [633, 250, 60, 0.3433435146, 0.5738964408, 0.1127905884],
  [633, 500, 0, 0.194886015, 0.194886015, 0.194886015],
  [633, 500, 30, 0.3003795789, 0.344955875, 0.2558032828],
  [633, 500, 60, 0.3275888424, 0.5324182719, 0.1227594128],
  [700, 0, 0, 0.3374346933, 0.3374346933, 0.3374346933],
  [700, 0, 30, 0.3374037538, 0.3891980609, 0.2856094466],
  [700, 0, 60, 0.3399502375, 0.5780027182, 0.1018977569],
  [700, 100, 0, 0.1025909612, 0.1025909612, 0.1025909612],
  [700, 100, 30, 0.1187030345, 0.1234406307, 0.1139654382],
  [700, 100, 60, 0.2057659673, 0.2617285436, 0.1498033911],
  [700, 250, 0, 0.3345155944, 0.3345155944, 0.3345155944],
  [700, 250, 30, 0.33641999, 0.3880698117, 0.2847701684],
  [700, 250, 60, 0.3140424863, 0.5101583109, 0.1179266616],
  [700, 500, 0, 0.3259059799, 0.3259059799, 0.3259059799],
  [700, 500, 30, 0.3334031652, 0.3846097567, 0.2821965738],
  [700, 500, 60, 0.2108475343, 0.2728755344, 0.1488195342],
];

// d_nm, theta_deg, X, Y, Z of the film under D65 (perfect reflector Y = 1)
const COLOUR_POINTS: readonly (readonly [number, number, number, number, number])[] = [
  [0, 0, 0.350796, 0.367452, 0.455864],
  [50, 0, 0.234457, 0.243951, 0.259403],
  [100, 0, 0.113132, 0.10754, 0.233852],
  [150, 0, 0.257834, 0.284593, 0.448859],
  [200, 0, 0.315971, 0.349782, 0.289982],
  [250, 0, 0.23613, 0.20366, 0.218785],
  [300, 0, 0.162092, 0.154578, 0.428403],
  [350, 0, 0.220278, 0.295504, 0.313967],
  [400, 0, 0.294813, 0.309233, 0.223761],
  [450, 0, 0.269518, 0.198797, 0.399416],
  [500, 0, 0.164742, 0.199875, 0.329019],
  [550, 0, 0.204244, 0.283995, 0.241447],
  [600, 0, 0.302009, 0.274366, 0.370612],
  [650, 0, 0.253141, 0.213927, 0.335205],
  [700, 0, 0.180082, 0.227569, 0.26282],
  [100, 40, 0.114031, 0.107003, 0.184079],
  [100, 75, 0.300873, 0.307649, 0.25079],
  [150, 60, 0.186744, 0.203422, 0.389609],
  [300, 20, 0.16683, 0.141869, 0.411088],
  [300, 60, 0.27901, 0.269834, 0.217867],
  [320, 0, 0.172008, 0.208467, 0.42469],
  [320, 40, 0.173681, 0.141093, 0.399182],
  [320, 75, 0.376912, 0.398845, 0.333972],
  [470, 20, 0.254994, 0.18854, 0.408738],
  [470, 60, 0.286349, 0.33977, 0.238284],
  [500, 40, 0.274111, 0.204102, 0.398178],
  [500, 75, 0.37014, 0.404061, 0.369397],
];

/** Analytic reflectance of bare silicon at normal incidence: ((n-1)² + k²) / ((n+1)² + k²). */
function bareSilicon(lambdaNm: number): number {
  const { re: n, im: k } = siliconIndex(lambdaNm);
  return ((n - 1) ** 2 + k ** 2) / ((n + 1) ** 2 + k ** 2);
}

function oklchOf(xyzOrRgb: Vec3, isXyz = false): Vec3 {
  const rgb = (isXyz ? xyzToLinearSrgb(xyzOrRgb) : xyzOrRgb).map((c) => Math.max(0, c)) as Vec3;
  return oklabToOklch(linearSrgbToOklab(rgb));
}

function deltaE(a: Vec3, b: Vec3): number {
  const la = linearSrgbToOklab(xyzToLinearSrgb(a).map((c) => Math.max(0, c)) as Vec3);
  const lb = linearSrgbToOklab(xyzToLinearSrgb(b).map((c) => Math.max(0, c)) as Vec3);
  return 100 * Math.hypot(la[0] - lb[0], la[1] - lb[1], la[2] - lb[2]);
}

function hueWithin(h: number, from: number, to: number): boolean {
  return from <= to ? h >= from && h <= to : h >= from || h <= to;
}

describe("filmReflectance", () => {
  it.each(TMM_POINTS)(
    "matches the transfer-matrix reference at %d nm, %d nm oxide, %d°",
    (lambda, d, theta, r, rs, rp) => {
      expect(filmReflectance(lambda, d, theta)).toBeCloseTo(r, 9);
      expect(filmReflectance(lambda, d, theta, "s")).toBeCloseTo(rs, 9);
      expect(filmReflectance(lambda, d, theta, "p")).toBeCloseTo(rp, 9);
    },
  );

  it("gives the textbook reflectance of bare silicon (about 35 % at 633 nm)", () => {
    for (const lambda of [400, 450, 500, 550, 600, 650, 700, 780]) {
      expect(filmReflectance(lambda, 0, 0)).toBeCloseTo(bareSilicon(lambda), 12);
    }
    expect(filmReflectance(633, 0, 0)).toBeCloseTo(0.3477, 4);
  });

  it("returns the bare substrate for a half-wave film at normal incidence", () => {
    for (const lambda of [450, 550, 650]) {
      const halfWave = lambda / (2 * silicaIndex(lambda));
      expect(filmReflectance(lambda, halfWave, 0)).toBeCloseTo(bareSilicon(lambda), 12);
      expect(filmReflectance(lambda, 3 * halfWave, 0)).toBeCloseTo(bareSilicon(lambda), 12);
    }
  });

  it("gives the quarter-wave value |(n0 Ns - nf²) / (n0 Ns + nf²)|²", () => {
    for (const lambda of [450, 550, 650]) {
      const nf = silicaIndex(lambda);
      const ns = siliconIndex(lambda);
      const nf2 = complex(nf * nf);
      const expected = abs2(div(sub(ns, nf2), add(ns, nf2)));
      expect(filmReflectance(lambda, lambda / (4 * nf), 0)).toBeCloseTo(expected, 12);
      // A quarter-wave of silica lowers the reflectance of silicon (an antireflection layer).
      expect(expected).toBeLessThan(bareSilicon(lambda));
    }
  });

  it("is periodic in thickness with period λ / 2n at normal incidence", () => {
    const lambda = 550;
    const period = lambda / (2 * silicaIndex(lambda));
    for (const d of [0, 37, 120, 333]) {
      expect(filmReflectance(lambda, d + period, 0)).toBeCloseTo(filmReflectance(lambda, d, 0), 12);
    }
  });

  it("treats s and p alike at normal incidence", () => {
    for (const d of [0, 90, 310]) {
      expect(filmReflectance(600, d, 0, "s")).toBeCloseTo(filmReflectance(600, d, 0, "p"), 14);
    }
  });

  it("nearly extinguishes p light at the pseudo-Brewster angle of silicon (about 75.5°)", () => {
    let best = { angle: 0, r: 1 };
    for (let angle = 70; angle <= 80; angle += 0.05) {
      const r = filmReflectance(633, 0, angle, "p");
      if (r < best.r) best = { angle, r };
    }
    const n = siliconIndex(633).re;
    expect(best.angle).toBeCloseTo((Math.atan(n) * 180) / Math.PI, 0);
    expect(best.r).toBeLessThan(1e-4);
  });

  it("stays between 0 and 1 (energy conservation)", () => {
    for (let lambda = 380; lambda <= 780; lambda += 40) {
      for (let d = 0; d <= 1000; d += 50) {
        for (const angle of [0, 30, 60, 85]) {
          const r = filmReflectance(lambda, d, angle);
          expect(r).toBeGreaterThanOrEqual(0);
          expect(r).toBeLessThanOrEqual(1);
        }
      }
    }
  });
});

describe("film colour", () => {
  it.each(COLOUR_POINTS)(
    "matches 1 nm CIE integration for %d nm oxide at %d°",
    (d, theta, x, y, z) => {
      const xyz = reflectedXyz((lambda) => filmReflectance(lambda, d, theta));
      expect(Math.max(...xyz.map((v, i) => Math.abs(v - [x, y, z][i]!)))).toBeLessThan(5e-4);
      expect(deltaE(xyz, [x, y, z])).toBeLessThan(0.1);
    },
  );

  it("renders a perfect reflector as the D65 white point", () => {
    const rgb = xyzToLinearSrgb(reflectedXyz(() => 1));
    for (const channel of rgb) expect(channel).toBeCloseTo(1, 3);
  });

  /*
   * Interference colours of thermal oxide on silicon, from the classic chart (W. A. Pliskin and
   * E. E. Conrad, IBM J. Res. Dev. 8, 43, 1964) and its computed version (J. Henrie et al.,
   * "Electronic color charts for dielectric films on silicon", Opt. Express 12, 1464, 2004).
   * Windows are OKLCH hue angles in degrees.
   */
  it.each([
    [120, "royal blue", 235, 280],
    [150, "light blue", 215, 260],
    [200, "light gold or yellow", 80, 130],
    [220, "gold", 70, 120],
    [270, "red-violet", 290, 340],
    [310, "blue", 230, 270],
    [350, "green to yellow-green", 140, 200],
    [390, "yellow", 90, 130],
    [420, "carnation pink", 330, 20],
    [470, "violet", 280, 320],
    [520, "green", 150, 200],
  ] as const)("shows %d nm of oxide as %s", (d, _name, from, to) => {
    const [, chroma, hue] = oklchOf(filmColorLinear(d, 0));
    expect(chroma).toBeGreaterThan(0.025);
    expect(hueWithin(hue, from, to)).toBe(true);
  });

  it("shows bare silicon as a near-neutral grey", () => {
    const [lightness, chroma] = oklchOf(filmColorLinear(0, 0));
    expect(chroma).toBeLessThan(0.03);
    expect(lightness).toBeGreaterThan(0.6);
  });

  it("shifts colour with viewing angle (thinner apparent film when tilted)", () => {
    const [, , hueNormal] = oklchOf(filmColorLinear(320, 0));
    const [, , hueTilted] = oklchOf(filmColorLinear(320, 40));
    expect(Math.abs(hueNormal - hueTilted)).toBeGreaterThan(15);
  });
});
