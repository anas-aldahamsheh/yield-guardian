"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";

import { usePrefersReducedMotion } from "@/components/motion";
import { formatInt } from "@/lib/format";
import { type DieGrid, layoutDies, planExposure } from "@/lib/wafer/geometry";
import { cn } from "@/lib/utils";

import { WaferPoster } from "./wafer-poster";
import type { DieHover } from "./wafer-scene";

const WaferScene = dynamic(() => import("./wafer-scene"), { ssr: false, loading: () => null });

// Kept here for the screens that already import them from this module.
export { usePrefersReducedMotion };

let webgl: boolean | undefined;

/** Probes WebGL 2 once per page and releases the probe's context straight away. */
export function webglAvailable(): boolean {
  if (webgl !== undefined) return webgl;
  try {
    const gl = document.createElement("canvas").getContext("webgl2");
    webgl = Boolean(gl);
    gl?.getExtension("WEBGL_lose_context")?.loseContext();
  } catch {
    webgl = false;
  }
  return webgl;
}

const noop = () => () => {};

/**
 * Runs the scan on its own only with a fine pointer (a desktop) and without Save-Data. On a
 * phone the poster stays until someone asks for the scan: a WebGL sequence would compete with
 * the first load on a slow CPU and costs battery.
 */
function autoplayAllowed(): boolean {
  const saveData = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData === true;
  return window.matchMedia("(pointer: fine)").matches && !saveData;
}

/** True once the page has loaded and the browser is idle, so the 3D scene never delays it. */
function useAfterLoad(): boolean {
  const [idle, setIdle] = useState(false);
  useEffect(() => {
    let cancel = () => {};
    const go = () => {
      if (typeof window.requestIdleCallback === "function") {
        const id = window.requestIdleCallback(() => setIdle(true), { timeout: 2000 });
        cancel = () => window.cancelIdleCallback(id);
      } else {
        const id = window.setTimeout(() => setIdle(true), 200);
        cancel = () => window.clearTimeout(id);
      }
    };
    if (document.readyState === "complete") go();
    else window.addEventListener("load", go, { once: true });
    return () => {
      window.removeEventListener("load", go);
      cancel();
    };
  }, []);
  return idle;
}

/**
 * Running totals of the exposure: after field i, how many dies have been inspected and how many
 * of them failed. Computed from the real map, so the counters under the wafer are real counts.
 */
function exposureTotals(grid: DieGrid) {
  const layout = layoutDies(grid);
  const plan = planExposure(grid, layout, 6);
  const n = plan.fields.length;
  const dies = new Array<number>(n).fill(0);
  const failed = new Array<number>(n).fill(0);
  layout.dies.forEach((die, i) => {
    const f = plan.dieField[i]!;
    dies[f]! += 1;
    if (die.failed) failed[f]! += 1;
  });
  for (let i = 1; i < n; i += 1) {
    dies[i]! += dies[i - 1]!;
    failed[i]! += failed[i - 1]!;
  }
  return { fields: n, dies, failed };
}

/**
 * The home page's wafer: an SVG poster first (and for good without WebGL), then the 3D wafer,
 * loaded once the page is idle, which runs the scanner sequence once while the counters below
 * it follow the real dies it reveals. Replay runs it again. Once inspected, pointing at a die
 * shows its result. On touch screens the scene loads when someone runs the exposure.
 */
