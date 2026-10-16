"use client";

import { memo, type ReactNode, useMemo, useState } from "react";

import { stageResult, type RunState, type UnitChartView } from "@/lib/live/run-state";
import { useUnitChart } from "@/lib/live/use-unit-chart";
import { formatNumber } from "@/lib/format";

import { Z_FULL, lampLevel } from "../scales";
import { useScene, type SceneStore } from "../scene";

/**
 * Station 1: the chamber's sensor bank on its screen. One lamp per SECOM sensor (S001 to S590,
 * row by row). A lamp's brightness is the absolute standardised reading |z| of the unit in the
 * chamber, 0 to 4 or more, in the film's 324 nm cyan (one hue for magnitude); a ring is a missing
 * reading; sensors the models do not monitor stay a dark point. The sensors that contributed most
 * to a T² or SPE alarm are ringed in the fail colour. The lamps power up row by row after intake.
 */

export const BANK_COLS = 24;
export const BANK_ROWS = 25;
const N_SENSORS = 590;
const PITCH = 7.6;
const BANK_X = 16;
const BANK_Y = 14;
/** The screen's drawing: the bank with a margin (bay.tsx sizes the columns by these widths). */
const VIEW_W = Math.round((BANK_COLS * PITCH + 2 * BANK_X) * 100) / 100;
const VIEW_H = 250;

export interface BankLamp {
  sensor: string;
  /** null: not monitored. */
  z: number | null | undefined;
  monitored: boolean;
  missing: boolean;
  flagged: boolean;
}

function sensorId(i: number) {
  return `S${String(i + 1).padStart(3, "0")}`;
}

/** The lamps of the bank for one unit's chart result, in sensor order. */
export function bankLamps(
  state: RunState | null,
  chart: UnitChartView | undefined,
  showReadings: boolean,
): BankLamp[] {
  const intake = state ? stageResult(state, "intake") : null;
  const charts = state ? stageResult(state, "control_charts") : null;
  const unmonitored = new Set(intake?.unmonitored_sensors ?? []);
  const featureIndex = new Map((charts?.features ?? []).map((f, i) => [f, i]));
  const row = showReadings ? chart : undefined;
  const flagged =
    row && row.level === "alarm"
      ? new Set(
          [...(row.top_spe ?? []).slice(0, 5), ...(row.top_t2 ?? []).slice(0, 5)].map(
            (c) => c.sensor,
          ),
        )
      : new Set<string>();
  return Array.from({ length: N_SENSORS }, (_, i) => {
    const sensor = sensorId(i);
    const monitored = intake ? !unmonitored.has(sensor) : false;
    const j = featureIndex.get(sensor);
    const z = row?.z && j != null ? row.z[j] : undefined;
    return {
      sensor,
      z,
      monitored,
      missing: monitored && row?.z != null && j != null && z == null,
      flagged: flagged.has(sensor),
    };
  });
}

/** A coordinate of the bank, to two decimals (7.6 steps add float noise to every one). */
const at = (v: number) => Math.round(v * 100) / 100;

