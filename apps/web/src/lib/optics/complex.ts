/** Minimal complex arithmetic for the Fresnel and Airy formulas. */
export interface Complex {
  readonly re: number;
  readonly im: number;
}

export const complex = (re: number, im = 0): Complex => ({ re, im });

export const add = (a: Complex, b: Complex): Complex => complex(a.re + b.re, a.im + b.im);
export const sub = (a: Complex, b: Complex): Complex => complex(a.re - b.re, a.im - b.im);
export const mul = (a: Complex, b: Complex): Complex =>
  complex(a.re * b.re - a.im * b.im, a.re * b.im + a.im * b.re);

export function div(a: Complex, b: Complex): Complex {
  const d = b.re * b.re + b.im * b.im;
  return complex((a.re * b.re + a.im * b.im) / d, (a.im * b.re - a.re * b.im) / d);
}

export const scale = (a: Complex, k: number): Complex => complex(a.re * k, a.im * k);
export const abs2 = (a: Complex): number => a.re * a.re + a.im * a.im;

/** Principal square root, with the branch cut on the negative real axis. */
export function sqrt(a: Complex): Complex {
  const r = Math.hypot(a.re, a.im);
  const re = Math.sqrt((r + a.re) / 2);
  const im = Math.sqrt(Math.max(0, (r - a.re) / 2));
  return complex(re, a.im < 0 ? -im : im);
}

/** e^(i·z) for complex z. */
export function expi(z: Complex): Complex {
  const m = Math.exp(-z.im);
  return complex(m * Math.cos(z.re), m * Math.sin(z.re));
}
