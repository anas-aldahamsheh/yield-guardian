"use client";

import { LocalDateTime } from "@/components/local-date-time";
import { useInfiniteQuery } from "@tanstack/react-query";
import type { AuditEntry } from "@yield-guardian/contracts";
import Link from "next/link";
import { useState } from "react";

import { Panel } from "@/components/page";
import { EmptyState, ErrorState, Placeholder } from "@/components/states";
import { Tag } from "@/components/tag";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useApi } from "@/lib/api/context";
import { unwrap } from "@/lib/api/client";
import { formatInt } from "@/lib/format";
import { ACTOR_ROLE, AUDIT_ACTION } from "@/lib/labels";
import { investigationHref, workOrderHref } from "@/lib/routes";
import { cn } from "@/lib/utils";

type Action = AuditEntry["action"];
const PAGE = 50;

/** Where an audited target lives in the product, when it has a page. */
export function targetHref(kind: string, id: string): string | null {
  if (kind === "investigation") return investigationHref(id);
  if (kind === "work_order") return workOrderHref(id);
  if (kind === "role") return "/admin";
  return null;
}

/** A detail value as text, with product IDs as links. */
function DetailValue({ value }: { value: unknown }) {
  if (typeof value === "string") {
    if (/^inv_[0-9a-z]+$/.test(value))
      return (
        <Link
          href={investigationHref(value)}
          className="text-ink underline decoration-hairline-strong underline-offset-4 transition-colors duration-(--dur-1) hover:decoration-ink"
        >
          {value}
        </Link>
      );
    if (/^WO-\d{6}$/.test(value))
      return (
        <Link
          href={workOrderHref(value)}
          className="text-ink underline decoration-hairline-strong underline-offset-4 transition-colors duration-(--dur-1) hover:decoration-ink"
        >
          {value}
        </Link>
      );
    return <>{value}</>;
  }
  if (value == null) return <span className="text-ink-3">none</span>;
  if (Array.isArray(value))
    return (
      <>{value.map((v) => (typeof v === "object" ? JSON.stringify(v) : String(v))).join(", ")}</>
    );
  if (typeof value === "object") return <>{JSON.stringify(value)}</>;
  return <>{String(value)}</>;
}

/**
 * Every action taken in this workspace, newest first, from the API's audit log (with those about
 * the recorded example, marked as such). With `targetId`,
 * only the entries about that target (filtered here; the API filters by action only).
 */
