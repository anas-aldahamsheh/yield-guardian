import type { LineKpis as Kpis } from "@yield-guardian/contracts";

import { Ticker } from "@/components/motion";
import { formatInt } from "@/lib/format";
import { cn } from "@/lib/utils";

const roundInt = (v: number) => formatInt(Math.round(v));

/**
 * Counts over the units in the window, as the API defines them, read like an instrument: large
 * light figures that tick to their new value when a unit arrives. Marks carry the chart colours.
 */
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
      <dl className="grid grid-cols-2 gap-street sm:grid-cols-5">
        {items.map((item) => (
          <div key={item.label} className="panel min-w-0 px-4 pt-3 pb-3.5 last:col-span-2 sm:px-5 sm:last:col-span-1">
            <dt className="flex items-center gap-1.5 text-[13px] leading-5 text-ink-2">
              <span aria-hidden="true" className="size-2 shrink-0 rounded-full" style={{ background: item.mark }} />
              {item.label}
            </dt>
            <dd className="readout mt-1 text-[36px] leading-10 text-ink">
              <Ticker value={item.value} format={roundInt} />
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
