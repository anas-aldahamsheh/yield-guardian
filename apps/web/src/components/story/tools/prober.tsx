"use client";

import type { WaferPatternItem, WaferPatternResult } from "@yield-guardian/contracts";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { arrivedLive, stageResult, type RunState } from "@/lib/live/run-state";
import { countsAsUnknown, testedLots } from "@/lib/live/stations";
import { FILM } from "@/lib/wafer/geometry";
import { formatInt } from "@/lib/format";
import { cn } from "@/lib/utils";

import { failsAlong, gridOf, probeOrder } from "../probe-order";
import { useScene, type SceneStore } from "../scene";
import styles from "../story.module.css";

const ChuckScene = dynamic(() => import("../chuck-scene"), { ssr: false, loading: () => null });

/** The drawing's box (margins included), and places in it as percentages for the HTML over it. */
const VIEW = { x: -16, w: 392, h: 318 } as const;
const box = (x: number, y: number, w: number, h?: number) => ({
  left: `${((x - VIEW.x) / VIEW.w) * 100}%`,
  top: `${(y / VIEW.h) * 100}%`,
  width: `${(w / VIEW.w) * 100}%`,
  ...(h != null ? { height: `${(h / VIEW.h) * 100}%` } : {}),
});
const CHUCK = box(28, 86, 176, 176);
const READOUT = box(16, 268, 200, 46);

/**
 * Station 3: the prober and the lot carrier. The prober steps over the real map die by die in
 * probe order and reveals each die's recorded result; each probed wafer goes back into its slot
 * of the 25-slot carrier, slot 1 at the bottom. With WebGL and motion the wafer on the chuck is
 * 3D (thin-film colours for an assumed oxide, said under the drawing); otherwise it is the flat
 * map. The carrier is drawn from the front either way, one bar per wafer.
 */
export function ProberTool({
  state,
  store,
  active,
  use3d,
}: {
  state: RunState | null;
  store: SceneStore;
  active: boolean;
  use3d: boolean;
}) {
  const shown = useScene(store, (s) => s.revealed.has("wafer_pattern"));
  const pattern = state && shown ? stageResult(state, "wafer_pattern") : null;
  const lotShown = useScene(store, (s) => s.revealed.has("lot"));
  const lots = state && lotShown ? stageResult(state, "lot") : null;
  const lotFlagged = Boolean(lots?.lots.some((l) => l.flagged));
  const tested = useMemo(() => testedLots(lots), [lots]);
  const onChuck = useScene(store, (s) => s.wafer != null);
  const [ready3d, setReady3d] = useState(false);
  const markReady = useCallback(() => setReady3d(true), []);
  const flat = !use3d || !ready3d;
  const wafers = pattern?.wafers ?? [];

  return (
    <div>
      <div className="relative">
        <svg
          viewBox={`${VIEW.x} 0 ${VIEW.w} ${VIEW.h}`}
          className="block h-auto w-full"
          aria-hidden="true"
        >
          <ProberSilhouette active={active} />
          <Carrier2D
            store={store}
            pattern={pattern}
            tested={tested}
            flagged={lotFlagged}
            live={state != null && arrivedLive(state, { stage: "wafer_pattern" })}
          />
        </svg>
        <div className="absolute aspect-square" style={CHUCK}>
          {flat ? <Probed2D store={store} wafers={wafers} /> : null}
          {use3d && pattern ? (
            <div
              className={cn(
                "absolute inset-0 transition-opacity duration-[var(--dur-panel)]",
                ready3d ? "opacity-100" : "opacity-0",
              )}
            >
              <ChuckScene store={store} wafers={pattern.wafers} onReady={markReady} />
            </div>
          ) : null}
        </div>
        <div className="absolute flex items-center justify-center" style={READOUT}>
          <ProbeReadout store={store} wafers={wafers} />
        </div>
      </div>
      {use3d ? (
        <p
          className={cn(
            "mt-1.5 px-4 text-[12px] leading-4 text-ink-3",
            !(onChuck && ready3d) && "invisible",
          )}
        >
          {`Wafer colour: an assumed ${FILM.centreNm} nm oxide film.`}
        </p>
      ) : null}
    </div>
  );
}