export function AuditLog({ targetId, className }: { targetId?: string; className?: string }) {
  const api = useApi();
  const [action, setAction] = useState<Action | "all">("all");
  const query = useInfiniteQuery({
    queryKey: ["audit", "pages", action, targetId ?? null],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      unwrap(
        api.GET("/api/v1/audit", {
          params: {
            query: {
              limit: targetId ? 200 : PAGE,
              ...(pageParam ? { cursor: pageParam } : {}),
              ...(action !== "all" ? { action } : {}),
            },
          },
          signal,
        }),
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const entries = (query.data?.pages.flatMap((p) => p.items) ?? []).filter(
    (e) => !targetId || e.target_id === targetId,
  );
  const total = query.data?.pages[0]?.total;

  return (
    <Panel
      title={targetId ? "History" : "Audit log"}
      description={
        targetId
          ? "Every recorded action on this work order, newest first."
          : total != null
            ? `Every action taken in this workspace, newest first. ${formatInt(total)} ${total === 1 ? "entry" : "entries"}.`
            : "Every action taken in this workspace, newest first."
      }
      actions={
        targetId ? null : (
          <Select value={action} onValueChange={(v) => setAction(v as Action | "all")}>
            <SelectTrigger size="sm" className="w-[220px] rounded-full" aria-label="Action">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All actions</SelectItem>
              {Object.entries(AUDIT_ACTION).map(([k, v]) => (
                <SelectItem key={k} value={k}>
                  {v}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )
      }
      className={className}
      bodyClassName="px-0 sm:px-0"
    >
      {query.isError ? (
        <ErrorState
          className="mx-5 sm:mx-6"
          error={query.error}
          onRetry={() => void query.refetch()}
        />
      ) : !query.data ? (
        <Placeholder className="mx-5 h-40 sm:mx-6" label="Loading the audit log" />
      ) : entries.length === 0 ? (
        <EmptyState
          className="unexposed mx-5 border-solid bg-surface sm:mx-6"
          title="Nothing recorded"
        >
          {action === "all" ? "No action has been taken yet." : "No entry has this action."}
        </EmptyState>
      ) : (
        <>
          <ol className="relative border-t border-hairline pt-2">
            {entries.map((e, i) => {
              const href = targetHref(e.target_kind, e.target_id);
              const details = Object.entries(e.details ?? {});
              const failed = e.action === "session.login_failed";
              return (
                <li
                  key={e.audit_id}
                  className="relative grid grid-cols-[minmax(0,1fr)] gap-x-5 gap-y-1 py-3 pr-5 pl-11 sm:grid-cols-[9.5rem_minmax(0,1fr)] sm:pr-6 sm:pl-12"
                >
                  {/* The rail runs from the first entry's dot to the last one's. First and last
                      come from the index: :first-child and :last-child in a variant would make
                      every node the parser adds restyle everything under the list. */}
                  <span
                    aria-hidden="true"
                    className={cn(
                      "absolute left-[23px] w-px bg-hairline sm:left-[27px]",
                      i === 0 ? "top-[18px]" : "top-0",
                      i === entries.length - 1 ? "bottom-[calc(100%-18px)]" : "bottom-0",
                    )}
                  />
                  <span
                    aria-hidden="true"
                    className={cn(
                      "absolute top-[15px] left-[20px] size-[7px] rounded-full shadow-[0_0_0_3px_var(--surface)] sm:left-[24px]",
                      failed ? "bg-fail" : i === 0 ? "bg-ink" : "bg-ink-3",
                    )}
                  />
                  <LocalDateTime iso={e.at} className="tnum text-[12.5px] leading-5 text-ink-3" />
                  <div className="min-w-0 text-[14px] leading-5">
                    <p className="text-ink">
                      <span className={cn("font-[560]", failed && "text-fail")}>
                        {AUDIT_ACTION[e.action] ?? e.action}
                      </span>{" "}
                      {href ? (
                        <Link
                          href={href}
                          className="tnum text-ink-2 underline decoration-hairline-strong underline-offset-4 transition-colors duration-(--dur-1) hover:text-ink hover:decoration-ink"
                        >
                          {e.target_id}
                        </Link>
                      ) : e.target_id ? (
                        <span className="tnum text-ink-2">{e.target_id}</span>
                      ) : null}
                      {e.example ? <Tag className="ml-2">Example</Tag> : null}
                    </p>
                    <p className="mt-0.5 text-[12.5px] leading-4 text-ink-3">
                      {e.actor_name ? `${e.actor_name}, ` : ""}
                      {ACTOR_ROLE[e.actor_role] ?? e.actor_role}
                    </p>
                    {details.length ? (
                      <dl className="tnum mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] leading-4">
                        {details.map(([k, v]) => (
                          <div key={k} className="flex min-w-0 gap-1">
                            <dt className="text-ink-3">{k.replaceAll("_", " ")}</dt>
                            <dd className="min-w-0 break-words text-ink-2">
                              <DetailValue value={v} />
                            </dd>
                          </div>
                        ))}
                      </dl>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ol>
          {query.hasNextPage && !targetId ? (
            <div className="px-5 pt-4 sm:px-6">
              <Button
                variant="outline"
                size="sm"
                onClick={() => void query.fetchNextPage()}
                disabled={query.isFetchingNextPage}
              >
                {query.isFetchingNextPage ? "Loading…" : "Show older entries"}
              </Button>
            </div>
          ) : null}
        </>
      )}
    </Panel>
  );
}
