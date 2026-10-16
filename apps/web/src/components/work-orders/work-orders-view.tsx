"use client";

import { LocalDateTime } from "@/components/local-date-time";
import { useInfiniteQuery } from "@tanstack/react-query";
import type { WorkOrder } from "@yield-guardian/contracts";
import Link from "next/link";

import { Panel } from "@/components/page";
import { EmptyState, ErrorState, Placeholder } from "@/components/states";
import { Button } from "@/components/ui/button";
import { useApi } from "@/lib/api/context";
import { q } from "@/lib/api/queries";
import { formatInt } from "@/lib/format";
import { WORK_ORDER_STATUS } from "@/lib/labels";
import { workOrderHref, workOrdersHref } from "@/lib/routes";
import { cn } from "@/lib/utils";

import { AuditLog } from "./audit-log";
import { WorkOrderSection } from "./work-order-view";
import { ScrollRegion } from "@/components/scroll-region";

export function StatusMark({
  status,
  className,
}: {
  status: WorkOrder["status"];
  className?: string;
}) {
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

/**
 * The Work orders tab of Investigations: every work order, newest first, and the audit log.
 * `order` opens one work order above the list (where /work-orders/<id> lands when the order's
 * investigation could not be looked up).
 */
export function WorkOrdersTab({ order }: { order?: string | null }) {
  const api = useApi();
  const query = useInfiniteQuery(q.workOrderPages(api));
  const orders = query.data?.pages.flatMap((p) => p.items) ?? [];
  const total = query.data?.pages[0]?.total;

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-8">
      {order ? (
        <section
          aria-label={`Work order ${order}`}
          className="border-b border-hairline pb-8"
          id="work-order"
        >
          <div className="mb-3">
            <Link
              href={workOrdersHref()}
              scroll={false}
              className="text-[13px] text-ink-2 underline decoration-hairline-strong underline-offset-4 hover:text-ink"
            >
              Close this work order
            </Link>
          </div>
          <WorkOrderSection id={order} showInvestigation />
        </section>
      ) : null}
      <div className="grid grid-cols-[minmax(0,1fr)] gap-street xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <Panel
          title="Work orders"
          description={total != null ? `${formatInt(total)} in all, newest first.` : undefined}
          bodyClassName="px-0 sm:px-0"
        >
          {query.isError ? (
            <ErrorState
              className="mx-4 sm:mx-5"
              error={query.error}
              onRetry={() => void query.refetch()}
            />
          ) : !query.data ? (
            <Placeholder className="mx-4 h-48 sm:mx-5" label="Loading work orders" />
          ) : orders.length === 0 ? (
            <EmptyState className="mx-4 sm:mx-5" title="No work orders yet">
              A work order opens when an engineer approves actions in an{" "}
              <Link
                href="/investigations"
                className="underline decoration-hairline-strong underline-offset-4"
              >
                investigation report
              </Link>
              .
            </EmptyState>
          ) : (
            <ScrollRegion label="Work orders">
              <table className="w-full min-w-[640px] border-collapse text-left text-[14px] leading-5">
                <caption className="sr-only">Work orders</caption>
                <thead>
                  <tr className="border-y border-hairline text-[12px] text-ink-3">
                    <th scope="col" className="px-4 py-2 font-normal sm:px-5">
                      Work order
                    </th>
                    <th scope="col" className="px-2 py-2 font-normal">
                      Status
                    </th>
                    <th scope="col" className="px-2 py-2 font-normal">
                      Outcome
                    </th>
                    <th scope="col" className="px-4 py-2 text-right font-normal sm:px-5">
                      Updated
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((o) => (
                    <tr
                      key={o.work_order_id}
                      className="border-b border-hairline last:border-b-0 hover:bg-die-2"
                    >
                      <th scope="row" className="px-4 py-2.5 font-normal sm:px-5">
                        <Link
                          href={workOrderHref(o.work_order_id, o.investigation_id)}
                          className="tnum text-ink underline decoration-hairline-strong underline-offset-4"
                        >
                          {o.work_order_id}
                        </Link>
                        {o.example ? (
                          <span className="ml-2 text-[12px] text-ink-3">Example</span>
                        ) : null}
                        <span className="mt-0.5 block text-[13px] text-ink-2">{o.title}</span>
                        <span className="block text-[12px] text-ink-3">
                          {o.actions.length} {o.actions.length === 1 ? "action" : "actions"}, opened
                          by {o.created_by}
                        </span>
                      </th>
                      <td className="px-2 py-2.5 align-top text-ink-2">
                        <StatusMark status={o.status} />
                      </td>
                      <td className="px-2 py-2.5 align-top text-[13px] text-ink-2">
                        {o.outcome ? (
                          <>
                            <span className="line-clamp-2">{o.outcome}</span>
                            <span className="block text-[12px] text-ink-3">
                              {o.outcome_confirmed ? "Confirmed" : "Not confirmed"}
                            </span>
                          </>
                        ) : (
                          <span className="text-ink-3">Not recorded</span>
                        )}
                      </td>
                      <td className="tnum px-4 py-2.5 text-right align-top text-[13px] text-ink-3 sm:px-5">
                        <LocalDateTime iso={o.updated_at} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {query.hasNextPage ? (
                <div className="px-4 pt-3 sm:px-5">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void query.fetchNextPage()}
                    disabled={query.isFetchingNextPage}
                  >
                    {query.isFetchingNextPage ? "Loading…" : "Show more"}
                  </Button>
                </div>
              ) : null}
            </ScrollRegion>
          )}
        </Panel>
        <AuditLog />
      </div>
    </div>
  );
}
