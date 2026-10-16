"use client";

import { useEffect, useRef } from "react";

import {
  hexToLinearSrgb,
  linearSrgbToHex,
  linearSrgbToOklab,
  oklabToLinearSrgb,
  type Vec3,
} from "@/lib/optics/oklab";
import { cn } from "@/lib/utils";

/**
 * A wafer map drawn flat on a canvas (WM-811K maps reach 200 × 200 dies, too many for SVG).
 * Two kinds: results (pass or fail per die) and frequencies (share of wafers whose die failed,
 * on a single-hue ramp). Colours are read from the theme tokens, so both themes are right.
 */

export type DieMapData =
  | { kind: "results"; height: number; width: number; cells: Uint8Array }
  | { kind: "frequency"; height: number; width: number; values: (number | null)[] };

function token(el: Element, name: string, fallback: string): string {
  const v = getComputedStyle(el).getPropertyValue(name).trim();
  return /^#[0-9a-f]{6}$/i.test(v) ? v : fallback;
}

/** OKLab mix from `a` (t = 0) to `b` (t = 1). */
export function mixOklab(a: string, b: string, t: number): string {
  const la = linearSrgbToOklab(hexToLinearSrgb(a));
  const lb = linearSrgbToOklab(hexToLinearSrgb(b));
  const m = la.map((v, i) => v + (lb[i]! - v) * t) as Vec3;
  return linearSrgbToHex(oklabToLinearSrgb(m).map((c) => Math.min(1, Math.max(0, c))) as Vec3);
}

/** Ramp stops for frequency maps: 0 is the panel colour stepped once, 1 is the fail colour. */
export function frequencyRamp(surface: string, fail: string, steps = 9): string[] {
  return Array.from({ length: steps }, (_, i) =>
    mixOklab(mixOklab(surface, fail, 0.08), fail, i / (steps - 1)),
  );
}

/**
 * Edges of `count` dies laid across `span` device pixels from `offset`, rounded to whole device
 * pixels so every die stays crisp: die i runs from edges[i] to edges[i + 1]. Each axis is fitted
 * on its own (x step = diameter / width, y step = diameter / height), because real dies are
 * rectangular: a grid that is not square still fills the round wafer edge to edge.
 */
export function dieEdges(count: number, span: number, offset = 0): number[] {
  return Array.from({ length: count + 1 }, (_, i) => Math.round(offset + (i * span) / count));
}

/** Whole device pixels left between dies, from the smaller of the two die steps. */
export function dieGap(step: number, dpr: number): number {
  return step >= 6 * dpr ? Math.max(1, Math.round(dpr)) : step >= 3 * dpr ? 1 : 0;
}

export function DieMap({
  data,
  label,
  className,
  max = 1,
  highlight,
}: {
  /** Null while the map is still being read: the canvas keeps its place, drawn once it is. */
  data: DieMapData | null;
  /** Accessible description; the canvas is an image. */
  label: string;
  className?: string;
  /** Frequency that reaches the end of the ramp. */
  max?: number;
  /** Row-major index of a die to outline. */
  highlight?: number | null;
}) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const draw = () => {
      const size = canvas.clientWidth;
      if (!size) return;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const side = Math.round(size * dpr);
      canvas.width = side;
      canvas.height = side;
      // Backed by memory, not the GPU: a map is up to 40,000 small squares, which a GPU-backed
      // canvas rasterises one by one (for seconds per map where the GPU is emulated).
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      if (!ctx) return;
      // Drawn in device pixels, on die edges rounded to whole pixels.
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, side, side);
      if (!data) return;
      const surface = token(canvas, "--surface-2", "#ffffff");
      const pass = token(canvas, "--hairline-strong", "#b9bdc2");
      const fail = token(canvas, "--fail", "#c62b44");
      const xs = dieEdges(data.width, side);
      const ys = dieEdges(data.height, side);
      const gap = dieGap(Math.min(side / data.width, side / data.height), dpr);
      const ramp = data.kind === "frequency" ? frequencyRamp(surface, fail) : [];
      for (let r = 0; r < data.height; r += 1) {
        const y = ys[r]!;
        const h = Math.max(1, ys[r + 1]! - gap - y);
        for (let c = 0; c < data.width; c += 1) {
          const i = r * data.width + c;
          let colour: string | null = null;
          if (data.kind === "results") {
            const cell = data.cells[i];
            colour = cell === 2 ? fail : cell === 1 ? pass : null;
          } else {
            const v = data.values[i];
            if (v != null)
              colour =
                ramp[
                  Math.min(
                    ramp.length - 1,
                    Math.round((Math.min(v, max) / max) * (ramp.length - 1)),
                  )
                ]!;
          }
          if (!colour) continue;
          ctx.fillStyle = colour;
          const x = xs[c]!;
          ctx.fillRect(x, y, Math.max(1, xs[c + 1]! - gap - x), h);
        }
      }
      if (highlight != null && highlight >= 0) {
        const r = Math.floor(highlight / data.width);
        const c = highlight % data.width;
        const line = Math.max(1, Math.round(dpr));
        ctx.strokeStyle = token(canvas, "--signal", "#a27900");
        ctx.lineWidth = 2 * line;
        ctx.strokeRect(
          xs[c]! - line,
          ys[r]! - line,
          xs[c + 1]! - xs[c]! + 2 * line,
          ys[r + 1]! - ys[r]! + 2 * line,
        );
      }
    };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    // Redraw when the theme changes (tokens are read at draw time).
    const themeObserver = new MutationObserver(draw);
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme", "class"],
    });
    return () => {
      observer.disconnect();
      themeObserver.disconnect();
    };
  }, [data, max, highlight]);

  return (
    <canvas
      ref={ref}
      role="img"
      aria-label={label}
      className={cn("block aspect-square w-full", className)}
    />
  );
}

/** Legend for a frequency map: the ramp with its end values. */
export function FrequencyLegend({ max = 1, className }: { max?: number; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ramp = frequencyRamp(token(el, "--surface-2", "#ffffff"), token(el, "--fail", "#c62b44"));
    el.style.background = `linear-gradient(to right, ${ramp.join(", ")})`;
  });
  return (
    <div className={cn("text-[12px] leading-4 text-ink-3", className)}>
      <div
        ref={ref}
        aria-hidden="true"
        className="h-2.5 w-full rounded-[6px] border border-hairline"
      />
      <div className="tnum mt-1 flex justify-between">
        <span>0%</span>
        <span>{Math.round(max * 100)}% of wafers failed at this die</span>
      </div>
    </div>
  );
}
