"use client";

import { LocalDateTime } from "@/components/local-date-time";
import { useInfiniteQuery } from "@tanstack/react-query";
import type { InvestigationSummary } from "@yield-guardian/contracts";
import Link from "next/link";
import { useState } from "react";

import { Panel } from "@/components/page";
import { ScrollRegion } from "@/components/scroll-region";
import { EmptyState, ErrorState, Placeholder } from "@/components/states";
import { Button } from "@/components/ui/button";
import { useApi } from "@/lib/api/context";
import { NOT_CONFIGURED, useFeatures } from "@/lib/api/features";
import { q } from "@/lib/api/queries";
import { LIVE_STATUSES } from "@/lib/investigation/events";
import { formatInt, formatNumber, plural } from "@/lib/format";
import { TRIGGER_KIND } from "@/lib/labels";
import { investigationHref, lineHref, workOrderHref } from "@/lib/routes";

import { Elapsed } from "./elapsed";
import { StatusLabel } from "./status-label";

type Status = InvestigationSummary["status"];
type GroupId = "running" | "awaiting" | "decided" | "failed";

const GROUPS: {
  id: GroupId;
  title: string;
  description: string;
  statuses: Status[];
  empty: string;
}[] = [
  {
    id: "running",
    title: "Running",
    description: "Gathering evidence or writing the report now, with the real elapsed time.",
    statuses: ["queued", "running"],
    empty: "Nothing is running.",
  },
  {
    id: "awaiting",
    title: "Awaiting decision",
    description: "A checked report is ready: an engineer approves actions or rejects it.",
    statuses: ["awaiting_decision"],
    empty: "No report is waiting for a decision.",
  },
  {
    id: "decided",
    title: "Decided",
    description: "Approved (with the work order it opened) or rejected.",
    statuses: ["approved", "rejected"],
    empty: "No report has been decided yet.",
  },
  {
    id: "failed",
    title: "Failed",
    description: "Runs that stopped before a report, with the reason on their page.",
    statuses: ["failed"],
    empty: "",
  },
];

/** While something runs, the list checks for new statuses every few seconds; otherwise it is still. */
const RUNNING_REFRESH_MS = 4000;

/**
 * The investigations, grouped by where they stand: running, awaiting a decision, decided.
 * Attempts to record a demo run that failed stay behind a button, so the runs people open come
 * first.
 */
export function InvestigationsIndex() {
  const api = useApi();
  const [showFailedRecordings, setShowFailedRecordings] = useState(false);
  const { liveInvestigations } = useFeatures();
  const query = useInfiniteQuery({
    ...q.investigationPages(api),
    refetchInterval: (state) =>
      state.state.data?.pages.some((p) => p.items.some((inv) => LIVE_STATUSES.has(inv.status)))
        ? RUNNING_REFRESH_MS
        : false,
  });

  const items = query.data?.pages.flatMap((p) => p.items) ?? [];
  const total = query.data?.pages[0]?.total;
  const failedRecordings = items.filter((inv) => inv.recorded && inv.status === "failed");
  const shown = showFailedRecordings
    ? items
    : items.filter((inv) => !(inv.recorded && inv.status === "failed"));

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-street">
      {liveInvestigations === false ? <NotConfiguredNote /> : null}
      {query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : !query.data ? (
        <Placeholder className="h-64" label="Loading investigations" />
      ) : items.length === 0 ? (
        <Panel>
          <EmptyState
            title="No investigations yet"
            action={
              <Link
                href={lineHref()}
                className="text-[14px] text-ink underline decoration-hairline-strong underline-offset-4"
              >
                Open the line
              </Link>
            }
          >
            Run a sample or your own data on the line, then choose Investigate on an alarm.
          </EmptyState>
        </Panel>
      ) : (
        <>
          {GROUPS.map((g) => {
            const rows = shown.filter((inv) => g.statuses.includes(inv.status));
            if (g.id === "failed" && rows.length === 0) return null;
            return <Group key={g.id} group={g} rows={rows} />;
          })}
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 px-1 pt-1 text-[13px] leading-5 text-ink-2">
            {total != null ? (
              <span className="tnum">
                {formatInt(items.length)} of {formatInt(total)} shown, newest first.
              </span>
            ) : null}
            {query.hasNextPage ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => void query.fetchNextPage()}
                disabled={query.isFetchingNextPage}
              >
                {query.isFetchingNextPage ? "Loading…" : "Show older investigations"}
              </Button>
            ) : null}
            {failedRecordings.length > 0 ? (
              <button
                type="button"
                aria-pressed={showFailedRecordings}
                onClick={() => setShowFailedRecordings((on) => !on)}
                className="inline-block min-h-6 cursor-pointer rounded-sm py-0.5 text-left underline decoration-hairline-strong underline-offset-4 hover:text-ink"
              >
                {showFailedRecordings
                  ? "Hide the failed recording attempts"
                  : `Show ${plural(failedRecordings.length, "failed recording attempt")}`}
              </button>
            ) : null}
          </div>
        </>
      )}
    </div>
  );
}

