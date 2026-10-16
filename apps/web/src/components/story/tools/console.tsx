"use client";

import { useMemo } from "react";

import { formatNumber, formatPercent, formatReading } from "@/lib/format";
import { leadingDrift } from "@/lib/live/rest";
import {
  stageResult,
  type ControlChartsView,
  type DriftHealthView,
  type RunState,
  type SensorRiskView,
} from "@/lib/live/run-state";

import {
  arcPath,
  decadeLabel,
  decades,
  dialAngle,
  fixed,
  logDomain,
  logPosition,
  polar,
  riskDomain,
  type LogScale,
} from "../scales";
import { useScene, type SceneStore } from "../scene";

/**
 * Station 2: the monitoring screen. Three dials read the unit at the console: Hotelling T² and
 * SPE on log scales with the model's 99% and 99.9% limits, and the calibrated failure risk with
 * the elevated and high bands of its operating points. The strip below shows the run's units in
 * order (a tick per unit, red where T² or SPE is beyond the 99.9% limit) and the EWMA of the
 * leading sensor group that moved most, with its control limits.
 */

const SWEEP = 240;
const R = 42;
const DIAL_Y = 60;
const DIAL_X = [60, 180, 300] as const;
const SCREEN = { x: 8, y: 130, w: 344, h: 110 } as const;

export function ConsoleTool({ state, store }: { state: RunState | null; store: SceneStore }) {
  const revealed = useScene(store, (s) => s.revealed);
  const charts =
    state && revealed.has("control_charts") ? stageResult(state, "control_charts") : null;
  const risk = state && revealed.has("sensor_risk") ? stageResult(state, "sensor_risk") : null;
  const drift = state && revealed.has("drift_health") ? stageResult(state, "drift_health") : null;

  return (
    <svg viewBox="0 0 360 250" className="block h-auto w-full" aria-hidden="true">
      <LogDial store={store} cx={DIAL_X[0]} label="T²" charts={charts} statistic="t2" />
      <LogDial store={store} cx={DIAL_X[1]} label="SPE" charts={charts} statistic="spe" />
      <RiskDial store={store} cx={DIAL_X[2]} risk={risk} />
      <Screen
        store={store}
        charts={charts}
        risk={risk}
        drift={drift}
        skippedDrift={state?.stages.drift_health.status === "skipped"}
      />
    </svg>
  );
}

function tickPath(cx: number, cy: number, r0: number, r1: number, angle: number) {
  const [x0, y0] = polar(cx, cy, r0, angle);
  const [x1, y1] = polar(cx, cy, r1, angle);
  return `M ${fixed(x0)} ${fixed(y0)} L ${fixed(x1)} ${fixed(y1)}`;
}

function Needle({ cx, cy, t, tone }: { cx: number; cy: number; t: number | null; tone: string }) {
  if (t == null) return <circle cx={cx} cy={cy} r={2.5} fill="var(--hairline-strong)" />;
  const angle = dialAngle(t, SWEEP);
  const [x, y] = polar(cx, cy, R - 4, angle);
  const [bx, by] = polar(cx, cy, 7, angle + 180);
  return (
    <g>
      <line
        x1={fixed(bx)}
        y1={fixed(by)}
        x2={fixed(x)}
        y2={fixed(y)}
        stroke={tone}
        strokeWidth={1.8}
        strokeLinecap="round"
      />
      <circle cx={cx} cy={cy} r={3.4} fill={tone} />
      <circle cx={cx} cy={cy} r={1.2} fill="var(--screen)" />
    </g>
  );
}

function DialFace({ cx, label }: { cx: number; label: string }) {
  return (
    <g>
      <circle
        cx={cx}
        cy={DIAL_Y}
        r={R + 8}
        fill="rgb(255 255 255 / 0.025)"
        stroke="var(--hairline)"
        vectorEffect="non-scaling-stroke"
      />
      <path
        d={arcPath(cx, DIAL_Y, R, -SWEEP / 2, SWEEP / 2)}
        fill="none"
        stroke="var(--hairline-strong)"
        vectorEffect="non-scaling-stroke"
      />
      <text
        x={cx}
        y={DIAL_Y + 19}
        textAnchor="middle"
        fontSize={12}
        fill="var(--ink-3)"
        fontWeight={560}
      >
        {label}
      </text>
    </g>
  );
}

