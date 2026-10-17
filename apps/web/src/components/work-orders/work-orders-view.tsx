"use client";

import { LocalDateTime } from "@/components/local-date-time";
import { useInfiniteQuery } from "@tanstack/react-query";
import type { WorkOrder } from "@yield-guardian/contracts";
import { ClockIcon, XIcon } from "lucide-react";
import Link from "next/link";

import { useEntrance } from "@/components/motion/entrance";
import { Panel } from "@/components/page";
import { EmptyState, ErrorState, Placeholder } from "@/components/states";
import { Tag } from "@/components/tag";
import { Button } from "@/components/ui/button";
import { useApi } from "@/lib/api/context";
import { q } from "@/lib/api/queries";
import { formatInt } from "@/lib/format";
import { useUpdateWorkOrder } from "@/lib/api/work-orders";
import { WORK_ORDER_STATUS } from "@/lib/labels";
import { workOrderHref, workOrdersHref } from "@/lib/routes";
import { cn } from "@/lib/utils";

import { AuditLog } from "./audit-log";
import { WorkOrderSection } from "./work-order-view";
import { ScrollRegion } from "@/components/scroll-region";

/**
 * A work order's status as a word on a chip, with a dot that repeats it: an open ring while it is
 * open, the signal while in progress, pass when done, grey when cancelled.
 */
export function StatusMark({
  status,
  className,
}: {
  status: WorkOrder["status"];
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-[12.5px] leading-4 font-[560] whitespace-nowrap text-ink",
        (status === "open" || status === "in_progress") && "bg-signal-wash",
        status === "done" && "bg-pass-wash",
        status === "cancelled" && "bg-surface-2 text-ink-2",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "size-1.5 shrink-0 rounded-full",
          status === "open" && "shadow-[inset_0_0_0_1.5px_var(--signal)]",
          status === "in_progress" && "bg-signal",
          status === "done" && "bg-pass",
          status === "cancelled" && "bg-mark-muted",
        )}
      />
      {WORK_ORDER_STATUS[status] ?? status}
    </span>
  );
}

/**
 * One work order opened above the list. It grows in when opened from the list; a page that
 * opens on it has it in place.
 */
