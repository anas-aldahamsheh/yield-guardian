"use client";

import type { MeasuredResult } from "@yield-guardian/contracts";
import { useQuery } from "@tanstack/react-query";

import { IntervalAxis, IntervalBar } from "@/components/charts/estimate";
import { Placeholder, QueryView } from "@/components/states";
import { useApi } from "@/lib/api/context";
import { q } from "@/lib/api/queries";
import { ciLabel, formatDateTime, formatInt, formatInterval, formatMetric } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ScrollRegion } from "@/components/scroll-region";

const onUnitScale = (r: MeasuredResult) => r.format === "ratio" || r.format === "percent";

/**
 * The measured results: each claim with its value, its confidence interval and the data it was
 * measured on. Shares and ratios sit on one 0 to 1 axis so their uncertainty can be compared.
 */
export function ResultsLedger() {
  const api = useApi();
  const results = useQuery(q.results(api));

  return (
    <section aria-labelledby="results-title" className="mx-auto max-w-[1600px] px-gutter py-16">
      <div className="grid grid-cols-[minmax(0,1fr)] gap-x-12 gap-y-6 lg:grid-cols-[minmax(0,4fr)_minmax(0,8fr)]">
        <div>
          <h2 id="results-title" className="text-h2 font-semibold tracking-[-0.01em]">
            Results, with their uncertainty
          </h2>
          <p className="mt-3 max-w-[46ch] text-[15px] leading-6 text-ink-2">
            Each value comes with its confidence interval, the number of observations behind it
            and the data it was measured on. Model metrics come from data the models did not
            train on. A row without a value has not been measured yet.
          </p>
          {results.data?.updated_at ? (
            <p className="mt-3 text-[13px] text-ink-3">Updated {formatDateTime(results.data.updated_at)}</p>
          ) : null}
        </div>

        <QueryView query={results} loading={<Placeholder className="h-96" label="Loading results" />}>
          {(data) => (
            <ScrollRegion label="Measured results table" className="panel">
              <table className="w-full border-collapse text-left">
                <caption className="sr-only">Measured results with confidence intervals</caption>
                <thead>
                  <tr className="border-b border-hairline text-[13px] text-ink-3">
                    <th scope="col" className="px-4 py-2.5 font-normal sm:px-5">Result</th>
                    <th scope="col" className="px-3 py-2.5 text-right font-normal">Value</th>
                    <th scope="col" className="hidden w-[30%] px-3 py-2.5 font-normal md:table-cell">
                      <span className="sr-only">Interval on a 0 to 1 scale</span>
                      <IntervalAxis format={(v) => (v === 0 || v === 1 ? String(v) : v.toFixed(2))} />
                    </th>
                    <th scope="col" className="hidden px-4 py-2.5 text-right font-normal sm:table-cell sm:px-5">n</th>
                  </tr>
                </thead>
                <tbody>
                  {data.results.map((row) => (
                    <LedgerRow key={row.id} row={row} />
                  ))}
                </tbody>
              </table>
            </ScrollRegion>
          )}
        </QueryView>
      </div>
    </section>
  );
}

function LedgerRow({ row }: { row: MeasuredResult }) {
  const e = row.estimate;
  const interval = e ? formatInterval(e, row.format) : null;
  return (
    <tr className="border-b border-hairline align-top last:border-b-0">
      <th scope="row" className="px-4 py-3 text-left font-normal sm:px-5">
        <span className={cn("block text-[15px] leading-6", e ? "text-ink" : "text-ink-2")}>{row.label}</span>
        <span className="block text-[13px] leading-5 text-ink-3">{row.data}</span>
      </th>
      <td className="tnum px-3 py-3 text-right sm:whitespace-nowrap">
        {e ? (
          <>
            <span className="block text-[17px] leading-6 font-medium text-ink">{formatMetric(e.value, row.format)}</span>
            <span className="block text-[13px] leading-5 text-ink-3">
              {interval ? `${ciLabel(e)} ${interval}` : e.note ?? "no interval"}
            </span>
          </>
        ) : (
          <span className="block text-[15px] leading-6 text-ink-3">Not measured yet</span>
        )}
      </td>
      <td className="hidden px-3 py-3.5 md:table-cell">
        {e && onUnitScale(row) ? (
          <IntervalBar
            estimate={e}
            label={`${row.label}: ${formatMetric(e.value, row.format)}${interval ? `, ${ciLabel(e)} ${interval}` : ""}`}
          />
        ) : e ? (
          <span className="text-[13px] text-ink-3">Not a share; see the value</span>
        ) : null}
      </td>
      <td className="tnum hidden px-4 py-3 text-right text-[15px] leading-6 text-ink-2 sm:table-cell sm:px-5">
        {e?.n != null ? formatInt(e.n) : "–"}
      </td>
    </tr>
  );
}