export function HeroWafer({
  grid,
  label,
  className,
}: {
  grid: DieGrid;
  /** Accessible description of the wafer. */
  label: string;
  className?: string;
}) {
  const reducedMotion = usePrefersReducedMotion();
  const canRender3d = useSyncExternalStore(noop, webglAvailable, () => false);
  const autoplay = useSyncExternalStore(noop, autoplayAllowed, () => false);
  const idle = useAfterLoad();
  const [requested, setRequested] = useState(false);
  // Reduced motion draws one still frame, which is cheap: it loads when idle on any device.
  const mount3d = canRender3d && (requested || (idle && (autoplay || reducedMotion)));
  const [ready, setReady] = useState(false);
  const [running, setRunning] = useState(true);
  const [playKey, setPlayKey] = useState(0);
  const [field, setField] = useState<number | null>(null);
  const [hover, setHover] = useState<DieHover | null>(null);
  const totals = useMemo(() => exposureTotals(grid), [grid]);

  const onReady = useCallback(() => setReady(true), []);
  const onEnd = useCallback(() => setRunning(false), []);
  const onField = useCallback((f: number) => setField(f), []);
  const onHover = useCallback((d: DieHover | null) => setHover(d), []);

  // Without the 3D sequence (no WebGL, reduced motion, or not run yet) the counters show the
  // whole wafer.
  const animated = mount3d && !reducedMotion;
  const done = !animated || field == null || field >= totals.fields;
  const at = done ? totals.fields - 1 : field;
  const exposed = animated && field == null ? 0 : totals.dies[at]!;
  const failed = animated && field == null ? 0 : totals.failed[at]!;

  return (
    <div className={cn("relative", className)}>
      <figure className="relative m-0 aspect-square w-full" aria-label={label} role="img">
        <div
          className={cn(
            "absolute inset-[11%] transition-opacity duration-[var(--dur-panel)] [transform:perspective(1600px)_rotateX(44deg)_rotateZ(24deg)]",
            ready && mount3d ? "opacity-0" : "opacity-100",
          )}
        >
          <WaferPoster grid={grid} />
        </div>
        {mount3d ? (
          <div
            className={cn(
              "absolute inset-0 transition-opacity duration-[var(--dur-panel)]",
              ready ? "opacity-100" : "opacity-0",
              !running && "cursor-crosshair",
            )}
          >
            <WaferScene
              grid={grid}
              playKey={playKey}
              reducedMotion={reducedMotion}
              onReady={onReady}
              onSequenceEnd={onEnd}
              onField={onField}
              onHover={onHover}
            />
          </div>
        ) : null}
        {hover ? <DieTip hover={hover} /> : null}
      </figure>

      <div className="relative z-[1] -mt-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-2 sm:-mt-14 lg:-mt-20">
        <dl className="tnum flex flex-wrap gap-x-6 gap-y-1 text-[13px] leading-5" aria-hidden="true">
          <div className="flex items-baseline gap-1.5">
            <dt className="text-ink-3">Field</dt>
            <dd className="text-ink">
              {formatInt(done ? totals.fields : at + 1)}
              <span className="text-ink-3"> of {formatInt(totals.fields)}</span>
            </dd>
          </div>
          <div className="flex items-baseline gap-1.5">
            <dt className="text-ink-3">Dies inspected</dt>
            <dd className="text-ink">{formatInt(exposed)}</dd>
          </div>
          <div className="flex items-baseline gap-1.5">
            <dt className="text-ink-3">Failed</dt>
            <dd className="text-fail">{formatInt(failed)}</dd>
          </div>
        </dl>
        {canRender3d && !reducedMotion && !mount3d ? (
          <button
            type="button"
            onClick={() => {
              setRunning(true);
              setField(null);
              setRequested(true);
            }}
            className="rounded-sm py-1 text-[13px] text-ink-2 underline decoration-hairline-strong underline-offset-4 hover:text-ink"
          >
            Run the exposure
          </button>
        ) : animated ? (
          <button
            type="button"
            onClick={() => {
              setRunning(true);
              setField(null);
              setHover(null);
              setPlayKey((k) => k + 1);
            }}
            disabled={running}
            className="rounded-sm py-1 text-[13px] text-ink-2 underline decoration-hairline-strong underline-offset-4 hover:text-ink disabled:text-ink-3 disabled:no-underline"
          >
            {running ? "Scanning field by field…" : "Run the exposure again"}
          </button>
        ) : null}
      </div>
      {animated && !running ? (
        <p className="mt-1 text-[12px] leading-4 text-ink-3">Point at a die to read its wafer-test result.</p>
      ) : null}
    </div>
  );
}

/** The result of the die under the pointer, from the map itself. */
function DieTip({ hover }: { hover: DieHover }) {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed z-50 rounded-sm border border-hairline-strong bg-die-2 px-2.5 py-1.5 text-[12px] leading-4 text-ink"
      style={{ left: hover.clientX + 14, top: hover.clientY + 14 }}
    >
      <p className="tnum">
        Row {hover.row + 1}, column {hover.col + 1}
      </p>
      <p className={hover.failed ? "text-fail" : "text-pass"}>
        {hover.failed ? "Failed at wafer test" : "Passed wafer test"}
      </p>
      <p className="tnum text-ink-3">Exposure field {hover.field + 1}</p>
    </div>
  );
}
