"use client";

import { LocalDateTime } from "@/components/local-date-time";
import { useInfiniteQuery } from "@tanstack/react-query";
import type { AuditEntry } from "@yield-guardian/contracts";
import Link from "next/link";
import { useState } from "react";

import { Panel } from "@/components/page";
import { EmptyState, ErrorState, Placeholder } from "@/components/states";
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
          className="underline decoration-hairline-strong underline-offset-4"
        >
          {value}
        </Link>
      );
    if (/^WO-\d{6}$/.test(value))
      return (
        <Link
          href={workOrderHref(value)}
          className="underline decoration-hairline-strong underline-offset-4"
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
 * Every action taken in the product, newest first, from the API's audit log. With `targetId`,
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
            ? `Every action taken in the product, newest first. ${formatInt(total)} ${total === 1 ? "entry" : "entries"}.`
            : "Every action taken in the product, newest first."
      }
      actions={
        targetId ? null : (
          <Select value={action} onValueChange={(v) => setAction(v as Action | "all")}>
            <SelectTrigger size="sm" className="w-[220px]" aria-label="Action">
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
          className="mx-4 sm:mx-5"
          error={query.error}
          onRetry={() => void query.refetch()}
        />
      ) : !query.data ? (
        <Placeholder className="mx-4 h-40 sm:mx-5" label="Loading the audit log" />
      ) : entries.length === 0 ? (
        <EmptyState className="mx-4 sm:mx-5" title="Nothing recorded">
          {action === "all" ? "No action has been taken yet." : "No entry has this action."}
        </EmptyState>
      ) : (
        <>
          <ol className="border-t border-hairline">
            {entries.map((e) => {
              const href = targetHref(e.target_kind, e.target_id);
              const details = Object.entries(e.details ?? {});
              return (
                <li
                  key={e.audit_id}
                  className="grid grid-cols-[minmax(0,1fr)] gap-x-4 gap-y-0.5 border-b border-hairline px-4 py-2.5 last:border-b-0 sm:grid-cols-[9.5rem_minmax(0,1fr)] sm:px-5"
                >
                  <LocalDateTime iso={e.at} className="tnum text-[12px] leading-5 text-ink-3" />
                  <div className="min-w-0 text-[14px] leading-5">
                    <p className="text-ink">
                      <span
                        className={e.action === "session.login_failed" ? "text-fail" : undefined}
                      >
                        {AUDIT_ACTION[e.action] ?? e.action}
                      </span>{" "}
                      {href ? (
                        <Link
                          href={href}
                          className="tnum text-ink-2 underline decoration-hairline-strong underline-offset-4 hover:text-ink"
                        >
                          {e.target_id}
                        </Link>
                      ) : e.target_id ? (
                        <span className="tnum text-ink-2">{e.target_id}</span>
                      ) : null}
                    </p>
                    <p className="text-[12px] leading-4 text-ink-3">
                      {e.actor_name ? `${e.actor_name}, ` : ""}
                      {ACTOR_ROLE[e.actor_role] ?? e.actor_role}
                    </p>
                    {details.length ? (
                      <dl className="tnum mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-[12px] leading-4">
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
            <div className="px-4 pt-3 sm:px-5">
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
