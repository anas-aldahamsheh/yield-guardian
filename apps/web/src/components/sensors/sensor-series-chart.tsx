"use client";

import type { HealthWindow, SensorSeries } from "@yield-guardian/contracts";
import { scaleLinear } from "d3";
import Link from "next/link";
import { type MouseEvent, useMemo, useState } from "react";

import { useWidth } from "@/components/charts/use-width";
import { formatInt, formatPlantTime, formatReading } from "@/lib/format";

/**
 * One sensor's readings in time order, against its reference range (1st to 99th percentile of
 * the FDC reference period, median dashed). Readings outside the range are marked; missing
 * readings are ticks on the rug below; weeks with a flat line are shaded; jumps are drawn as
 * vertical rules.
 */

const M = { left: 56, right: 14, top: 12, bottom: 44 };
const HEIGHT = 260;

function quantile(sorted: number[], p: number) {
  if (!sorted.length) return 0;
  const i = Math.min(sorted.length - 1, Math.max(0, Math.round(p * (sorted.length - 1))));
  return sorted[i]!;
}

export function seriesDomain(values: number[], reference: SensorSeries["reference"]): [number, number] {
  const sorted = [...values].sort((a, b) => a - b);
  let lo = Math.min(quantile(sorted, 0.005), reference?.q01 ?? Infinity);
  let hi = Math.max(quantile(sorted, 0.995), reference?.q99 ?? -Infinity);
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return [0, 1];
  if (lo === hi) {
    lo -= Math.abs(lo) * 0.1 || 1;
    hi += Math.abs(hi) * 0.1 || 1;
  }
  const pad = (hi - lo) * 0.06;
  const d = scaleLinear().domain([lo - pad, hi + pad]).nice(5).domain();
  return [d[0]!, d[1]!];
}

