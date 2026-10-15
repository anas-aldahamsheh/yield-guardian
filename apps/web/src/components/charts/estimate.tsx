import type { Estimate } from "@yield-guardian/contracts";

import { ciLabel, formatInt, formatInterval, formatMetric, type MetricFormat } from "@/lib/format";
import { cn } from "@/lib/utils";

/** "0.21 (95% CI 0.12–0.30, n = 307)". A missing interval says why instead of hiding. */
export function EstimateText({
  estimate,
  format = "ratio",
  showN = true,
  className,
}: {
  estimate: Estimate;
  format?: MetricFormat;
  showN?: boolean;
  className?: string;
}) {
  const interval = formatInterval(estimate, format);
  return (
    <span className={cn("tnum", className)}>
      <span className="text-ink">{formatMetric(estimate.value, format)}</span>
      <span className="text-ink-3">
        {" "}
        ({interval ? `${ciLabel(estimate)} ${interval}` : "no interval"}
        {showN && estimate.n != null ? `, n = ${formatInt(estimate.n)}` : ""})
      </span>
    </span>
  );
}

/**
 * A point estimate with its confidence interval on a linear axis. Several bars that share a
 * domain can be compared down a column.
 */
export function IntervalBar({
  estimate,
  domain = [0, 1],
  className,
  label,
}: {
  estimate: Estimate;
  domain?: [number, number];
  className?: string;
  label?: string;
}) {
  const [d0, d1] = domain;
  const x = (v: number) => `${(Math.min(Math.max((v - d0) / (d1 - d0), 0), 1) * 100).toFixed(2)}%`;
  const lo = estimate.ci_low;
  const hi = estimate.ci_high;
  return (
    <svg
      className={cn("block h-4 w-full overflow-visible", className)}
      role="img"
      aria-label={label}
      preserveAspectRatio="none"
    >
      <line x1="0" x2="100%" y1="8" y2="8" stroke="var(--hairline)" strokeWidth="1" />
      {lo != null && hi != null ? (
        <>
          <line
            x1={x(lo)}
            x2={x(hi)}
            y1="8"
            y2="8"
            stroke="var(--ink-2)"
            strokeWidth="2"
            strokeLinecap="round"
          />
          <line x1={x(lo)} x2={x(lo)} y1="4.5" y2="11.5" stroke="var(--ink-2)" strokeWidth="1.5" />
          <line x1={x(hi)} x2={x(hi)} y1="4.5" y2="11.5" stroke="var(--ink-2)" strokeWidth="1.5" />
        </>
      ) : null}
      <circle
        cx={x(estimate.value)}
        cy="8"
        r="4"
        fill="var(--ink)"
        stroke="var(--die)"
        strokeWidth="2"
      />
    </svg>
  );
}

/** Tick labels for a column of interval bars. */
export function IntervalAxis({
  ticks = [0, 0.25, 0.5, 0.75, 1],
  domain = [0, 1],
  format = (v: number) => String(v),
  className,
}: {
  ticks?: number[];
  domain?: [number, number];
  format?: (v: number) => string;
  className?: string;
}) {
  const [d0, d1] = domain;
  return (
    <div
      className={cn("relative h-4 text-[12px] leading-4 text-ink-3", className)}
      aria-hidden="true"
    >
      {ticks.map((t, i) => (
        <span
          key={t}
          className={cn(
            "tnum absolute top-0",
            i === 0
              ? "translate-x-0"
              : i === ticks.length - 1
                ? "-translate-x-full"
                : "-translate-x-1/2",
          )}
          style={{ left: `${((t - d0) / (d1 - d0)) * 100}%` }}
        >
          {format(t)}
        </span>
      ))}
    </div>
  );
}
