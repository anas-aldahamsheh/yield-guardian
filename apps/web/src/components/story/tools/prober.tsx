"use client";

import { WAFER_CELL } from "@yield-guardian/contracts";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  arrivedLive,
  stageResult,
  type RunState,
  type WaferItem,
  type WaferPatternView,
} from "@/lib/live/run-state";
import { countsAsUnknown, testedLots } from "@/lib/live/stations";
import { formatInt } from "@/lib/format";

import { failsAlong, gridOf, probeOrder } from "../probe-order";
import { useScene, type SceneStore } from "../scene";
import styles from "../story.module.css";

/** The drawing's box (margins included), and places in it as percentages for the HTML over it. */
const VIEW = { x: 0, w: 360, h: 250 } as const;
const box = (x: number, y: number, w: number, h?: number) => ({
  left: `${((x - VIEW.x) / VIEW.w) * 100}%`,
  top: `${(y / VIEW.h) * 100}%`,
  width: `${(w / VIEW.w) * 100}%`,
  ...(h != null ? { height: `${(h / VIEW.h) * 100}%` } : {}),
});
const CHUCK = box(10, 4, 200, 200);
const READOUT = box(10, 208, 200, 38);
/** The chuck's centre and radius in the drawing (the wafer sits on it). */
const CHUCK_C = { x: 110, y: 104, r: 99 } as const;
/** The wafer's radius as a share of the chuck window's side. */
const WAFER_R = 0.465;

/**
 * Station 3: the prober's screen and the lot carrier. The prober steps over the real map die by
 * die in probe order and reveals each die's recorded result, failed dies in the fail colour; each
 * probed wafer goes back into its slot of the 25-slot carrier, slot 1 at the bottom. The film's
 * light lies faintly over the wafer and never covers a die.
 */
export function ProberTool({ state, store }: { state: RunState | null; store: SceneStore }) {
  const shown = useScene(store, (s) => s.revealed.has("wafer_pattern"));
  const pattern = state && shown ? stageResult(state, "wafer_pattern") : null;
  const lotShown = useScene(store, (s) => s.revealed.has("lot"));
  const lots = state && lotShown ? stageResult(state, "lot") : null;
  const lotFlagged = Boolean(lots?.lots.some((l) => l.flagged));
  const tested = useMemo(() => testedLots(lots), [lots]);
  const wafers = pattern?.wafers ?? [];

  return (
    <div className="relative">
      <svg
        viewBox={`${VIEW.x} 0 ${VIEW.w} ${VIEW.h}`}
        className="block h-auto w-full"
        aria-hidden="true"
      >
        {/* The chuck the wafer sits on */}
        <circle
          cx={CHUCK_C.x}
          cy={CHUCK_C.y}
          r={CHUCK_C.r}
          fill="rgb(255 255 255 / 0.025)"
          stroke="var(--hairline)"
          vectorEffect="non-scaling-stroke"
        />
        <Carrier2D
          store={store}
          pattern={pattern}
          tested={tested}
          flagged={lotFlagged}
          live={state != null && arrivedLive(state, { stage: "wafer_pattern" })}
        />
      </svg>
      <div className="absolute aspect-square" style={CHUCK}>
        <Probed2D store={store} wafers={wafers} />
      </div>
      <div className="absolute flex items-center justify-center" style={READOUT}>
        <ProbeReadout store={store} wafers={wafers} />
      </div>
    </div>
  );
}

/** The readout under the chuck: which wafer is on it, dies probed so far and how many failed. */
function ProbeReadout({ store, wafers }: { store: SceneStore; wafers: readonly WaferItem[] }) {
  const index = useScene(store, (s) => s.wafer);
  const dies = useScene(store, (s) => s.dies);
  const wafer = index != null ? wafers.find((w) => w.index === index) : undefined;
  const grid = useMemo(() => (wafer?.map ? gridOf(wafer.map) : null), [wafer]);
  const order = useMemo(() => (grid ? probeOrder(grid) : null), [grid]);
  const fails = useMemo(() => (grid && order ? failsAlong(grid, order) : null), [grid, order]);
  if (!wafer || !order || !fails) return null;
  const probed = Math.min(order.length, Math.floor(dies));
  return (
    <p className="tnum px-1 text-center text-[11.5px] leading-[15px] text-ink-2">
      <span className="block truncate">{`Wafer ${wafer.wafer}: ${formatInt(probed)} of ${formatInt(order.length)}`}</span>
      <span className="block truncate">
        {"dies probed, "}
        <span
          className={fails[probed] ? "text-fail" : undefined}
        >{`${formatInt(fails[probed]!)} failed`}</span>
      </span>
    </p>
  );
}

/**
 * The probed wafer, die by die, on device pixels so every die is crisp: dies probed so far show
 * their recorded result (passed in a quiet grey, failed in the fail colour), the rest are dim,
 * and the probe is a lit square with its crosshair.
 */
