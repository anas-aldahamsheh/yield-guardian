"use client";

import { scaleLinear } from "d3";
import { type MouseEvent, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";

import { usePrefersReducedMotion } from "@/components/motion";
import { cn } from "@/lib/utils";

/**
 * One control chart: a statistic per unit in time order, with its limits drawn and labelled.
 * Charts in a stack share the x domain and one cursor, so a unit lines up across all of them.
 * Values above the axis are drawn as a triangle at the top edge and read out exactly.
 *
 * Motion (none under reduced motion): when the window moves on by a unit, the series slides
 * left by one step so the new unit arrives from the right; the newest unit carries a ring of
 * safelight, and pulses in the fail colour when it arrives beyond a limit. The cursor glides.
 */

export type MarkTone = "neutral" | "concern" | "fail";

export interface SeriesPoint {
  x: number;
  y: number | null;
  tone: MarkTone;
}

export interface LimitLine {
  value: number;
  label: string;
  pattern: "dashed" | "dotted" | "solid";
}

export interface RugMark {
  x: number;
  result: "pass" | "fail";
}

export const CHART_MARGIN = { left: 52, right: 14 } as const;

const TONE_FILL: Record<MarkTone, string> = {
  neutral: "var(--ink-3)",
  concern: "var(--concern)",
  fail: "var(--fail)",
};

const DASH: Record<LimitLine["pattern"], string | undefined> = {
  dashed: "5 4",
  dotted: "1.5 3",
  solid: undefined,
};

/** A top for the y axis that shows every limit and nearly every value, rounded to a nice step. */
export function axisMax(values: (number | null)[], limits: number[], floor = 0): number {
  const finite = values.filter((v): v is number => v != null && Number.isFinite(v)).sort((a, b) => a - b);
  const high = finite.length ? finite[Math.min(finite.length - 1, Math.floor(finite.length * 0.97))]! : 0;
  const top = Math.max(floor, high * 1.08, ...limits.map((l) => l * 1.25));
  const domain = scaleLinear().domain([0, top || 1]).nice(4).domain();
  return domain[1]!;
}

export function xScaleFor(domain: [number, number], width: number) {
  return scaleLinear()
    .domain([domain[0] - 0.5, domain[1] + 0.5])
    .range([CHART_MARGIN.left, Math.max(CHART_MARGIN.left + 1, width - CHART_MARGIN.right)]);
}

/**
 * Slide the series in when the window moves on: render at the new positions, offset by the
 * distance moved, then let the offset run out to zero.
 */
function useArrivalShift(first: number, step: number, reduced: boolean) {
  const [shift, setShift] = useState({ px: 0, animate: false });
  const previous = useRef(first);
  useLayoutEffect(() => {
    const moved = first - previous.current;
    previous.current = first;
    if (reduced || moved <= 0 || moved > 4) return;
    setShift({ px: moved * step, animate: false });
    let frame = requestAnimationFrame(() => {
      frame = requestAnimationFrame(() => setShift({ px: 0, animate: true }));
    });
    return () => cancelAnimationFrame(frame);
  }, [first, step, reduced]);
  return shift;
}

export function ControlChart({
  label,
  unitLabel,
  points,
  xDomain,
  yMax,
  limits,
  alarmAbove,
  formatTick,
  width,
  height = 148,
  cursorX,
  pinned = false,
  newestX,
  rug,
  showXAxis = false,
  onPointerX,
  onPick,
}: {
  label: string;
  /** Short unit for the axis, such as "%"; omit for dimensionless statistics. */
  unitLabel?: string;
  points: SeriesPoint[];
  xDomain: [number, number];
  yMax: number;
  limits: LimitLine[];
  /** Values above this are alarms: the band above it is tinted with the fail colour. */
  alarmAbove?: number;
  formatTick: (value: number) => string;
  width: number;
  height?: number;
  cursorX: number | null;
  pinned?: boolean;
  newestX?: number;
  rug?: { label: string; marks: RugMark[] };
  showXAxis?: boolean;
  onPointerX?: (x: number | null) => void;
  onPick?: (x: number) => void;
}) {
  const clipId = useId();
  const reduced = usePrefersReducedMotion();
  const rugHeight = rug ? 22 : 0;
  const axisHeight = showXAxis ? 22 : 0;
  const top = 28;
  const plotBottom = height - rugHeight - axisHeight - (rug || showXAxis ? 0 : 10);
  const x = useMemo(() => xScaleFor(xDomain, width), [xDomain, width]);
  const y = useMemo(() => scaleLinear().domain([0, yMax]).range([plotBottom, top]), [yMax, plotBottom]);
  const yTicks = y.ticks(3);
  const xTicks = showXAxis ? x.ticks(Math.max(2, Math.floor(width / 110))).filter(Number.isInteger) : [];
  const step = Math.abs(x(1) - x(0));
  const r = step >= 5 ? 2.6 : step >= 2.5 ? 2 : 1.5;
  const shift = useArrivalShift(xDomain[0], step, reduced);
  const right = width - CHART_MARGIN.right;

  const path = useMemo(() => {
    let d = "";
    let pen = false;
    for (const p of points) {
      if (p.y == null) {
        pen = false;
        continue;
      }
      const py = y(Math.min(p.y, yMax));
      d += `${pen ? "L" : "M"}${x(p.x).toFixed(1)},${py.toFixed(1)}`;
      pen = true;
    }
    return d;
  }, [points, x, y, yMax]);

  const nearest = (event: MouseEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const px = event.clientX - box.left;
    const value = Math.round(x.invert(px));
    return Math.min(xDomain[1], Math.max(xDomain[0], value));
  };

  // Marks that carry state are drawn last so they sit on top of ordinary points.
  const ordered = useMemo(
    () => [...points].sort((a, b) => (a.tone === "neutral" ? 0 : 1) - (b.tone === "neutral" ? 0 : 1)),
    [points],
  );
  const newest = newestX != null ? points.find((pt) => pt.x === newestX) : undefined;
  const latest = points.at(-1);
  const cursorPoint = cursorX != null ? points.find((pt) => pt.x === cursorX) : undefined;

  // The cursor glides only while the pointer moves across the chart, not when it first appears.
  const [glide, setGlide] = useState(false);
  useEffect(() => {
    const showing = cursorX != null;
    const id = requestAnimationFrame(() => setGlide(showing));
    return () => cancelAnimationFrame(id);
  }, [cursorX == null]); // eslint-disable-line react-hooks/exhaustive-deps

  const zoneTop = alarmAbove != null && alarmAbove < yMax ? y(alarmAbove) : null;

  return (
    <svg
      width={width}
      height={height}
      className="block touch-pan-y select-none"
      aria-hidden="true"
      onPointerMove={(e) => onPointerX?.(nearest(e))}
      onPointerLeave={() => onPointerX?.(null)}
      onClick={(e) => onPick?.(nearest(e))}
    >
      <defs>
        <clipPath id={clipId}>
          <rect x={CHART_MARGIN.left} y={0} width={Math.max(0, right - CHART_MARGIN.left)} height={height} />
        </clipPath>
      </defs>

      {/* The alarm zone: everything beyond the outer limit. */}
      {zoneTop != null ? (
        <rect x={CHART_MARGIN.left} y={top} width={Math.max(0, right - CHART_MARGIN.left)} height={Math.max(0, zoneTop - top)} fill="var(--fail-wash)" opacity={0.4} />
      ) : null}

      {/* Grid and y axis. */}
      {yTicks.map((t) => (
        <g key={t}>
          <line x1={CHART_MARGIN.left} x2={right} y1={y(t)} y2={y(t)} stroke="var(--hairline)" strokeWidth={1} shapeRendering="crispEdges" />
          <text x={CHART_MARGIN.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="tnum fill-ink-3 text-[11px]">
            {formatTick(t)}
          </text>
        </g>
      ))}
      <text x={0} y={4} dy="0.8em" className="fill-ink text-[13px] font-semibold">
        {label}
        {unitLabel ? <tspan className="fill-ink-3 font-normal"> {unitLabel}</tspan> : null}
      </text>
      {latest?.y != null ? (
        <text x={right} y={4} dy="0.8em" textAnchor="end" className="tnum fill-ink-2 text-[12px]">
          <tspan className="fill-ink-3">latest </tspan>
          {formatTick(latest.y)}
        </text>
      ) : null}

      {/* Limits, labelled where they end. */}
      {limits.map((limit) => {
        const ly = y(Math.min(limit.value, yMax));
        return (
          <g key={limit.label}>
            <line
              x1={CHART_MARGIN.left}
              x2={right}
              y1={ly}
              y2={ly}
              stroke="var(--ink-2)"
              strokeWidth={limit.pattern === "solid" ? 1.25 : 1}
              strokeDasharray={DASH[limit.pattern]}
              shapeRendering="crispEdges"
            />
            <text
              x={right}
              y={ly - 4}
              textAnchor="end"
              className="tnum fill-ink-2 text-[11px]"
              style={{ paintOrder: "stroke", stroke: "var(--die)", strokeWidth: 3, strokeLinejoin: "round" }}
            >
              {limit.label}
            </text>
          </g>
        );
      })}

      {/* The series, the newest unit and the final-test rug slide together. */}
      <g clipPath={`url(#${clipId})`}>
        <g
          style={{
            transform: `translateX(${shift.px}px)`,
            transition: shift.animate ? "transform var(--dur-arrive) var(--ease-arrive)" : "none",
          }}
        >
          <path d={path} fill="none" stroke="var(--mark-muted)" strokeWidth={1} strokeLinejoin="round" />
          {ordered.map((p) => {
            if (p.y == null) return null;
            const cx = x(p.x);
            if (p.y > yMax) {
              const s = r + 2;
              return (
                <path
                  key={p.x}
                  d={`M${cx},${top - 1} l${s},${s * 1.6} h${-2 * s}z`}
                  fill={TONE_FILL[p.tone]}
                  stroke="var(--die)"
                  strokeWidth={1.5}
                />
              );
            }
            const flagged = p.tone !== "neutral";
            return (
              <circle
                key={p.x}
                cx={cx}
                cy={y(p.y)}
                r={flagged ? r + 0.9 : r}
                fill={TONE_FILL[p.tone]}
                stroke={flagged ? "var(--die)" : "none"}
                strokeWidth={flagged ? 1.5 : 0}
              />
            );
          })}

          {/* The newest unit: a steady ring of safelight; on arrival one widening ring, and two
              fail-coloured rings if it arrived beyond a limit. */}
          {latest && latest.y != null ? (
            <g transform={`translate(${x(latest.x)},${latest.y > yMax ? top + r + 2 : y(latest.y)})`}>
              {newest === latest ? (
                <g key={`new-${newestX}`}>
                  {latest.tone === "fail" ? (
                    <circle r={r + 4} fill="none" stroke="var(--fail)" strokeWidth={1.5} className="alarm-pulse" />
                  ) : null}
                  <circle r={r + 5} fill="none" stroke="var(--safelight)" strokeWidth={1.5} className="arrival" />
                </g>
              ) : null}
              <circle r={r + 3} fill="none" stroke="var(--safelight)" strokeWidth={1.5} />
            </g>
          ) : null}

          {/* Final-test results under the chart: they arrive a fixed number of units later. */}
          {rug ? (
            <g>
              {rug.marks.map((m) => (
                <line
                  key={m.x}
                  x1={x(m.x)}
                  x2={x(m.x)}
                  y1={m.result === "fail" ? plotBottom + 4 : plotBottom + 9}
                  y2={plotBottom + 20}
                  stroke={m.result === "fail" ? "var(--fail)" : "var(--pass)"}
                  strokeWidth={m.result === "fail" ? 2 : 1}
                  strokeOpacity={m.result === "fail" ? 1 : 0.55}
                />
              ))}
            </g>
          ) : null}
        </g>
      </g>
      {rug ? (
        <text x={CHART_MARGIN.left - 8} y={plotBottom + 12} dy="0.32em" textAnchor="end" className="fill-ink-3 text-[11px]">
          {rug.label}
        </text>
      ) : null}

      {/* X axis: unit sequence numbers. */}
      {showXAxis ? (
        <g>
          {xTicks.map((t) => (
            <text key={t} x={x(t)} y={height - 6} textAnchor="middle" className="tnum fill-ink-3 text-[11px]">
              {t}
            </text>
          ))}
        </g>
      ) : null}

      {/* Shared cursor: a line and a ring on this chart's value, gliding between units. */}
      {cursorX != null ? (
        <g
          style={{
            transform: `translateX(${x(cursorX)}px)`,
            transition: glide && !reduced ? "transform 90ms linear" : "none",
          }}
          className="pointer-events-none"
        >
          <line
            x1={0}
            x2={0}
            y1={top}
            y2={plotBottom + rugHeight}
            stroke={pinned ? "var(--safelight)" : "var(--ink-2)"}
            strokeWidth={pinned ? 1.5 : 1}
            className={cn(!pinned && "opacity-70")}
          />
          {cursorPoint?.y != null ? (
            <circle
              cx={0}
              cy={y(Math.min(cursorPoint.y, yMax))}
              r={r + 3.5}
              fill="none"
              stroke={pinned ? "var(--safelight)" : "var(--ink)"}
              strokeWidth={1.5}
              style={{ transition: glide && !reduced ? "cy 90ms linear" : "none" }}
            />
          ) : null}
        </g>
      ) : null}
    </svg>
  );
}
