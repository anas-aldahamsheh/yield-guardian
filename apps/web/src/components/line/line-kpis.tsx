import type { LineKpis as Kpis } from "@yield-guardian/contracts";

import { formatInt } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Counts over the units in the window, as the API defines them. Marks carry the chart colours. */
export function LineKpis({ kpis, className }: { kpis: Kpis; className?: string }) {
  const items: { label: string; value: number; mark?: string }[] = [
    { label: "Control-chart alarms", value: kpis.fdc_alarms, mark: "var(--fail)" },
    { label: "Control-chart warnings", value: kpis.fdc_warnings, mark: "var(--concern)" },
    { label: "Failed final test", value: kpis.failures_revealed, mark: "var(--fail)" },
    { label: "High risk, experimental", value: kpis.high_risk, mark: "var(--fail)" },
    { label: "Elevated risk, experimental", value: kpis.elevated_risk, mark: "var(--concern)" },
  ];
  return (
    <section aria-label={`Counts over the last ${kpis.window_units} units`} className={cn("min-w-0", className)}>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3 lg:grid-cols-5">
        {items.map((item) => (
          <div key={item.label} className="min-w-0 border-t border-hairline-strong pt-2.5">
            <dt className="flex items-center gap-1.5 text-[13px] leading-5 text-ink-2">
              <span aria-hidden="true" className="size-2 shrink-0 rounded-full" style={{ background: item.mark }} />
              {item.label}
            </dt>
            <dd className="tnum mt-0.5 text-[28px] leading-9 font-medium tracking-[-0.01em] text-ink">
              {formatInt(item.value)}
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 text-[13px] leading-5 text-ink-3">
        In the last {formatInt(kpis.window_units)} units off the line.
      </p>
    </section>
  );
}