function Probed2D({ store, wafers }: { store: SceneStore; wafers: readonly WaferItem[] }) {
  const index = useScene(store, (s) => s.wafer);
  const dies = useScene(store, (s) => s.dies);
  const wafer = index != null ? wafers.find((w) => w.index === index) : undefined;
  const grid = useMemo(() => (wafer?.map ? gridOf(wafer.map) : null), [wafer]);
  const order = useMemo(() => (grid ? probeOrder(grid) : null), [grid]);
  const ref = useRef<HTMLCanvasElement>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(Math.round(entry.contentRect.width));
    });
    observer.observe(canvas);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const size = width || canvas.clientWidth;
    if (!size) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const side = Math.round(size * dpr);
    canvas.width = side;
    canvas.height = side;
    // Drawn on the CPU: the map is small, and a canvas kept on the GPU is a layer of its own that
    // anything drawn over it (the light crossing the screen) has to be lifted above.
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, side, side);
    const css = getComputedStyle(canvas);
    const color = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback;
    const c = side / 2;
    const radius = side * WAFER_R;

    ctx.lineWidth = Math.max(1, dpr);
    if (!grid || !order) {
      // No wafer on the chuck yet: only the place where it will sit.
      ctx.setLineDash([2 * dpr, 4 * dpr]);
      ctx.strokeStyle = color("--hairline-strong", "#3d4453");
      ctx.beginPath();
      ctx.arc(c, c, radius, 0, Math.PI * 2);
      ctx.stroke();
      return;
    }
    // The wafer: a disc with a lit rim and its notch at six o'clock.
    ctx.fillStyle = color("--surface-2", "#1a2131");
    ctx.beginPath();
    ctx.arc(c, c, radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = color("--hairline-strong", "#3d4453");
    ctx.stroke();
    ctx.fillStyle = color("--screen", "#060b18");
    ctx.beginPath();
    ctx.arc(c, c + radius, radius * 0.035, Math.PI, 0);
    ctx.fill();
    // The film's light, faint, on the wafer's face under the dies: it lightens the wafer and never
    // covers a die. Drawn here rather than laid over the canvas, which would have to be lifted
    // onto a layer of its own above it, and the station drawn after it with it.
    ctx.save();
    ctx.beginPath();
    ctx.arc(c, c, radius, 0, Math.PI * 2);
    ctx.clip();
    ctx.globalAlpha = 0.13;
    const film = ctx.createLinearGradient(c - radius, c - radius, c + radius, c + radius);
    film.addColorStop(0, color("--film-1", "#c09df4"));
    film.addColorStop(0.45, color("--film-3", "#71b8f4"));
    film.addColorStop(0.75, color("--film-5", "#44c6ca"));
    film.addColorStop(1, color("--film-6", "#44cf80"));
    ctx.fillStyle = film;
    ctx.fillRect(c - radius, c - radius, radius * 2, radius * 2);
    const lx = c - radius * 0.4;
    const ly = c - radius * 0.56;
    const glow = ctx.createRadialGradient(lx, ly, 0, lx, ly, radius * 0.8);
    glow.addColorStop(0, "rgb(255 255 255 / 0.5)");
    glow.addColorStop(1, "rgb(255 255 255 / 0)");
    ctx.fillStyle = glow;
    ctx.fillRect(c - radius, c - radius, radius * 2, radius * 2);
    ctx.restore();

    const n = Math.max(grid.height, grid.width);
    const pitch = (radius * 2 * 0.93) / n;
    const ox = c - (grid.width * pitch) / 2;
    const oy = c - (grid.height * pitch) / 2;
    const gap = pitch >= 5 ? Math.max(1, Math.round(pitch * 0.14)) : pitch >= 3 ? 1 : 0;
    const probed = Math.min(order.length, Math.floor(dies));
    const pass = color("--ink-3", "#9ba0ac");
    const fail = color("--fail", "#f95e62");
    const unprobed = color("--hairline", "#282f3e");
    const cell = (k: number) => {
      const col = k % grid.width;
      const row = Math.floor(k / grid.width);
      const x0 = Math.round(ox + col * pitch);
      const y0 = Math.round(oy + row * pitch);
      return [
        x0,
        y0,
        Math.max(1, Math.round(ox + (col + 1) * pitch) - gap - x0),
        Math.max(1, Math.round(oy + (row + 1) * pitch) - gap - y0),
      ] as const;
    };

    ctx.fillStyle = unprobed;
    for (let i = probed; i < order.length; i += 1) {
      const [x, y, w, h] = cell(order[i]!);
      ctx.fillRect(x, y, w, h);
    }
    ctx.globalAlpha = 0.5;
    ctx.fillStyle = pass;
    for (let i = 0; i < probed; i += 1) {
      const k = order[i]!;
      if (grid.cells[k] === WAFER_CELL.fail) continue;
      const [x, y, w, h] = cell(k);
      ctx.fillRect(x, y, w, h);
    }
    ctx.globalAlpha = 1;
    ctx.fillStyle = fail;
    for (let i = 0; i < probed; i += 1) {
      const k = order[i]!;
      if (grid.cells[k] !== WAFER_CELL.fail) continue;
      const [x, y, w, h] = cell(k);
      ctx.fillRect(x, y, w, h);
    }

    if (probed < order.length) {
      const [x, y, w, h] = cell(order[probed]!);
      const signal = color("--signal", "#7cc2fe");
      const line = Math.max(1, Math.round(dpr));
      // The crosshair, inside the wafer.
      ctx.save();
      ctx.beginPath();
      ctx.arc(c, c, radius, 0, Math.PI * 2);
      ctx.clip();
      ctx.globalAlpha = 0.3;
      ctx.fillStyle = signal;
      ctx.fillRect(Math.round(x + w / 2), 0, line, side);
      ctx.fillRect(0, Math.round(y + h / 2), side, line);
      ctx.restore();
      ctx.strokeStyle = signal;
      ctx.lineWidth = 1.5 * dpr;
      const pad = Math.max(1.5, pitch * 0.25);
      ctx.strokeRect(x - pad, y - pad, w + pad * 2, h + pad * 2);
    }
  }, [grid, order, dies, width]);

  return <canvas ref={ref} className="block aspect-square w-full" aria-hidden="true" />;
}