function ProberSilhouette({ active }: { active: boolean }) {
  return (
    <g
      fill="none"
      stroke="var(--hairline-strong)"
      strokeWidth={1}
      vectorEffect="non-scaling-stroke"
      strokeLinejoin="round"
    >
      {/* Head plate with the probe card and the microscope above the chuck */}
      <path d="M 40 58 H 192 V 70 H 40 Z" fill="var(--die-2)" />
      <rect x={100} y={16} width={32} height={42} rx={3} fill="var(--die)" />
      <path d="M 108 16 V 8 H 124 V 16" />
      <path d="M 116 70 V 80" stroke="var(--ink-3)" />
      {/* Cabinet and its deck, with the readout panel */}
      <path d="M 16 268 V 70 H 40 M 192 70 H 216 V 268" />
      <path d="M 8 268 H 352" />
      <rect x={16} y={268} width={200} height={46} fill="var(--die)" />
      {/* Load port for the carrier */}
      <rect x={228} y={262} width={116} height={8} fill="var(--die-2)" />
      <circle
        cx={204}
        cy={84}
        r={3}
        fill={active ? "var(--safelight-lamp)" : "var(--hairline)"}
        stroke="none"
      />
    </g>
  );
}

/** The cabinet's readout: which wafer is on the chuck, dies probed so far and how many failed. */
function ProbeReadout({ store, wafers }: { store: SceneStore; wafers: WaferPatternItem[] }) {
  const index = useScene(store, (s) => s.wafer);
  const dies = useScene(store, (s) => s.dies);
  const wafer = index != null ? wafers.find((w) => w.index === index) : undefined;
  const grid = useMemo(() => (wafer ? gridOf(wafer.map) : null), [wafer]);
  const order = useMemo(() => (grid ? probeOrder(grid) : null), [grid]);
  const fails = useMemo(() => (grid && order ? failsAlong(grid, order) : null), [grid, order]);
  if (!wafer || !order || !fails) return null;
  const probed = Math.min(order.length, Math.floor(dies));
  return (
    <p className="tnum px-1 text-center text-[11px] leading-[14px] text-ink-2">
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

/** The probed wafer as a flat map: dies probed so far show their result, the probe is a lit square. */
function Probed2D({ store, wafers }: { store: SceneStore; wafers: WaferPatternItem[] }) {
  const index = useScene(store, (s) => s.wafer);
  const dies = useScene(store, (s) => s.dies);
  const wafer = index != null ? wafers.find((w) => w.index === index) : undefined;
  const grid = useMemo(() => (wafer ? gridOf(wafer.map) : null), [wafer]);
  const order = useMemo(() => (grid ? probeOrder(grid) : null), [grid]);
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const size = canvas.clientWidth;
    if (!size) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.round(size * dpr);
    canvas.height = Math.round(size * dpr);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size, size);
    const css = getComputedStyle(canvas);
    const color = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback;
    // The wafer disc, a little inside the chuck window, as the 3D wafer is.
    const radius = size * 0.42;
    ctx.fillStyle = color("--die-2", "#24221b");
    ctx.beginPath();
    ctx.arc(size / 2, size / 2, radius, 0, Math.PI * 2);
    ctx.fill();
    if (!grid || !order) return;
    const n = Math.max(grid.height, grid.width);
    const pitch = (radius * 2 * 0.94) / n;
    const ox = (size - grid.width * pitch) / 2;
    const oy = (size - grid.height * pitch) / 2;
    const gap = pitch >= 6 ? 1 : pitch >= 3 ? 0.5 : 0;
    const probed = Math.min(order.length, Math.floor(dies));
    const pass = color("--hairline-strong", "#4f4c43");
    const fail = color("--fail", "#eb556e");
    const unprobed = color("--hairline", "#37352e");
    const place = (k: number) =>
      [ox + (k % grid.width) * pitch, oy + Math.floor(k / grid.width) * pitch] as const;
    for (let i = 0; i < order.length; i += 1) {
      const k = order[i]!;
      const [x, y] = place(k);
      ctx.fillStyle = i < probed ? (grid.cells[k] === 2 ? fail : pass) : unprobed;
      ctx.fillRect(x + gap / 2, y + gap / 2, pitch - gap, pitch - gap);
    }
    if (probed < order.length) {
      const [x, y] = place(order[probed]!);
      ctx.strokeStyle = color("--safelight-lamp", "#f5d326");
      ctx.lineWidth = 1.5;
      ctx.strokeRect(x - 1, y - 1, pitch + 2, pitch + 2);
    }
  }, [grid, order, dies]);

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
  pattern: WaferPatternResult | null;
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
  const x0 = 244;
  const x1 = 328;
  const top = 100;
  const bottom = 256;
  const pitch = (bottom - top) / SLOTS;
  return (
    <g>
      <path
        d={`M ${x0 - 6} ${top - 8} V ${bottom + 6} M ${x1 + 6} ${top - 8} V ${bottom + 6} M ${x0 - 6} ${top - 8} H ${x1 + 6}`}
        fill="none"
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
      <text x={x1 + 11} y={bottom + 2} fontSize={10} fill="var(--ink-3)">
        1
      </text>
      <text x={x1 + 11} y={top + 4} fontSize={10} fill="var(--ink-3)">
        25
      </text>
    </g>
  );
}
