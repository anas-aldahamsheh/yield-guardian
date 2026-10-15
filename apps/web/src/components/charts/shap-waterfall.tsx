import type { Explanation } from "@yield-guardian/contracts";
import { scaleLinear } from "d3";

import { formatReading, formatSigned } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Row {
  key: string;
  label: string;
  detail?: string;
  start: number;
  end: number;
  kind: "anchor" | "up" | "down";
}

/** Rows of the waterfall: base value, each listed contribution, the rest, the model output. */
export function waterfallRows(explanation: Explanation): Row[] {
  const rows: Row[] = [
    {
      key: "base",
      label: "Average unit",
      detail: "base value",
      start: 0,
      end: explanation.base_value,
      kind: "anchor",
    },
  ];
  let x = explanation.base_value;
  for (const c of explanation.contributions) {
    const label = c.kind === "missing_indicator" ? `${c.sensor} missing` : c.sensor;
    const detail =
      c.kind === "missing_indicator"
        ? c.value === 1
          ? "not measured"
          : "measured"
        : c.value == null
          ? "not measured"
          : formatReading(c.value);
    rows.push({
      key: c.feature,
      label,
      detail,
      start: x,
      end: x + c.shap,
      kind: c.shap >= 0 ? "up" : "down",
    });
    x += c.shap;
  }
  if (explanation.other_features > 0) {
    rows.push({
      key: "other",
      label: `${explanation.other_features} other features`,
      start: x,
      end: x + explanation.other_shap,
      kind: explanation.other_shap >= 0 ? "up" : "down",
    });
    x += explanation.other_shap;
  }
  rows.push({
    key: "out",
    label: "This unit",
    detail: "model output",
    start: 0,
    end: explanation.raw_score,
    kind: "anchor",
  });
  return rows;
}

/**
 * SHAP waterfall in log-odds: from the average unit, each feature moves the score up (towards
 * failure) or down, ending at this unit's model output. Exact for tree models.
 */
export function ShapWaterfall({
  explanation,
  className,
}: {
  explanation: Explanation;
  className?: string;
}) {
  const rows = waterfallRows(explanation);
  const values = rows.flatMap((r) => [r.start, r.end]);
  const scale = scaleLinear()
    .domain([Math.min(0, ...values), Math.max(0, ...values)])
    .nice(6);
  const pct = (v: number) =>
    `${(((v - scale.domain()[0]!) / (scale.domain()[1]! - scale.domain()[0]!)) * 100).toFixed(3)}%`;
  const ticks = scale.ticks(6);

  return (
    <figure className={cn("m-0 min-w-0", className)}>
      <div
        role="table"
        aria-label="SHAP contributions in log-odds"
        className="grid grid-cols-[minmax(6.5rem,auto)_minmax(0,1fr)_4.5rem] text-[13px] leading-5 sm:grid-cols-[minmax(7rem,auto)_6.5rem_minmax(0,1fr)_4.5rem]"
      >
        <div role="row" className="contents text-[12px] text-ink-3">
          <span role="columnheader" className="py-1.5 pr-3">
            Feature
          </span>
          <span role="columnheader" className="hidden py-1.5 pr-3 text-right sm:block">
            Reading
          </span>
          <span role="columnheader" className="py-1.5">
            <span className="sr-only">Bar</span>
          </span>
          <span role="columnheader" className="py-1.5 text-right">
            SHAP
          </span>
        </div>
        {rows.map((r) => {
          const lo = Math.min(r.start, r.end);
          const hi = Math.max(r.start, r.end);
          const anchor = r.kind === "anchor";
          return (
            <div role="row" key={r.key} className={cn("contents", anchor && "font-medium")}>
              <span
                role="rowheader"
                className={cn(
                  "tnum truncate border-t border-hairline py-1.5 pr-3",
                  anchor ? "text-ink" : "text-ink-2",
                )}
              >
                {r.label}
                {anchor && r.detail ? (
                  <span className="ml-1.5 font-normal text-ink-3">{r.detail}</span>
                ) : null}
              </span>
              <span
                role="cell"
                className="tnum hidden truncate border-t border-hairline py-1.5 pr-3 text-right text-ink-3 sm:block"
              >
                {anchor ? "" : r.detail}
              </span>
              <span role="cell" aria-hidden="true" className="relative border-t border-hairline">
                <span
                  className="absolute inset-y-0 w-px bg-hairline-strong"
                  style={{ left: pct(0) }}
                />
                <span
                  className={cn(
                    "absolute top-1/2 h-3 -translate-y-1/2 rounded-[2px]",
                    anchor ? "bg-ink-2" : r.kind === "up" ? "bg-fail" : "bg-pass",
                  )}
                  style={{ left: pct(lo), width: `max(2px, calc(${pct(hi)} - ${pct(lo)}))` }}
                />
              </span>
              <span
                role="cell"
                className={cn(
                  "tnum border-t border-hairline py-1.5 text-right",
                  anchor ? "text-ink" : "text-ink-2",
                )}
              >
                {anchor ? formatReading(r.end, 3) : formatSigned(r.end - r.start)}
              </span>
            </div>
          );
        })}
        <div aria-hidden="true" className="contents">
          <span />
          <span className="hidden sm:block" />
          <span className="relative h-6 border-t border-hairline-strong">
            {ticks.map((t) => (
              <span
                key={t}
                className="tnum absolute top-1 -translate-x-1/2 text-[11px] text-ink-3"
                style={{ left: pct(t) }}
              >
                {formatSigned(t, Number.isInteger(t) ? 0 : 1).replace(/^\+/, "")}
              </span>
            ))}
          </span>
          <span />
        </div>
      </div>
      <figcaption className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[12px] leading-4 text-ink-2">
        <span className="flex items-center gap-1.5">
          <span aria-hidden="true" className="h-2.5 w-4 rounded-[2px] bg-fail" /> Raises the failure
          score
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden="true" className="h-2.5 w-4 rounded-[2px] bg-pass" /> Lowers it
        </span>
        <span className="text-ink-3">Log-odds; 0 is even odds. {explanation.method}.</span>
      </figcaption>
    </figure>
  );
}