const SLOTS = 25;

/** The carrier from the front: 25 slots, slot 1 at the bottom; each probed wafer seen edge-on. */
function Carrier2D({
  store,
  pattern,
  tested,
  flagged,
  live,
}: {
  store: SceneStore;
  pattern: WaferPatternView | null;
  /** Lots the lot test covered, once its result is shown. */
  tested: ReadonlySet<string>;
  flagged: boolean;
  /**
   * The wafer maps reached this page on the stream: each probed wafer slides into its slot as
   * the line shows it. Read with the run's stored state (a reload), they are in their slots.
   */
  live: boolean;
}) {
  const wafers = pattern?.wafers ?? [];
  const filled = useScene(store, (s) => s.carrier);
  const current = useScene(store, (s) => s.wafer);
  const lot = wafers[0]?.lot;
  const inLot = wafers.filter((w) => w.lot === lot).slice(0, SLOTS);
  const x0 = 252;
  const x1 = 332;
  const top = 22;
  const bottom = 206;
  const pitch = (bottom - top) / SLOTS;
  return (
    <g>
      <rect
        x={x0 - 8}
        y={top - 10}
        width={x1 - x0 + 16}
        height={bottom - top + 18}
        rx={8}
        fill="rgb(255 255 255 / 0.02)"
        stroke={flagged ? "var(--fail)" : "var(--hairline-strong)"}
        strokeWidth={1.2}
        vectorEffect="non-scaling-stroke"
      />
      {Array.from({ length: SLOTS }, (_, i) => {
        const y = bottom - (i + 0.5) * pitch;
        const wafer = inLot[i];
        const loaded = wafer != null && i < filled;
        // A defect pattern in the fail colour, no pattern in grey, by the model's prediction.
        // Once the lot test has answered, a wafer it counts as unknown (energy score above its
        // threshold) is drawn hollow, so the filled bars are the lot test's count; a map unlike
        // the ones the model learned from gets a dot beside its slot: check it by eye.
        const tone = !wafer ? null : wafer.top_label !== "none" ? "var(--fail)" : "var(--ink-3)";
        const hollow =
          wafer != null &&
          pattern != null &&
          tested.has(wafer.lot) &&
          countsAsUnknown(wafer, pattern);
        return (
          <g key={i}>
            <path
              d={`M ${x0 - 6} ${y} h 4 M ${x1 + 2} ${y} h 4`}
              stroke="var(--hairline-strong)"
              vectorEffect="non-scaling-stroke"
            />
            {loaded && tone ? (
              <g
                className={live ? styles.slot : undefined}
                opacity={wafer.index === current ? 1 : 0.8}
              >
                <rect
                  x={x0}
                  y={y - 1.1}
                  width={x1 - x0}
                  height={2.2}
                  rx={1.1}
                  fill={hollow ? "none" : tone}
                  stroke={hollow ? tone : "none"}
                  strokeWidth={0.8}
                />
                {wafer.is_unknown ? (
                  <circle cx={x0 - 11} cy={y} r={1.5} fill="var(--ink-2)" />
                ) : null}
              </g>
            ) : null}
          </g>
        );
      })}
      <text x={x1 + 13} y={bottom + 2} fontSize={10} fill="var(--ink-3)">
        1
      </text>
      <text x={x1 + 13} y={top + 4} fontSize={10} fill="var(--ink-3)">
        25
      </text>
      <text x={(x0 + x1) / 2} y={bottom + 30} fontSize={10} textAnchor="middle" fill="var(--ink-3)">
        {lot ? `Carrier, ${lot.length > 18 ? `${lot.slice(0, 17)}…` : lot}` : "Carrier"}
      </text>
    </g>
  );
}