const Bank = memo(function Bank({ lamps, power }: { lamps: BankLamp[]; power: number }) {
  const on = Math.round(power * N_SENSORS);
  // The dark points (not monitored, or not powered yet) are one path of round dots, a zero-length
  // segment with a round cap each: as 590 circles they were 590 nodes to parse, style, lay out
  // and hydrate before the line's first paint. Lit and missing lamps stay circles.
  let dark = "";
  const shown: ReactNode[] = [];
  lamps.forEach((lamp, i) => {
    const cx = at(BANK_X + (i % BANK_COLS) * PITCH + PITCH / 2);
    const cy = at(BANK_Y + Math.floor(i / BANK_COLS) * PITCH + PITCH / 2);
    if (!lamp.monitored || i >= on) {
      dark += `M${cx} ${cy}h0`;
      return;
    }
    if (lamp.missing) {
      shown.push(
        <circle
          key={lamp.sensor}
          cx={cx}
          cy={cy}
          r={2}
          fill="none"
          stroke="var(--ink-3)"
          strokeWidth={0.7}
        />,
      );
      return;
    }
    // Powered with no reading shown yet (intake only): a dim pilot light.
    const level = lamp.z === undefined ? 0 : lampLevel(lamp.z);
    shown.push(
      <g key={lamp.sensor}>
        <circle cx={cx} cy={cy} r={2.45} fill="var(--film-4)" opacity={0.14 + 0.86 * level} />
        {lamp.flagged ? (
          <circle cx={cx} cy={cy} r={3.4} fill="none" stroke="var(--fail)" strokeWidth={1.1} />
        ) : null}
      </g>,
    );
  });
  return (
    <g>
      {dark ? (
        <path
          d={dark}
          fill="none"
          stroke="var(--hairline-strong)"
          strokeWidth={2.1}
          strokeLinecap="round"
        />
      ) : null}
      {shown}
    </g>
  );
});

export function ChamberTool({ state, store }: { state: RunState | null; store: SceneStore }) {
  const unit = useScene(store, (s) => s.unit);
  const power = useScene(store, (s) => s.bank);
  const showReadings = useScene(store, (s) => s.revealed.has("control_charts"));
  const chart = useUnitChart(state, unit);
  const lamps = useMemo(() => bankLamps(state, chart, showReadings), [state, chart, showReadings]);
  const [hover, setHover] = useState<number | null>(null);
  const lamp = hover != null ? lamps[hover] : null;

  const monitored = lamps.filter((l) => l.monitored).length;
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} className="block h-auto w-full" aria-hidden="true">
        <Bank lamps={lamps} power={power} />
        {/* The bank's scale: what a lamp is, under it */}
        <g fontSize={10} fill="var(--ink-3)">
          <text x={BANK_X} y={BANK_Y + BANK_ROWS * PITCH + 18}>
            {state && monitored
              ? `${monitored} of ${N_SENSORS} sensors monitored`
              : `${N_SENSORS} sensors`}
          </text>
          <g transform={`translate(${BANK_X + 3} ${BANK_Y + BANK_ROWS * PITCH + 31})`}>
            {[0, 0.33, 0.66, 1].map((level, i) => (
              <circle
                key={level}
                cx={i * 9}
                cy={0}
                r={2.45}
                fill="var(--film-4)"
                opacity={0.14 + 0.86 * level}
              />
            ))}
            <text x={36} y={3.5}>
              {`|z| from 0 to ${Z_FULL} or more`}
            </text>
          </g>
        </g>
        <rect
          x={BANK_X}
          y={BANK_Y}
          width={BANK_COLS * PITCH}
          height={BANK_ROWS * PITCH}
          fill="transparent"
          onPointerMove={(e) => {
            const box = e.currentTarget.getBoundingClientRect();
            const col = Math.floor(((e.clientX - box.left) / box.width) * BANK_COLS);
            const row = Math.floor(((e.clientY - box.top) / box.height) * BANK_ROWS);
            const i = row * BANK_COLS + col;
            setHover(i >= 0 && i < N_SENSORS && col >= 0 && col < BANK_COLS ? i : null);
          }}
          onPointerLeave={() => setHover(null)}
        />
      </svg>
      {lamp ? (
        <div className="tnum pointer-events-none absolute top-1 right-1 rounded-[8px] bg-surface-2/90 px-2 py-1 text-[12px] leading-4 text-ink-2 shadow-float backdrop-blur-sm">
          <span className="text-ink">{lamp.sensor}</span>{" "}
          {!lamp.monitored
            ? "not monitored"
            : lamp.missing
              ? "no reading"
              : lamp.z != null
                ? `z ${formatNumber(lamp.z, 2)}`
                : "monitored"}
        </div>
      ) : null}
    </div>
  );
}

export const ZScaleNote = `Lamp brightness is |z|, each sensor's standardised reading for the unit in the chamber, from 0 to ${Z_FULL} or more.`;