function Group({ group, rows }: { group: (typeof GROUPS)[number]; rows: InvestigationSummary[] }) {
  const titleId = `group-${group.id}`;
  return (
    <Panel
      aria-labelledby={titleId}
      data-group={group.id}
      title={
        <span id={titleId}>
          {group.title}{" "}
          <span className="tnum font-normal text-ink-3">{formatInt(rows.length)}</span>
        </span>
      }
      description={group.description}
      bodyClassName="px-0 sm:px-0"
    >
      {rows.length === 0 ? (
        <p className="px-4 pt-1 text-[14px] leading-5 text-ink-3 sm:px-5">{group.empty}</p>
      ) : (
        <ScrollRegion label={group.title}>
          <table className="w-full min-w-[760px] border-collapse text-left text-[14px] leading-5">
            <caption className="sr-only">{group.title}</caption>
            <thead>
              <tr className="border-y border-hairline text-[12px] text-ink-3">
                <th scope="col" className="px-4 py-2 font-normal sm:px-5">
                  Investigation
                </th>
                <th scope="col" className="px-3 py-2 font-normal">
                  Status
                </th>
                <th scope="col" className="px-3 py-2 font-normal">
                  From
                </th>
                <th scope="col" className="px-3 py-2 font-normal">
                  {group.id === "running" ? "Elapsed" : "Started"}
                </th>
                <th scope="col" className="px-3 py-2 text-right font-normal">
                  Points
                </th>
                <th scope="col" className="px-4 py-2 font-normal sm:px-5">
                  Work order
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((inv) => (
                <tr
                  key={inv.investigation_id}
                  className="border-b border-hairline last:border-b-0 hover:bg-die-2"
                >
                  <th scope="row" className="px-4 py-2.5 font-normal sm:px-5">
                    <Link
                      href={investigationHref(inv.investigation_id)}
                      className="text-ink underline decoration-hairline-strong underline-offset-4 hover:decoration-ink"
                    >
                      {inv.title}
                    </Link>
                    {inv.recorded ? (
                      <span className="ml-2 text-[12px] text-ink-3">Recorded</span>
                    ) : null}
                  </th>
                  <td className="px-3 py-2.5 whitespace-nowrap">
                    <StatusLabel status={inv.status} />
                  </td>
                  <td className="tnum px-3 py-2.5 whitespace-nowrap text-ink-2">
                    {TRIGGER_KIND[inv.trigger.kind] ?? inv.trigger.kind} {inv.trigger.ref}
                  </td>
                  <td className="tnum px-3 py-2.5 whitespace-nowrap text-ink-2">
                    {LIVE_STATUSES.has(inv.status) ? (
                      <Elapsed from={inv.created_at} running />
                    ) : (
                      <LocalDateTime iso={inv.created_at} />
                    )}
                  </td>
                  <td className="tnum px-3 py-2.5 text-right text-ink-2">
                    {inv.usage ? formatNumber(inv.usage.points, 5) : "–"}
                  </td>
                  <td className="tnum px-4 py-2.5 sm:px-5">
                    {inv.work_order_id ? (
                      <Link
                        href={workOrderHref(inv.work_order_id, inv.investigation_id)}
                        className="text-ink underline decoration-hairline-strong underline-offset-4"
                      >
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
  );
}

function NotConfiguredNote() {
  return (
    <div role="note" className="rounded-md border border-hairline-strong bg-die px-4 py-3 sm:px-5">
      <p className="text-[14px] leading-5 font-medium text-ink">
        {NOT_CONFIGURED.investigations.title}
      </p>
      <p className="mt-1 text-[13px] leading-5 text-ink-2">
        {NOT_CONFIGURED.investigations.detail}
      </p>
    </div>
  );
}