function LogDial({
  store,
  cx,
  label,
  charts,
  statistic,
}: {
  store: SceneStore;
  cx: number;
  label: string;
  charts: ControlChartsView | null;
  statistic: "t2" | "spe";
}) {
  const value = useScene(store, (s) => (statistic === "t2" ? s.t2 : s.spe));
  const limits = charts
    ? statistic === "t2"
      ? [charts.limits.t2_99, charts.limits.t2_999]
      : [charts.limits.spe_99, charts.limits.spe_999]
    : null;
  const scale = useMemo<LogScale | null>(
    () =>
      charts && limits
        ? logDomain(
            charts.units.map((u) => u[statistic]),
            limits,
          )
        : null,
    // limits derive from charts
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [charts, statistic],
  );
  const beyond = value != null && limits != null && value > limits[1]!;
  return (
    <g>
      <DialFace cx={cx} label={label} />
      {scale && limits ? (
        <g>
          {/* Beyond the 99.9% limit: the alarm zone */}
          <path
            d={arcPath(
              cx,
              DIAL_Y,
              R - 3,
              dialAngle(logPosition(limits[1]!, scale), SWEEP),
              SWEEP / 2,
            )}
            fill="none"
            stroke="var(--fail)"
            strokeOpacity={0.35}
            strokeWidth={5}
          />
          {decades(scale).map((e, i, all) => {
            const angle = dialAngle(logPosition(10 ** e, scale), SWEEP);
            const labelled = all.length <= 4 || i % 2 === 0 || i === all.length - 1;
            const [lx, ly] = polar(cx, DIAL_Y, R + 12 > 50 ? 50 : R + 12, angle);
            return (
              <g key={e}>
                <path
                  d={tickPath(cx, DIAL_Y, R - 5, R, angle)}
                  stroke="var(--ink-3)"
                  vectorEffect="non-scaling-stroke"
                />
                {labelled ? (
                  <text
                    x={fixed(lx)}
                    y={fixed(ly + 3.5)}
                    textAnchor="middle"
                    fontSize={10}
                    fill="var(--ink-3)"
                  >
                    {decadeLabel(e)}
                  </text>
                ) : null}
              </g>
            );
          })}
          {/* The model's limits */}
          <path
            d={tickPath(cx, DIAL_Y, R - 9, R + 2, dialAngle(logPosition(limits[0]!, scale), SWEEP))}
            stroke="var(--concern)"
            strokeWidth={1.5}
          />
          <path
            d={tickPath(cx, DIAL_Y, R - 9, R + 2, dialAngle(logPosition(limits[1]!, scale), SWEEP))}
            stroke="var(--fail)"
            strokeWidth={1.5}
          />
          <Needle
            cx={cx}
            cy={DIAL_Y}
            t={value != null ? logPosition(value, scale) : null}
            tone={beyond ? "var(--fail)" : "var(--ink)"}
          />
          <text
            x={cx}
            y={DIAL_Y + 37}
            textAnchor="middle"
            fontSize={15}
            className="tnum"
            fill={beyond ? "var(--fail)" : "var(--ink)"}
          >
            {value != null ? formatReading(value, 3) : ""}
          </text>
        </g>
      ) : (
        <Needle cx={cx} cy={DIAL_Y} t={null} tone="var(--ink)" />
      )}
    </g>
  );
}

function RiskDial({
  store,
  cx,
  risk,
}: {
  store: SceneStore;
  cx: number;
  risk: SensorRiskView | null;
}) {
  const value = useScene(store, (s) => s.risk);
  const domain = useMemo(
    () =>
      risk
        ? riskDomain(
            risk.units.map((u) => u.risk),
            risk.threshold,
          )
        : null,
    [risk],
  );
  const t = (v: number) => (domain ? v / domain : 0);
  const band =
    risk && value != null
      ? value >= risk.threshold
        ? "high"
        : value >= risk.elevated_threshold
          ? "elevated"
          : "low"
      : null;
  const tone =
    band === "high" ? "var(--fail)" : band === "elevated" ? "var(--concern)" : "var(--ink-2)";
  return (
    <g>
      <DialFace cx={cx} label="Risk" />
      {risk && domain ? (
        <g>
          <path
            d={arcPath(
              cx,
              DIAL_Y,
              R - 3,
              dialAngle(t(risk.elevated_threshold), SWEEP),
              dialAngle(t(risk.threshold), SWEEP),
            )}
            fill="none"
            stroke="var(--concern)"
            strokeOpacity={0.45}
            strokeWidth={5}
          />
          <path
            d={arcPath(cx, DIAL_Y, R - 3, dialAngle(t(risk.threshold), SWEEP), SWEEP / 2)}
            fill="none"
            stroke="var(--fail)"
            strokeOpacity={0.35}
            strokeWidth={5}
          />
          {/* The dial fills to the calibrated risk */}
          {value != null && value > 0 ? (
            <path
              d={arcPath(cx, DIAL_Y, R - 11, -SWEEP / 2, dialAngle(t(value), SWEEP))}
              fill="none"
              stroke={tone}
              strokeWidth={4}
              strokeLinecap="butt"
            />
          ) : null}
          {[0, 0.5, 1].map((f) => {
            const angle = dialAngle(f, SWEEP);
            const [lx, ly] = polar(cx, DIAL_Y, 50, angle);
            return (
              <g key={f}>
                <path
                  d={tickPath(cx, DIAL_Y, R - 5, R, angle)}
                  stroke="var(--ink-3)"
                  vectorEffect="non-scaling-stroke"
                />
                <text
                  x={fixed(lx)}
                  y={fixed(ly + 3.5)}
                  textAnchor="middle"
                  fontSize={10}
                  fill="var(--ink-3)"
                >
                  {formatPercent(domain * f, 0)}
                </text>
              </g>
            );
          })}
          <path
            d={tickPath(cx, DIAL_Y, R - 9, R + 2, dialAngle(t(risk.threshold), SWEEP))}
            stroke="var(--fail)"
            strokeWidth={1.5}
          />
          <Needle
            cx={cx}
            cy={DIAL_Y}
            t={value != null ? t(value) : null}
            tone={band === "high" ? "var(--fail)" : "var(--ink)"}
          />
          <text
            x={cx}
            y={DIAL_Y + 37}
            textAnchor="middle"
            fontSize={15}
            className="tnum"
            fill={tone}
          >
            {value != null ? formatPercent(value, 1) : ""}
          </text>
        </g>
      ) : (
        <Needle cx={cx} cy={DIAL_Y} t={null} tone="var(--ink)" />
      )}
    </g>
  );
}

