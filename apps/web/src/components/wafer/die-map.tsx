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
      canvas.width = Math.round(size * dpr);
      canvas.height = Math.round(size * dpr);
      // Backed by memory, not the GPU: a map is up to 40,000 small squares, which a GPU-backed
      // canvas rasterises one by one (for seconds per map where the GPU is emulated).
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, size, size);
      if (!data) return;
      const surface = token(canvas, "--die-2", "#ffffff");
      const pass = token(canvas, "--hairline-strong", "#b9bdc2");
      const fail = token(canvas, "--fail", "#c62b44");
      const n = Math.max(data.height, data.width);
      const pitch = size / n;
      const gap = pitch >= 6 ? 1 : pitch >= 3 ? 0.5 : 0;
      const ox = (size - data.width * pitch) / 2;
      const oy = (size - data.height * pitch) / 2;
      const ramp = data.kind === "frequency" ? frequencyRamp(surface, fail) : [];
      for (let r = 0; r < data.height; r += 1) {
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
          ctx.fillRect(
            ox + c * pitch + gap / 2,
            oy + r * pitch + gap / 2,
            pitch - gap,
            pitch - gap,
          );
        }
      }
      if (highlight != null && highlight >= 0) {
        const r = Math.floor(highlight / data.width);
        const c = highlight % data.width;
        ctx.strokeStyle = token(canvas, "--safelight", "#a27900");
        ctx.lineWidth = 2;
        ctx.strokeRect(ox + c * pitch - 1, oy + r * pitch - 1, pitch + 2, pitch + 2);
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
    const ramp = frequencyRamp(token(el, "--die-2", "#ffffff"), token(el, "--fail", "#c62b44"));
    el.style.background = `linear-gradient(to right, ${ramp.join(", ")})`;
  });
  return (
    <div className={cn("text-[12px] leading-4 text-ink-3", className)}>
      <div
        ref={ref}
        aria-hidden="true"
        className="h-2.5 w-full rounded-[2px] border border-hairline"
      />
      <div className="tnum mt-1 flex justify-between">
        <span>0%</span>
        <span>{Math.round(max * 100)}% of wafers failed at this die</span>
      </div>
    </div>
  );
}
