"use client";

import dynamic from "next/dynamic";
import { useCallback, useState, useSyncExternalStore } from "react";

import type { DieGrid } from "@/lib/wafer/geometry";
import { cn } from "@/lib/utils";

import { WaferPoster } from "./wafer-poster";

const WaferScene = dynamic(() => import("./wafer-scene"), { ssr: false, loading: () => null });

function subscribeReducedMotion(callback: () => void) {
  const query = window.matchMedia("(prefers-reduced-motion: reduce)");
  query.addEventListener("change", callback);
  return () => query.removeEventListener("change", callback);
}

export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeReducedMotion,
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => false,
  );
}

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
 * The home page's wafer: an SVG poster first (and for good without WebGL), then the 3D wafer,
 * loaded on demand, which runs the stepper sequence once. Replay runs it again.
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
  const [ready, setReady] = useState(false);
  const [running, setRunning] = useState(true);
  const [playKey, setPlayKey] = useState(0);

  const onReady = useCallback(() => setReady(true), []);
  const onEnd = useCallback(() => setRunning(false), []);

  return (
    <div className={cn("relative", className)}>
      <figure className="relative m-0 aspect-square w-full" aria-label={label} role="img">
        <div
          className={cn(
            "absolute inset-[9%] transition-opacity duration-[var(--dur-panel)] [transform:perspective(1600px)_rotateX(35deg)]",
            ready && canRender3d ? "opacity-0" : "opacity-100",
          )}
        >
          <WaferPoster grid={grid} />
        </div>
        {canRender3d ? (
          <div
            className={cn(
              "absolute inset-0 transition-opacity duration-[var(--dur-panel)]",
              ready ? "opacity-100" : "opacity-0",
            )}
          >
            <WaferScene
              grid={grid}
              playKey={playKey}
              reducedMotion={reducedMotion}
              onReady={onReady}
              onSequenceEnd={onEnd}
            />
          </div>
        ) : null}
      </figure>
      {canRender3d && !reducedMotion ? (
        <button
          type="button"
          onClick={() => {
            setRunning(true);
            setPlayKey((k) => k + 1);
          }}
          disabled={running}
          className="absolute right-0 bottom-0 rounded-sm px-2 py-1 text-[13px] text-ink-2 underline decoration-hairline-strong underline-offset-4 hover:text-ink disabled:text-ink-3 disabled:no-underline"
        >
          {running ? "Exposing field by field…" : "Run the exposure again"}
        </button>
      ) : null}
    </div>
  );
}