function OpenOrder({ order }: { order: string }) {
  const entrance = useEntrance();
  return (
    <section
      aria-label={`Work order ${order}`}
      className={cn(
        entrance && "grow-in",
        "scroll-mt-[calc(var(--bar-height)+24px)] border-b border-hairline pb-10",
      )}
      id="work-order"
    >
      <div className="mb-4">
        <Link
          href={workOrdersHref()}
          scroll={false}
          className="press inline-flex h-8 items-center gap-1.5 rounded-full px-3.5 text-[13px] font-[560] text-ink-2 no-underline shadow-[inset_0_0_0_1px_var(--hairline-strong)] hover:bg-surface-2 hover:text-ink"
        >
          <XIcon className="size-3.5" strokeWidth={2} aria-hidden />
          Close this work order
        </Link>
      </div>
      <WorkOrderSection id={order} showInvestigation />
    </section>
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
      {order ? <OpenOrder key={order} order={order} /> : null}
      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-5 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <Panel
          title="Work orders"
          description={total != null ? `${formatInt(total)} in all, newest first.` : undefined}
          bodyClassName="px-0 sm:px-0"
        >
          {query.isError ? (
            <ErrorState
              className="mx-5 sm:mx-6"
              error={query.error}
              onRetry={() => void query.refetch()}
            />
          ) : !query.data ? (
            <Placeholder className="mx-5 h-48 sm:mx-6" label="Loading work orders" />
          ) : orders.length === 0 ? (
            <EmptyState
              className="unexposed mx-5 border-solid bg-surface sm:mx-6"
              title="No work orders yet"
            >
              A work order opens when an engineer approves actions in an{" "}
              <Link
                href="/investigations"
                className="text-ink underline decoration-hairline-strong underline-offset-4 transition-colors duration-(--dur-1) hover:decoration-ink"
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
                  <tr className="border-y border-hairline text-[12.5px] leading-4 text-ink-3">
                    <th scope="col" className="py-3 pr-3 pl-5 font-[520] sm:pl-6">
                      Work order
                    </th>
                    <th scope="col" className="px-3 py-3 font-[520]">
                      Status
                    </th>
                    <th scope="col" className="px-3 py-3 font-[520]">
                      Outcome
                    </th>
                    <th scope="col" className="py-3 pr-5 pl-3 text-right font-[520] sm:pr-6">
                      Updated
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((o) => (
                    <tr
                      key={o.work_order_id}
                      aria-current={o.work_order_id === order ? "true" : undefined}
                      className="group/row border-b border-hairline transition-colors duration-(--dur-1) last:border-b-0 hover:bg-surface-2 aria-[current]:bg-signal-wash aria-[current]:shadow-[inset_3px_0_0_var(--signal)]"
                    >
                      <th scope="row" className="py-3.5 pr-3 pl-5 align-top font-[420] sm:pl-6">
                        <Link
                          href={workOrderHref(o.work_order_id, o.investigation_id)}
                          className="tnum text-[15px] leading-[22px] font-[600] text-ink no-underline decoration-ink underline-offset-4 group-hover/row:underline focus-visible:underline"
                        >
                          {o.work_order_id}
                        </Link>
                        {o.example ? (
                          <Tag className="ml-2 group-hover/row:bg-surface-3">Example</Tag>
                        ) : null}
                        <span className="mt-0.5 block text-[13.5px] leading-5 text-ink-2">
                          {o.title}
                        </span>
                        <span className="mt-0.5 block text-[12.5px] leading-4 text-ink-3">
                          {o.actions.length} {o.actions.length === 1 ? "action" : "actions"}, opened
                          by {o.created_by}
                        </span>
                      </th>
                      <td className="px-3 py-3.5 align-top text-ink-2">
                        {o.example ? <StatusMark status={o.status} /> : <StatusSelect order={o} />}
                      </td>
                      <td className="px-3 py-3.5 align-top text-[13.5px] leading-5 text-ink-2">
                        {o.outcome ? (
                          <>
                            <span className="line-clamp-2">{o.outcome}</span>
                            <span className="mt-0.5 block text-[12.5px] leading-4 text-ink-3">
                              {o.outcome_confirmed ? "Confirmed" : "Not confirmed"}
                            </span>
                          </>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 rounded-full border border-hairline bg-surface-2/80 px-2.5 py-0.5 text-[12px] font-medium text-ink-3">
                            <ClockIcon className="size-3 text-ink-3" />
                            Pending confirmation
                          </span>
                        )}
                      </td>
                      <td className="tnum py-3.5 pr-5 pl-3 text-right align-top text-[13px] leading-5 text-ink-3 sm:pr-6">
                        <LocalDateTime iso={o.updated_at} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {query.hasNextPage ? (
                <div className="px-5 pt-4 sm:px-6">
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

/** The status of one work order, changed in place: the chip opens the list of statuses. */
function StatusSelect({ order }: { order: WorkOrder }) {
  const update = useUpdateWorkOrder(order.work_order_id);
  const shown = update.isPending && update.variables?.status ? update.variables.status : order.status;
  return (
    <label className="relative inline-flex cursor-pointer items-center gap-1 rounded-full focus-within:ring-2 focus-within:ring-[var(--signal)]">
      <span className="sr-only">Status of {order.work_order_id}</span>
      <StatusMark status={shown} />
      <span aria-hidden="true" className="text-[11px] text-ink-3">
        {update.isPending ? "…" : "▾"}
      </span>
      <select
        value={shown}
        disabled={update.isPending}
        onChange={(e) => update.mutate({ status: e.target.value as WorkOrder["status"] })}
        className="absolute inset-0 cursor-pointer opacity-0"
      >
        {Object.entries(WORK_ORDER_STATUS).map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
    </label>
  );
}
