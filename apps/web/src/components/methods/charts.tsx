"use client";

import type {
  BlockInfo,
  ConfusionMatrix as Confusion,
  CurvePoint,
  OperatingPoint,
  ReliabilityBin,
} from "@yield-guardian/contracts";
import { scaleLinear, scaleSqrt } from "d3";
import { useState } from "react";

import { useWidth } from "@/components/charts/use-width";
import { formatInt, formatPercent, formatPlantTime } from "@/lib/format";
import { type PatternLabel, patternName } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { ScrollRegion } from "@/components/scroll-region";

const M = { left: 48, right: 16, top: 14, bottom: 40 };

function Axes({
  x,
  y,
  width,
  height,
  xLabel,
  yLabel,
  format = (v: number) => `${Math.round(v * 100)}%`,
}: {
  x: (v: number) => number;
  y: (v: number) => number;
  width: number;
  height: number;
  xLabel: string;
  yLabel: string;
  format?: (v: number) => string;
}) {
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  return (
    <g>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={M.left} x2={width - M.right} y1={y(t)} y2={y(t)} stroke="var(--hairline)" />
          <text
            x={M.left - 8}
            y={y(t)}
            dy="0.32em"
            textAnchor="end"
            className="tnum fill-ink-3 text-[11px]"
          >
            {format(t)}
          </text>
          <text
            x={x(t)}
            y={height - M.bottom + 16}
            textAnchor="middle"
            className="tnum fill-ink-3 text-[11px]"
          >
            {format(t)}
          </text>
        </g>
      ))}
      <text
        x={(M.left + width - M.right) / 2}
        y={height - 6}
        textAnchor="middle"
        className="fill-ink-2 text-[12px]"
      >
        {xLabel}
      </text>
      <text
        transform={`translate(12 ${(M.top + height - M.bottom) / 2}) rotate(-90)`}
        textAnchor="middle"
        className="fill-ink-2 text-[12px]"
      >
        {yLabel}
      </text>
    </g>
  );
}

/**
 * Precision against recall on the test block, with the operating points chosen on validation and
 * the no-skill line at the failure rate.
 */
