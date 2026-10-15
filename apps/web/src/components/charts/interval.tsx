import type { Estimate } from "@yield-guardian/contracts";

import {
  ciLabel,
  formatInterval,
  formatMetric,
  formatNumber,
  type MetricFormat,
} from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * A point estimate with its confidence interval on a fixed axis: a hairline track, the interval
 * as a bar and the estimate as a mark. Several in a column share the axis, so they compare.
 */
export function IntervalMark({
  estimate,
  domain = [0, 1],
  reference,
  className,
}: {
  estimate: Estimate;
  domain?: [number, number];
  /** A value to mark on the axis, such as a no-skill rate. */
  reference?: number | null;
  className?: string;
}) {
  const [d0, d1] = domain;
  const at = (v: number) => `${Math.min(100, Math.max(0, ((v - d0) / (d1 - d0 || 1)) * 100))}%`;
  const hasCi = estimate.ci_low != null && estimate.ci_high != null;
  return (
    <span aria-hidden="true" className={cn("relative block h-3.5 min-w-[80px]", className)}>
      <span className="absolute inset-x-0 top-1/2 h-px bg-hairline" />
      {reference != null ? (
        <span className="absolute top-0 h-full w-px bg-ink-3" style={{ left: at(reference) }} />
      ) : null}
      {hasCi ? (
        <span
          className="absolute top-1/2 h-[3px] -translate-y-1/2 rounded-full bg-ink-3/60"
          style={{
            left: at(estimate.ci_low!),
            width: `calc(${at(estimate.ci_high!)} - ${at(estimate.ci_low!)})`,
          }}
        />
      ) : null}
      {estimate.value != null ? (
        <span
          className="absolute top-1/2 size-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-ink"
          style={{ left: at(estimate.value) }}
        />
      ) : null}
    </span>
  );
}

/** "0.88, 95% CI 0.76–1.00 (n = 24)" as text. `digits` overrides the format for small values (Brier, ECE). */
export function EstimateText({
  estimate,
  format = "ratio",
  digits,
  showN = false,
}: {
  estimate: Estimate;
  format?: MetricFormat;
  digits?: number;
  showN?: boolean;
}) {
  const fmt = (v: number) => (digits != null ? formatNumber(v, digits) : formatMetric(v, format));
  const interval =
    digits != null
      ? estimate.ci_low != null && estimate.ci_high != null
        ? `${fmt(estimate.ci_low)}–${fmt(estimate.ci_high)}`
        : null
      : formatInterval(estimate, format);
  return (
    <span className="tnum">
      <span className="text-ink">
        {estimate.value == null ? "Not measured yet" : fmt(estimate.value)}
      </span>
      {interval ? (
        <span className="text-ink-3">
          {" "}
          {ciLabel(estimate)} {interval}
        </span>
      ) : null}
      {showN && estimate.n != null ? <span className="text-ink-3"> (n = {estimate.n})</span> : null}
    </span>
  );
}
