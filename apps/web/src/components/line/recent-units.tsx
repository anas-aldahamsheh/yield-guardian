"use client";

import type { UnitSummary } from "@yield-guardian/contracts";
import Link from "next/link";
import { useState } from "react";

import { useNewIds } from "@/components/motion";
import { Panel } from "@/components/page";
import { Button } from "@/components/ui/button";
import { formatInt, formatPlantTime, formatProbability, formatReading } from "@/lib/format";
import { BAND_NAME } from "@/lib/labels";
import { unitHref } from "@/lib/routes";
import { cn } from "@/lib/utils";
import { ScrollRegion } from "@/components/scroll-region";

const SHOWN = 15;

const FDC_LABEL = { none: "Within limits", warning: "Beyond 99%", alarm: "Beyond 99.9%" } as const;

/** The units in the window as a table, newest first: the readable view of the charts. */
export function RecentUnits({ units, lag }: { units: UnitSummary[]; lag: number }) {
  const [all, setAll] = useState(false);
  const newestFirst = [...units].reverse();
  const shown = all ? newestFirst : newestFirst.slice(0, SHOWN);
  const fresh = useNewIds(units.map((u) => String(u.sequence)));

  return (
    <Panel
      title="Units off the line"
      description={`Newest first. Final-test results arrive ${lag} units after a unit leaves the line.`}
      bodyClassName="px-0 sm:px-0 pb-2"
    >
      <ScrollRegion label="Recent units">
        <table className="w-full min-w-[720px] border-collapse text-left text-[14px] leading-5">
          <caption className="sr-only">Recent units with failure risk, control-chart statistics and final test</caption>
          <thead>
            <tr className="border-y border-hairline text-[12px] text-ink-3">
              <th scope="col" className="px-4 py-2 font-normal sm:px-5">Unit</th>
              <th scope="col" className="px-3 py-2 font-normal">Plant time</th>
              <th scope="col" className="px-3 py-2 text-right font-normal">Risk, experimental</th>
              <th scope="col" className="px-3 py-2 font-normal">Band</th>
              <th scope="col" className="px-3 py-2 text-right font-normal">T²</th>
              <th scope="col" className="px-3 py-2 text-right font-normal">SPE</th>
              <th scope="col" className="px-3 py-2 font-normal">Control charts</th>
              <th scope="col" className="px-4 py-2 font-normal sm:px-5">Final test</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((u) => (
              <tr
                key={u.sequence}
                className={cn(
                  "border-b border-hairline last:border-b-0 hover:bg-die-2",
                  fresh.has(String(u.sequence)) && (u.fdc_alarm === "alarm" || u.risk_band === "high" ? "flash-alarm" : "flash-new"),
                )}
              >
                <th scope="row" className="tnum px-4 py-2 font-normal sm:px-5">
                  <Link href={unitHref(u.unit_id)} className="text-ink underline decoration-hairline-strong underline-offset-4 hover:decoration-ink">
                    {formatInt(u.unit_id)}
                  </Link>
                </th>
                <td className="tnum px-3 py-2 whitespace-nowrap text-ink-2">{formatPlantTime(u.timestamp)}</td>
                <td className="tnum px-3 py-2 text-right text-ink">{u.risk == null ? <span className="text-ink-3">Warm-up</span> : formatProbability(u.risk)}</td>
                <td className="px-3 py-2">
                  {u.risk_band ? (
                    <span className="inline-flex items-center gap-1.5 text-ink-2">
                      <span
                        aria-hidden="true"
                        className={cn(
                          "size-2 rounded-full",
                          u.risk_band === "high" ? "bg-fail" : u.risk_band === "elevated" ? "bg-concern" : "bg-mark-muted",
                        )}
                      />
                      {BAND_NAME[u.risk_band]}
                    </span>
                  ) : (
                    <span className="text-ink-3">–</span>
                  )}
                </td>
                <td className="tnum px-3 py-2 text-right text-ink-2">{formatReading(u.t2)}</td>
                <td className="tnum px-3 py-2 text-right text-ink-2">{formatReading(u.spe)}</td>
                <td className={cn("px-3 py-2", u.fdc_alarm === "alarm" ? "text-fail" : u.fdc_alarm === "warning" ? "text-ink" : "text-ink-3")}>
                  {FDC_LABEL[u.fdc_alarm]}
                  {u.ewma_alarm || u.cusum_alarm ? (
                    <span className="ml-1.5 text-[12px] text-ink-3">
                      {[u.ewma_alarm && "EWMA", u.cusum_alarm && "CUSUM"].filter(Boolean).join(", ")} drift
                    </span>
                  ) : null}
                </td>
                <td className="px-4 py-2 sm:px-5">
                  {u.final_test === "fail" ? (
                    <span className="font-medium text-fail">Fail</span>
                  ) : u.final_test === "pass" ? (
                    <span className="text-pass">Pass</span>
                  ) : (
                    <span className="text-ink-3">Pending</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </ScrollRegion>
      {units.length > SHOWN ? (
        <div className="border-t border-hairline px-4 pt-2 sm:px-5">
          <Button variant="ghost" size="sm" onClick={() => setAll((v) => !v)} className="-ml-2">
            {all ? "Show fewer" : `Show all ${formatInt(units.length)}`}
          </Button>
        </div>
      ) : null}
    </Panel>
  );
}
