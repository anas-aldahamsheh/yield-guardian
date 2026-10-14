"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import type { WorkOrder } from "@yield-guardian/contracts";
import Link from "next/link";

import { PageFrame, PageHeader, Panel } from "@/components/page";
import { EmptyState, ErrorState, Placeholder } from "@/components/states";
import { Button } from "@/components/ui/button";
import { unwrap } from "@/lib/api/client";
import { useApi } from "@/lib/api/context";
import { formatDateTime, formatInt } from "@/lib/format";
import { WORK_ORDER_STATUS } from "@/lib/labels";
import { cn } from "@/lib/utils";

import { AuditLog } from "./audit-log";

const PAGE = 50;

export function StatusMark({ status, className }: { status: WorkOrder["status"]; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap", className)}>
      <span
        aria-hidden="true"
        className={cn(
          "size-2 rounded-full",
          status === "open" && "bg-safelight",
          status === "in_progress" && "border-[1.5px] border-safelight",
          status === "done" && "bg-pass",
          status === "cancelled" && "bg-mark-muted",
        )}
      />
      {WORK_ORDER_STATUS[status] ?? status}
    </span>
  );
}

export function WorkOrdersView() {
  const api = useApi();
  const query = useInfiniteQuery({
    queryKey: ["work-orders", "list", "pages"],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      unwrap(api.GET("/api/v1/work-orders", { params: { query: { limit: PAGE, ...(pageParam ? { cursor: pageParam } : {}) } }, signal })),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const orders = query.data?.pages.flatMap((p) => p.items) ?? [];
  const total = query.data?.pages[0]?.total;

  return (
    <PageFrame>
      <PageHeader
        title="Work orders"
        description="Actions an engineer approved from an investigation report, and what was found when the work was done. Every change is in the audit log."
      />
      <div className="grid gap-street xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <Panel
          title="Work orders"
          description={total != null ? `${formatInt(total)} in all, newest first.` : undefined}
          bodyClassName="px-0 sm:px-0"
        >
          {query.isError ? (
            <ErrorState className="mx-4 sm:mx-5" error={query.error} onRetry={() => void query.refetch()} />
          ) : !query.data ? (
            <Placeholder className="mx-4 h-48 sm:mx-5" label="Loading work orders" />
          ) : orders.length === 0 ? (
            <EmptyState className="mx-4 sm:mx-5" title="No work orders yet">
              A work order opens when an engineer approves actions in an{" "}
              <Link href="/investigations" className="underline decoration-hairline-strong underline-offset-4">
                investigation report
              </Link>
              .
            </EmptyState>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] border-collapse text-left text-[14px] leading-5">
                <caption className="sr-only">Work orders</caption>
                <thead>
                  <tr className="border-y border-hairline text-[12px] text-ink-3">
                    <th scope="col" className="px-4 py-2 font-normal sm:px-5">Work order</th>
                    <th scope="col" className="px-2 py-2 font-normal">Status</th>
                    <th scope="col" className="px-2 py-2 font-normal">Outcome</th>
                    <th scope="col" className="px-4 py-2 text-right font-normal sm:px-5">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((o) => (
                    <tr key={o.work_order_id} className="border-b border-hairline last:border-b-0 hover:bg-die-2">
                      <th scope="row" className="px-4 py-2.5 font-normal sm:px-5">
                        <Link href={`/work-orders/${o.work_order_id}`} className="tnum text-ink underline decoration-hairline-strong underline-offset-4">
                          {o.work_order_id}
                        </Link>
                        <span className="mt-0.5 block text-[13px] text-ink-2">{o.title}</span>
                        <span className="block text-[12px] text-ink-3">
                          {o.actions.length} {o.actions.length === 1 ? "action" : "actions"}, opened by {o.created_by}
                        </span>
                      </th>
                      <td className="px-2 py-2.5 align-top text-ink-2">
                        <StatusMark status={o.status} />
                      </td>
                      <td className="px-2 py-2.5 align-top text-[13px] text-ink-2">
                        {o.outcome ? (
                          <>
                            <span className="line-clamp-2">{o.outcome}</span>
                            <span className="text-[12px] text-ink-3">{o.outcome_confirmed ? "Confirmed" : "Not confirmed"}</span>
                          </>
                        ) : (
                          <span className="text-ink-3">Not recorded</span>
                        )}
                      </td>
                      <td className="tnum px-4 py-2.5 text-right align-top text-[13px] text-ink-3 sm:px-5">
                        <time dateTime={o.updated_at} suppressHydrationWarning>
                          {formatDateTime(o.updated_at)}
                        </time>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {query.hasNextPage ? (
                <div className="px-4 pt-3 sm:px-5">
                  <Button variant="outline" size="sm" onClick={() => void query.fetchNextPage()} disabled={query.isFetchingNextPage}>
                    {query.isFetchingNextPage ? "Loading…" : "Show more"}
                  </Button>
                </div>
              ) : null}
            </div>
          )}
        </Panel>
        <AuditLog />
      </div>
    </PageFrame>
  );
}
