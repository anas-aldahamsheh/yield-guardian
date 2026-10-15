"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { PageFrame, PageHeader, Panel } from "@/components/page";
import { EmptyState, ErrorState, Placeholder } from "@/components/states";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useApi } from "@/lib/api/context";
import { q } from "@/lib/api/queries";
import { formatInt, formatPValue } from "@/lib/format";
import { type PatternLabel, patternName } from "@/lib/labels";
import { lotHref } from "@/lib/routes";
import { ScrollRegion } from "@/components/scroll-region";

export function LotsList() {
  const api = useApi();
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const query = useQuery(q.lots(api, flaggedOnly ? { flagged_only: true } : {}));
  return (
    <PageFrame>
      <PageHeader
        title="Lots"
        description="WM-811K lots, each tested for patterns that occur more often than in the training period (binomial test, Benjamini-Hochberg across lots)."
      />
      <Panel
        title="Lots"
        description={query.data ? `${formatInt(query.data.total)} lots` : undefined}
        actions={
          <div className="flex items-center gap-2">
            <Switch id="flagged-only" checked={flaggedOnly} onCheckedChange={setFlaggedOnly} />
            <Label htmlFor="flagged-only" className="text-[13px] text-ink-2">
              Only lots with a flagged pattern
            </Label>
          </div>
        }
        bodyClassName="px-0 sm:px-0"
      >
        {query.isError ? (
          <ErrorState className="mx-4 sm:mx-5" error={query.error} onRetry={() => void query.refetch()} />
        ) : !query.data ? (
          <Placeholder className="mx-4 h-48 sm:mx-5" label="Loading lots" />
        ) : query.data.items.length === 0 ? (
          <EmptyState className="mx-4 sm:mx-5" title={flaggedOnly ? "No lot has a flagged pattern" : "No lots"}>
            {flaggedOnly ? "Every pattern occurs at about its expected rate. Show all lots to browse them." : "The wafer bundle has no lots."}
          </EmptyState>
        ) : (
          <ScrollRegion label="Lots">
            <table className="w-full min-w-[560px] border-collapse text-left text-[14px] leading-5">
              <caption className="sr-only">Lots</caption>
              <thead>
                <tr className="border-y border-hairline text-[12px] text-ink-3">
                  <th scope="col" className="px-4 py-2 font-normal sm:px-5">Lot</th>
                  <th scope="col" className="px-3 py-2 text-right font-normal">Wafers</th>
                  <th scope="col" className="px-3 py-2 text-right font-normal">Labelled</th>
                  <th scope="col" className="px-3 py-2 font-normal">More than expected</th>
                  <th scope="col" className="px-4 py-2 text-right font-normal sm:px-5">Smallest q</th>
                </tr>
              </thead>
              <tbody>
                {query.data.items.map((l) => (
                  <tr key={l.lot} className="border-b border-hairline last:border-b-0 hover:bg-die-2">
                    <th scope="row" className="tnum px-4 py-2.5 font-normal sm:px-5">
                      <Link href={lotHref(l.lot)} className="text-ink underline decoration-hairline-strong underline-offset-4">
                        {l.lot}
                      </Link>
                    </th>
                    <td className="tnum px-3 py-2.5 text-right text-ink-2">{formatInt(l.wafers)}</td>
                    <td className="tnum px-3 py-2.5 text-right text-ink-2">{formatInt(l.labelled)}</td>
                    <td className="px-3 py-2.5">
                      {l.flagged_labels.length ? (
                        <span className="text-ink">{l.flagged_labels.map((x) => patternName(x as PatternLabel)).join(", ")}</span>
                      ) : (
                        <span className="text-ink-3">None</span>
                      )}
                    </td>
                    <td className="tnum px-4 py-2.5 text-right text-ink-2 sm:px-5">{l.min_q_value == null ? "not tested" : formatPValue(l.min_q_value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollRegion>
        )}
      </Panel>
    </PageFrame>
  );
}
