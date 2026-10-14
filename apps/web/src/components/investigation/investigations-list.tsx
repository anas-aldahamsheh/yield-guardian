"use client";

import { LocalDateTime } from "@/components/local-date-time";
import { useQuery } from "@tanstack/react-query";
import type { InvestigationSummary } from "@yield-guardian/contracts";
import Link from "next/link";
import { useState } from "react";

import { PageFrame, PageHeader, Panel } from "@/components/page";
import { EmptyState, ErrorState, Placeholder } from "@/components/states";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useApi } from "@/lib/api/context";
import { NOT_CONFIGURED, useFeatures } from "@/lib/api/features";
import { q } from "@/lib/api/queries";
import { formatInt, formatNumber } from "@/lib/format";
import { TRIGGER_KIND } from "@/lib/labels";

import { StatusLabel } from "./status-label";
import { ScrollRegion } from "@/components/scroll-region";

type Status = InvestigationSummary["status"];
const FILTERS: { value: Status | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "awaiting_decision", label: "Awaiting decision" },
  { value: "running", label: "Running" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
  { value: "failed", label: "Failed" },
];

export function InvestigationsList() {
  const api = useApi();
  const [status, setStatus] = useState<Status | "all">("all");
  const query = useQuery(q.investigations(api, status === "all" ? {} : { status }));
  const { liveInvestigations } = useFeatures();

  return (
    <PageFrame>
      <PageHeader
        title="Investigations"
        description="Each one gathers evidence with data tools, writes a report whose numbers are checked, and waits for an engineer's decision."
      />
      {liveInvestigations === false ? <NotConfiguredNote /> : null}
      <Panel
        title="Runs"
        description={query.data ? `${formatInt(query.data.total)} in total, newest first.` : undefined}
        actions={
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            value={status}
            onValueChange={(v) => v && setStatus(v as Status | "all")}
            aria-label="Filter by status"
            className="flex-wrap"
          >
            {FILTERS.map((f) => (
              <ToggleGroupItem key={f.value} value={f.value} className="px-2.5">
                {f.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        }
        bodyClassName="px-0 sm:px-0"
      >
        {query.isError ? (
          <ErrorState className="mx-4 sm:mx-5" error={query.error} onRetry={() => void query.refetch()} />
        ) : !query.data ? (
          <Placeholder className="mx-4 h-48 sm:mx-5" label="Loading investigations" />
        ) : query.data.items.length === 0 ? (
          <EmptyState
            className="mx-4 sm:mx-5"
            title={status === "all" ? "No investigations yet" : "None with this status"}
            action={
              <Link href="/line" className="text-[14px] text-ink underline decoration-hairline-strong underline-offset-4">
                Open the line
              </Link>
            }
          >
            Start one from an open alarm on the line, or from a unit, wafer or lot.
          </EmptyState>
        ) : (
          <ScrollRegion label="Investigations">
            <table className="w-full min-w-[760px] border-collapse text-left text-[14px] leading-5">
              <caption className="sr-only">Investigations</caption>
              <thead>
                <tr className="border-y border-hairline text-[12px] text-ink-3">
                  <th scope="col" className="px-4 py-2 font-normal sm:px-5">Investigation</th>
                  <th scope="col" className="px-3 py-2 font-normal">Status</th>
                  <th scope="col" className="px-3 py-2 font-normal">From</th>
                  <th scope="col" className="px-3 py-2 font-normal">Started</th>
                  <th scope="col" className="px-3 py-2 text-right font-normal">Points</th>
                  <th scope="col" className="px-4 py-2 font-normal sm:px-5">Work order</th>
                </tr>
              </thead>
              <tbody>
                {query.data.items.map((inv) => (
                  <tr key={inv.investigation_id} className="border-b border-hairline last:border-b-0 hover:bg-die-2">
                    <th scope="row" className="px-4 py-2.5 font-normal sm:px-5">
                      <Link
                        href={`/investigations/${inv.investigation_id}`}
                        className="text-ink underline decoration-hairline-strong underline-offset-4 hover:decoration-ink"
                      >
                        {inv.title}
                      </Link>
                      {inv.recorded ? <span className="ml-2 text-[12px] text-ink-3">Recorded</span> : null}
                    </th>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <StatusLabel status={inv.status} />
                    </td>
                    <td className="tnum px-3 py-2.5 whitespace-nowrap text-ink-2">
                      {TRIGGER_KIND[inv.trigger.kind]} {inv.trigger.ref}
                    </td>
                    <td className="tnum px-3 py-2.5 whitespace-nowrap text-ink-2"><LocalDateTime iso={inv.created_at} /></td>
                    <td className="tnum px-3 py-2.5 text-right text-ink-2">{inv.usage ? formatNumber(inv.usage.points, 5) : "–"}</td>
                    <td className="tnum px-4 py-2.5 sm:px-5">
                      {inv.work_order_id ? (
                        <Link href={`/work-orders/${inv.work_order_id}`} className="text-ink underline decoration-hairline-strong underline-offset-4">
                          {inv.work_order_id}
                        </Link>
                      ) : (
                        <span className="text-ink-3">–</span>
                      )}
                    </td>
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

function NotConfiguredNote() {
  return (
    <div role="note" className="mb-6 rounded-md border border-hairline-strong bg-die px-4 py-3 sm:px-5">
      <p className="text-[14px] font-medium leading-5 text-ink">{NOT_CONFIGURED.investigations.title}</p>
      <p className="mt-1 text-[13px] leading-5 text-ink-2">{NOT_CONFIGURED.investigations.detail}</p>
    </div>
  );
}
