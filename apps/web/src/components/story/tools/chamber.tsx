"use client";

import { memo, useMemo, useState } from "react";

import type { UnitChartResult } from "@yield-guardian/contracts";

import { stageResult, type RunState } from "@/lib/live/run-state";
import { useUnitChart } from "@/lib/live/use-unit-chart";
import { formatNumber } from "@/lib/format";

import { Z_FULL, lampLevel } from "../scales";
import { useScene, type SceneStore } from "../scene";

/**
 * Station 1: a process chamber with its sensor bank. The bank has one lamp per SECOM sensor
 * (S001 to S590, row by row). A lamp's brightness is the absolute standardised reading |z| of the
 * unit in the chamber, 0 to 4 or more; a ring is a missing reading; sensors the models do not
 * monitor have no lamp. The sensors that contributed most to a T² or SPE alarm are ringed in
 * the fail colour.
 */

export const BANK_COLS = 30;
export const BANK_ROWS = 20;
const N_SENSORS = 590;
const PITCH = 7;
const BANK_X = 25;
const BANK_Y = 170;

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
  chart: UnitChartResult | undefined,
  showReadings: boolean,
): BankLamp[] {
  const intake = state ? stageResult(state, "intake") : null;
  const charts = state ? stageResult(state, "control_charts") : null;
  const unmonitored = new Set(intake?.unmonitored_sensors ?? []);
  const featureIndex = new Map((charts?.features ?? []).map((f, i) => [f, i]));
  const row = showReadings ? chart : undefined;
  const flagged =
    row && row.level === "alarm"
      ? new Set([...row.top_spe.slice(0, 5), ...row.top_t2.slice(0, 5)].map((c) => c.sensor))
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

const Bank = memo(function Bank({ lamps, power }: { lamps: BankLamp[]; power: number }) {
  const on = Math.round(power * N_SENSORS);
  return (
    <g>
      {lamps.map((lamp, i) => {
        const cx = BANK_X + (i % BANK_COLS) * PITCH + PITCH / 2;
        const cy = BANK_Y + Math.floor(i / BANK_COLS) * PITCH + PITCH / 2;
        if (!lamp.monitored || i >= on) {
          return <circle key={lamp.sensor} cx={cx} cy={cy} r={1.1} fill="var(--hairline)" />;
        }
        if (lamp.missing) {
          return (
            <circle
              key={lamp.sensor}
              cx={cx}
              cy={cy}
              r={2.1}
              fill="none"
              stroke="var(--ink-3)"
              strokeWidth={0.7}
            />
          );
        }
        // Powered with no reading shown yet (intake only): a dim pilot light.
        const level = lamp.z === undefined ? 0 : lampLevel(lamp.z);
        return (
          <g key={lamp.sensor}>
            <circle
              cx={cx}
              cy={cy}
              r={2.4}
              fill="var(--safelight-lamp)"
              opacity={0.16 + 0.84 * level}
            />
            {lamp.flagged ? (
              <circle cx={cx} cy={cy} r={3.3} fill="none" stroke="var(--fail)" strokeWidth={1} />
            ) : null}
          </g>
        );
      })}
    </g>
  );
});

export function ChamberTool({
  state,
  store,
  active,
}: {
  state: RunState | null;
  store: SceneStore;
  active: boolean;
}) {
  const unit = useScene(store, (s) => s.unit);
  const power = useScene(store, (s) => s.bank);
  const showReadings = useScene(store, (s) => s.revealed.has("control_charts"));
  const chart = useUnitChart(state, unit);
  const lamps = useMemo(() => bankLamps(state, chart, showReadings), [state, chart, showReadings]);
  const [hover, setHover] = useState<number | null>(null);
  const lamp = hover != null ? lamps[hover] : null;

  return (
    <div className="relative">
      <svg viewBox="-16 0 292 318" className="block h-auto w-full" aria-hidden="true">
        <ChamberSilhouette active={active} />
        {/* Bank panel */}
        <rect
          x={BANK_X - 7}
          y={BANK_Y - 9}
          width={BANK_COLS * PITCH + 14}
          height={BANK_ROWS * PITCH + 18}
          rx={2}
          fill="var(--room)"
          stroke="var(--hairline-strong)"
          vectorEffect="non-scaling-stroke"
        />
        <Bank lamps={lamps} power={power} />
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
        <div className="tnum pointer-events-none absolute top-1 right-1 rounded-[2px] border border-hairline bg-die-2 px-2 py-1 text-[12px] leading-4 text-ink-2">
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

/** The chamber: gas lines and valves, a domed lid, a viewport onto the pedestal, the pump below. */
function ChamberSilhouette({ active }: { active: boolean }) {
  const stroke = "var(--hairline-strong)";
  const detail = "var(--ink-3)";
  return (
    <g
      fill="none"
      stroke={stroke}
      strokeWidth={1}
      vectorEffect="non-scaling-stroke"
      strokeLinejoin="round"
    >
      {/* Gas lines into the lid, each with a valve */}
      <path d="M 52 14 H 104 V 34" />
      <path d="M 208 14 H 156 V 34" />
      <path d="M 130 6 V 30" />
      {[78, 182].map((x) => (
        <g key={x}>
          <path d={`M ${x - 6} 8 L ${x + 6} 20 M ${x - 6} 20 L ${x + 6} 8`} stroke={detail} />
          <rect x={x - 6} y={8} width={12} height={12} fill="var(--die)" />
        </g>
      ))}
      {/* Lid */}
      <path d="M 70 52 Q 70 32 130 30 Q 190 32 190 52 Z" fill="var(--die-2)" />
      <rect x={58} y={52} width={144} height={8} fill="var(--die-2)" />
      {/* Body */}
      <rect x={64} y={60} width={132} height={70} rx={4} fill="var(--die)" />
      {/* Viewport: the pedestal and a wafer on it, lit by the process when the chamber works */}
      <ellipse cx={130} cy={95} rx={40} ry={20} fill="var(--room)" stroke={detail} />
      <ellipse
        cx={130}
        cy={98}
        rx={26}
        ry={6}
        fill={active ? "var(--safelight-lamp)" : "var(--hairline)"}
        opacity={active ? 0.55 : 1}
        stroke="none"
        className="transition-[opacity,fill] duration-[var(--dur-panel)]"
      />
      <path d="M 112 104 H 148" stroke={detail} />
      {/* Clamps and ports on the body */}
      <path d="M 64 76 H 56 V 112 H 64" />
      <path d="M 196 76 H 204 V 112 H 196" />
      {/* Pump */}
      <path d="M 116 130 V 138 H 144 V 130" />
      <rect x={110} y={138} width={40} height={14} rx={3} fill="var(--die-2)" />
      {/* Status lamp */}
      <circle
        cx={186}
        cy={70}
        r={3}
        fill={active ? "var(--safelight-lamp)" : "var(--hairline)"}
        stroke="none"
      />
      {/* Cable down to the sensor bank */}
      <path d="M 186 130 V 161" strokeDasharray="2 2" stroke={detail} />
    </g>
  );
}

export const ZScaleNote = `Lamp brightness is |z|, each sensor's standardised reading for the unit in the chamber, from 0 to ${Z_FULL} or more.`;