export function PrCurve({
  curve,
  points,
  prevalence,
  defaultId,
}: {
  curve: CurvePoint[];
  points: OperatingPoint[];
  prevalence: number;
  defaultId: string;
}) {
  const [ref, w] = useWidth<HTMLDivElement>(420);
  const width = Math.max(260, w);
  const height = Math.min(360, Math.round(width * 0.8));
  const x = scaleLinear()
    .domain([0, 1])
    .range([M.left, width - M.right]);
  const y = scaleLinear()
    .domain([0, 1])
    .range([height - M.bottom, M.top]);
  const sorted = [...curve].sort((a, b) => a.recall - b.recall || b.precision - a.precision);
  const d = sorted
    .map((p, i) => `${i ? "L" : "M"}${x(p.recall).toFixed(1)},${y(p.precision).toFixed(1)}`)
    .join("");
  return (
    <div ref={ref} className="min-w-0 [contain:inline-size]">
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={`Precision-recall curve on the test block with ${points.length} operating points. No-skill precision is ${formatPercent(prevalence)}.`}
        className="block"
      >
        <Axes
          x={x}
          y={y}
          width={width}
          height={height}
          xLabel="Recall: failures caught"
          yLabel="Precision: alarms that were failures"
        />
        <line
          x1={x(0)}
          x2={x(1)}
          y1={y(prevalence)}
          y2={y(prevalence)}
          stroke="var(--ink-3)"
          strokeDasharray="5 4"
        />
        <text x={x(0) + 4} y={y(prevalence) - 5} className="tnum fill-ink-3 text-[11px]">
          No skill {formatPercent(prevalence)}
        </text>
        <path d={d} fill="none" stroke="var(--ink)" strokeWidth={1.5} strokeLinejoin="round" />
        {points.map((p) => (
          <g key={p.id}>
            <circle
              cx={x(p.recall.value)}
              cy={y(p.precision.value)}
              r={p.id === defaultId ? 5.5 : 4}
              fill={p.id === defaultId ? "var(--safelight)" : "var(--die)"}
              stroke="var(--ink)"
              strokeWidth={1.5}
            />
            <text
              x={x(p.recall.value) + 8}
              y={y(p.precision.value) - 8}
              className="fill-ink-2 text-[11px]"
            >
              {p.label}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

/** Observed failure rate against mean predicted risk per bin; dot area follows the units in the bin. */
export function ReliabilityDiagram({ bins }: { bins: ReliabilityBin[] }) {
  const [ref, w] = useWidth<HTMLDivElement>(420);
  const width = Math.max(260, w);
  const height = Math.min(360, Math.round(width * 0.8));
  const top = Math.max(0.05, ...bins.flatMap((b) => [b.mean_predicted, b.observed_rate]));
  const max = Math.min(
    1,
    scaleLinear()
      .domain([0, top * 1.1])
      .nice(4)
      .domain()[1]!,
  );
  const x = scaleLinear()
    .domain([0, max])
    .range([M.left, width - M.right]);
  const y = scaleLinear()
    .domain([0, max])
    .range([height - M.bottom, M.top]);
  const r = scaleSqrt()
    .domain([0, Math.max(1, ...bins.map((b) => b.units))])
    .range([0, 5.5]);
  const ticks = x.ticks(4);
  return (
    <div ref={ref} className="min-w-0 [contain:inline-size]">
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={`Reliability diagram with ${bins.length} bins of equal size.`}
        className="block"
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={M.left} x2={width - M.right} y1={y(t)} y2={y(t)} stroke="var(--hairline)" />
            <text
              x={M.left - 8}
              y={y(t)}
              dy="0.32em"
              textAnchor="end"
              className="tnum fill-ink-3 text-[11px]"
            >
              {formatPercent(t, 0)}
            </text>
            <text
              x={x(t)}
              y={height - M.bottom + 16}
              textAnchor="middle"
              className="tnum fill-ink-3 text-[11px]"
            >
              {formatPercent(t, 0)}
            </text>
          </g>
        ))}
        <text
          x={(M.left + width - M.right) / 2}
          y={height - 6}
          textAnchor="middle"
          className="fill-ink-2 text-[12px]"
        >
          Mean predicted risk in the bin
        </text>
        <text
          transform={`translate(12 ${(M.top + height - M.bottom) / 2}) rotate(-90)`}
          textAnchor="middle"
          className="fill-ink-2 text-[12px]"
        >
          Observed failure rate
        </text>
        <line
          x1={x(0)}
          y1={y(0)}
          x2={x(max)}
          y2={y(max)}
          stroke="var(--ink-3)"
          strokeDasharray="5 4"
        />
        <path
          d={bins
            .map(
              (b, i) =>
                `${i ? "L" : "M"}${x(b.mean_predicted).toFixed(1)},${y(b.observed_rate).toFixed(1)}`,
            )
            .join("")}
          fill="none"
          stroke="var(--ink-2)"
        />
        {bins.map((b) => (
          <circle
            key={b.bin}
            cx={x(b.mean_predicted)}
            cy={y(b.observed_rate)}
            r={Math.max(2.5, r(b.units))}
            fill="var(--ink)"
            fillOpacity={0.75}
          >
            <title>{`Bin ${b.bin + 1}: predicted ${formatPercent(b.mean_predicted)}, observed ${formatPercent(b.observed_rate)}, ${b.units} units`}</title>
          </circle>
        ))}
      </svg>
    </div>
  );
}

/** Confusion matrix, rows are true patterns; each cell is shaded by its share of the row, with the count. */
export function ConfusionMatrix({ matrix }: { matrix: Confusion }) {
  const [hover, setHover] = useState<[number, number] | null>(null);
  const n = matrix.labels.length;
  return (
    <ScrollRegion label="Confusion matrix">
      <table className="border-collapse text-[11px] leading-4" onMouseLeave={() => setHover(null)}>
        <caption className="sr-only">
          Confusion matrix: rows are true patterns, columns predicted patterns. Cells give counts.
        </caption>
        <thead>
          <tr>
            <th scope="col" className="p-1 text-left font-normal text-ink-3">
              True ↓ Predicted →
            </th>
            {matrix.labels.map((l, j) => (
              <th
                key={l}
                scope="col"
                className={cn(
                  "h-24 w-10 p-0 align-bottom font-normal",
                  hover?.[1] === j ? "text-ink" : "text-ink-3",
                )}
              >
                <span className="inline-block origin-bottom-left translate-x-5 -rotate-60 whitespace-nowrap">
                  {patternName(l as PatternLabel)}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.counts.map((row, i) => {
            const total = row.reduce((a, b) => a + b, 0) || 1;
            return (
              <tr key={matrix.labels[i]}>
                <th
                  scope="row"
                  className={cn(
                    "pr-2 text-right font-normal whitespace-nowrap",
                    hover?.[0] === i ? "text-ink" : "text-ink-2",
                  )}
                >
                  {patternName(matrix.labels[i] as PatternLabel)}
                </th>
                {row.map((c, j) => {
                  const share = c / total;
                  const diagonal = i === j;
                  return (
                    <td
                      key={j}
                      onMouseEnter={() => setHover([i, j])}
                      title={`True ${patternName(matrix.labels[i] as PatternLabel)}, predicted ${patternName(matrix.labels[j] as PatternLabel)}: ${formatInt(c)} (${formatPercent(share)} of the row)`}
                      className="tnum relative size-10 border border-die p-0 text-center"
                      style={{
                        // Cells with light text are pulled toward the ink so the count keeps 4.5:1.
                        background: c
                          ? share > 0.5
                            ? `color-mix(in oklab, color-mix(in oklab, ${diagonal ? "var(--pass)" : "var(--fail)"} ${Math.round(8 + share * 82)}%, var(--die-2)), var(--ink) 25%)`
                            : `color-mix(in oklab, ${diagonal ? "var(--pass)" : "var(--fail)"} ${Math.round(8 + share * 82)}%, var(--die-2))`
                          : "var(--die-2)",
                        color: share > 0.5 ? "var(--die)" : "var(--ink-2)",
                      }}
                    >
                      {c ? formatInt(c) : ""}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2 text-[12px] leading-4 text-ink-3">
        Shade is the share of the true pattern&rsquo;s wafers: blue on the diagonal (correct), red
        off it. {n} patterns.
      </p>
    </ScrollRegion>
  );
}

/** The time-ordered split of SECOM into train, validation and test blocks. */
export function BlocksBar({ blocks }: { blocks: BlockInfo[] }) {
  const total = blocks.reduce((a, b) => a + b.units, 0) || 1;
  const tone: Record<string, string> = {
    train: "bg-ink-3",
    validation: "bg-ink-2",
    test: "bg-ink",
  };
  return (
    <div>
      <div className="flex h-3 overflow-hidden rounded-[2px]" aria-hidden="true">
        {blocks.map((b) => (
          <div
            key={b.block}
            className={cn("h-full border-r-2 border-die last:border-r-0", tone[b.block])}
            style={{ width: `${(b.units / total) * 100}%` }}
          />
        ))}
      </div>
      <dl className="mt-2 grid grid-cols-[minmax(0,1fr)] gap-x-4 gap-y-2 sm:grid-cols-3">
        {blocks.map((b) => (
          <div key={b.block} className="min-w-0 text-[12px] leading-4">
            <dt className="font-medium text-ink capitalize">{b.block}</dt>
            <dd className="tnum text-ink-2">
              {formatInt(b.units)} units, {formatInt(b.failures)} failed (
              {formatPercent(b.failures / (b.units || 1))})
              <span className="block text-ink-3">
                {formatPlantTime(b.start).slice(0, 10)} to {formatPlantTime(b.end).slice(0, 10)}
              </span>
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