export function SensorSeriesChart({
  series,
  windows,
  flatlineWindows,
  jumpUnitIds,
}: {
  series: SensorSeries;
  windows: HealthWindow[];
  flatlineWindows: number[];
  jumpUnitIds: number[];
}) {
  const [ref, width] = useWidth<HTMLDivElement>(720);
  const [hover, setHover] = useState<number | null>(null);
  const points = series.points;
  const ref_ = series.reference;

  const model = useMemo(() => {
    const values = points.filter((p) => p.value != null).map((p) => p.value as number);
    const [y0, y1] = seriesDomain(values, ref_);
    const first = points[0]?.sequence ?? 0;
    const last = points.at(-1)?.sequence ?? 1;
    const x = scaleLinear().domain([first - 0.5, last + 0.5]).range([M.left, Math.max(M.left + 1, width - M.right)]);
    const y = scaleLinear().domain([y0, y1]).range([HEIGHT - M.bottom, M.top]);
    let d = "";
    let pen = false;
    const outside: { sx: number; sy: number; edge: "top" | "bottom" | null }[] = [];
    const missing: number[] = [];
    let outCount = 0;
    for (const p of points) {
      if (p.value == null) {
        missing.push(x(p.sequence));
        pen = false;
        continue;
      }
      const cy = Math.min(y(y0), Math.max(y(y1), y(p.value)));
      d += `${pen ? "L" : "M"}${x(p.sequence).toFixed(1)},${cy.toFixed(1)}`;
      pen = true;
      const out = ref_ != null && (p.value < ref_.q01 || p.value > ref_.q99);
      if (out) outCount += 1;
      const edge = p.value > y1 ? "top" : p.value < y0 ? "bottom" : null;
      if (out || edge) outside.push({ sx: x(p.sequence), sy: cy, edge });
    }
    // Map each health window and jump onto the sequence axis by plant time and unit.
    const bySeq = points.map((p) => ({ seq: p.sequence, t: Date.parse(p.timestamp) }));
    const seqAt = (iso: string, fallback: number) => bySeq.find((p) => p.t >= Date.parse(iso))?.seq ?? fallback;
    const shaded = windows
      .filter((w) => flatlineWindows.includes(w.window_id))
      .map((w) => ({ id: w.window_id, x0: x(seqAt(w.start, first) - 0.5), x1: x(seqAt(w.end, last + 1) - 0.5) }))
      .filter((s) => s.x1 > s.x0);
    const unitToSeq = new Map(points.map((p) => [p.unit_id, p.sequence]));
    const jumps = jumpUnitIds.map((u) => unitToSeq.get(u)).filter((s): s is number => s != null).map((s) => x(s));
    return { x, y, d, outside, outCount, missing, shaded, jumps, ticks: y.ticks(5), xTicks: x.ticks(Math.max(2, Math.floor(width / 110))) };
  }, [points, ref_, width, windows, flatlineWindows, jumpUnitIds]);

  const { x, y } = model;
  const hovered = hover != null ? points[hover] : undefined;

  const onMove = (e: MouseEvent<SVGSVGElement>) => {
    if (!points.length) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const seq = Math.round(x.invert(e.clientX - rect.left));
    const i = Math.min(points.length - 1, Math.max(0, seq - points[0]!.sequence));
    setHover(i);
  };

  return (
    <div className="min-w-0">
      <dl className="tnum grid min-h-[44px] grid-cols-2 gap-x-6 gap-y-1 rounded-sm bg-die-2 px-3 py-1.5 text-[13px] leading-5 sm:grid-cols-4">
        {hovered ? (
          <>
            <Item label="Unit">
              <Link href={`/units/${hovered.unit_id}`} className="underline decoration-hairline-strong underline-offset-4">
                {formatInt(hovered.unit_id)}
              </Link>
            </Item>
            <Item label="Plant time">{formatPlantTime(hovered.timestamp)}</Item>
            <Item label="Reading">{hovered.value == null ? <span className="text-ink-3">Not measured</span> : formatReading(hovered.value)}</Item>
            <Item label="Reference median">{ref_ ? formatReading(ref_.median) : "No reference"}</Item>
          </>
        ) : (
          <>
            <Item label="Units">{formatInt(points.length)}</Item>
            <Item label="Not measured">{formatInt(model.missing.length)}</Item>
            <Item label="Reference range">{ref_ ? `${formatReading(ref_.q01)} to ${formatReading(ref_.q99)}` : "No reference"}</Item>
            <Item label="Outside the range">{ref_ ? formatInt(model.outCount) : "–"}</Item>
          </>
        )}
      </dl>
      <div ref={ref} className="mt-2">
        <svg
          width={width}
          height={HEIGHT}
          role="img"
          aria-label={`${series.sensor} readings for ${points.length} units${ref_ ? `, reference range ${formatReading(ref_.q01)} to ${formatReading(ref_.q99)}` : ""}.`}
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
          className="block touch-pan-y"
        >
          {model.shaded.map((s) => (
            <rect key={s.id} x={s.x0} width={s.x1 - s.x0} y={M.top} height={HEIGHT - M.top - M.bottom} fill="var(--concern)" opacity={0.12} />
          ))}
          {model.ticks.map((t) => (
            <g key={t}>
              <line x1={M.left} x2={width - M.right} y1={y(t)} y2={y(t)} stroke="var(--hairline)" />
              <text x={M.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="tnum fill-ink-3 text-[11px]">
                {formatReading(t, 3)}
              </text>
            </g>
          ))}
          {ref_ ? (
            <>
              <rect
                x={M.left}
                width={width - M.left - M.right}
                y={y(ref_.q99)}
                height={Math.max(0, y(ref_.q01) - y(ref_.q99))}
                fill="var(--pass)"
                opacity={0.08}
              />
              <line x1={M.left} x2={width - M.right} y1={y(ref_.q99)} y2={y(ref_.q99)} stroke="var(--pass)" strokeDasharray="1.5 3" />
              <line x1={M.left} x2={width - M.right} y1={y(ref_.q01)} y2={y(ref_.q01)} stroke="var(--pass)" strokeDasharray="1.5 3" />
              <line x1={M.left} x2={width - M.right} y1={y(ref_.median)} y2={y(ref_.median)} stroke="var(--pass)" strokeDasharray="5 4" />
            </>
          ) : null}
          {model.jumps.map((jx, i) => (
            <line key={i} x1={jx} x2={jx} y1={M.top} y2={HEIGHT - M.bottom} stroke="var(--fail)" strokeWidth={1} opacity={0.3} />
          ))}
          <path d={model.d} fill="none" stroke="var(--ink-2)" strokeWidth={1} strokeLinejoin="round" />
          {model.outside.map((o, i) =>
            o.edge ? (
              <path key={i} d={o.edge === "top" ? `M${o.sx},${o.sy - 1} l3,5 h-6z` : `M${o.sx},${o.sy + 1} l3,-5 h-6z`} fill="var(--fail)" />
            ) : (
              <circle key={i} cx={o.sx} cy={o.sy} r={1.8} fill="var(--fail)" />
            ),
          )}
          {/* Missing readings */}
          <text x={M.left - 8} y={HEIGHT - M.bottom + 12} dy="0.32em" textAnchor="end" className="fill-ink-3 text-[11px]">
            Missing
          </text>
          {model.missing.map((mx, i) => (
            <line key={i} x1={mx} x2={mx} y1={HEIGHT - M.bottom + 7} y2={HEIGHT - M.bottom + 17} stroke="var(--ink-3)" />
          ))}
          {model.xTicks.map((t) => (
            <text key={t} x={x(t)} y={HEIGHT - 6} textAnchor="middle" className="tnum fill-ink-3 text-[11px]">
              {formatInt(t)}
            </text>
          ))}
          {hovered ? (
            <line x1={x(hovered.sequence)} x2={x(hovered.sequence)} y1={M.top} y2={HEIGHT - M.bottom + 17} stroke="var(--safelight)" strokeWidth={1.5} />
          ) : null}
        </svg>
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1.5 pl-[56px] text-[12px] leading-4 text-ink-2" aria-label="Legend">
        <li className="flex items-center gap-1.5">
          <svg width="16" height="10" aria-hidden="true">
            <rect width="16" height="10" fill="var(--pass)" opacity={0.15} />
            <line x1="0" x2="16" y1="5" y2="5" stroke="var(--pass)" strokeDasharray="5 4" />
          </svg>
          Reference range and median
        </li>
        <li className="flex items-center gap-1.5">
          <svg width="10" height="10" aria-hidden="true"><circle cx="5" cy="5" r="2.5" fill="var(--fail)" /></svg>
          Outside the range
        </li>
        <li className="flex items-center gap-1.5">
          <svg width="16" height="10" aria-hidden="true"><rect width="16" height="10" fill="var(--concern)" opacity={0.25} /></svg>
          Week with a flat line
        </li>
        <li className="flex items-center gap-1.5">
          <svg width="6" height="12" aria-hidden="true"><line x1="3" x2="3" y1="0" y2="12" stroke="var(--fail)" /></svg>
          Jump
        </li>
        <li>Horizontal axis: unit sequence</li>
      </ul>
    </div>
  );
}

function Item({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] leading-4 text-ink-3">{label}</dt>
      <dd className="truncate text-ink">{children}</dd>
    </div>
  );
}