function Screen({
  store,
  charts,
  risk,
  drift,
  skippedDrift,
}: {
  store: SceneStore;
  charts: ControlChartsView | null;
  risk: SensorRiskView | null;
  drift: DriftHealthView | null;
  skippedDrift: boolean;
}) {
  const unit = useScene(store, (s) => s.unit);
  const passed = useScene(store, (s) => s.unitsPassed);
  const drawn = useScene(store, (s) => s.drift);
  const n = charts?.units.length ?? risk?.units.length ?? 0;
  const group = leadingDrift(drift);
  const { x, y, w, h } = SCREEN;
  const xAt = (i: number) => x + 8 + ((i + 0.5) / Math.max(1, n)) * (w - 16);
  const ticks = { y: y + 10, h: 12 };
  const strip = { y: y + 40, h: h - 52 };
  // The leading group's EWMA is in every first paint (lib/live/glance.ts).
  const ewma = group?.ewma ?? [];
  const span = group ? Math.max(group.ewma_limit * 1.25, ...ewma.map((v) => Math.abs(v))) : 1;
  const yAt = (v: number) => strip.y + strip.h / 2 - (v / span) * (strip.h / 2);
  const shown = Math.floor(drawn);
  const points = group
    ? ewma
        .slice(0, Math.max(0, Math.min(ewma.length, shown)))
        .map((v, i) => `${fixed(xAt(i))},${fixed(yAt(v))}`)
        .join(" ")
    : "";

  return (
    <g>
      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        rx={8}
        fill="rgb(255 255 255 / 0.025)"
        stroke="var(--hairline)"
        vectorEffect="non-scaling-stroke"
      />
      {/* One tick per unit, in input order: lit once the console has read it */}
      {Array.from({ length: n }, (_, i) => {
        const level = charts?.units[i]?.level;
        const above = risk?.units[i]?.above_threshold;
        const read = i < passed;
        const fill = !read
          ? "var(--hairline)"
          : level === "alarm"
            ? "var(--fail)"
            : level === "warning"
              ? "var(--concern)"
              : "var(--ink-3)";
        const bw = Math.max(1, Math.min(5, ((w - 16) / Math.max(1, n)) * 0.6));
        return (
          <g key={i}>
            <rect
              x={fixed(xAt(i) - bw / 2)}
              y={ticks.y}
              width={fixed(bw)}
              height={ticks.h}
              fill={fill}
            />
            {read && above ? (
              <rect
                x={fixed(xAt(i) - bw / 2 - 1.5)}
                y={ticks.y - 4}
                width={fixed(bw + 3)}
                height={2}
                fill="var(--fail)"
              />
            ) : null}
          </g>
        );
      })}
      {/* EWMA of the leading group with its control limits */}
      {group ? (
        <g>
          <line
            x1={x + 8}
            x2={x + w - 8}
            y1={yAt(0)}
            y2={yAt(0)}
            stroke="var(--hairline)"
            vectorEffect="non-scaling-stroke"
          />
          {[group.ewma_limit, -group.ewma_limit].map((v) => (
            <line
              key={v}
              x1={x + 8}
              x2={x + w - 8}
              y1={fixed(yAt(v))}
              y2={fixed(yAt(v))}
              stroke="var(--fail)"
              strokeDasharray="3 3"
              strokeOpacity={0.8}
              vectorEffect="non-scaling-stroke"
            />
          ))}
          <polyline
            points={points}
            fill="none"
            stroke="var(--ink)"
            strokeWidth={1.4}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          <text x={x + 8} y={strip.y - 5} fontSize={10} fill="var(--ink-3)">
            {`EWMA, sensor group ${group.group_id} (${group.sensors.length} ${group.sensors.length === 1 ? "sensor" : "sensors"}), limits ±${formatNumber(group.ewma_limit, 2)}`}
          </text>
        </g>
      ) : (
        <text x={x + 8} y={strip.y + strip.h / 2} fontSize={11} fill="var(--ink-3)">
          {skippedDrift ? "Drift needs at least 20 units in time order." : n ? "" : ""}
        </text>
      )}
      {unit != null && n ? (
        <line
          x1={fixed(xAt(unit))}
          x2={fixed(xAt(unit))}
          y1={y + 4}
          y2={y + h - 4}
          stroke="var(--signal)"
          strokeWidth={1.2}
        />
      ) : null}
    </g>
  );
}
