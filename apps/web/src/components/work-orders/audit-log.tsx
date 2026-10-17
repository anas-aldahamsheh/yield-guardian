"use client";

import { LocalDateTime } from "@/components/local-date-time";
import { useInfiniteQuery } from "@tanstack/react-query";
import type { AuditEntry } from "@yield-guardian/contracts";
import {
  ActivityIcon,
  CheckCircle2Icon,
  ClipboardCheckIcon,
  FileSearchIcon,
  LogInIcon,
  LogOutIcon,
  OctagonAlertIcon,
  RefreshCwIcon,
  ShieldAlertIcon,
  UserCheckIcon,
  WrenchIcon,
  XCircleIcon,
} from "lucide-react";
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

/** Formats audit target IDs into human-readable friendly labels */
function formatTargetLabel(kind: string, id: string): string {
  if (kind === "investigation") {
    // If it's a long inv_ hash, make it clean and readable
    return `Investigation ${id.length > 12 ? `${id.slice(0, 10)}…` : id}`;
  }
  if (kind === "work_order") {
    return id;
  }
  return id;
}

/** Returns action specific iconography and color styles */
function getActionMeta(action: string) {
  switch (action) {
    case "investigation.approved":
      return {
        icon: CheckCircle2Icon,
        color: "text-pass",
        bg: "bg-pass-wash border-pass/30",
        badge: "bg-pass/10 text-pass border-pass/20",
      };
    case "investigation.rejected":
      return {
        icon: XCircleIcon,
        color: "text-fail",
        bg: "bg-fail-wash border-fail/30",
        badge: "bg-fail/10 text-fail border-fail/20",
      };
    case "work_order.created":
      return {
        icon: ClipboardCheckIcon,
        color: "text-signal",
        bg: "bg-signal-wash border-signal/30",
        badge: "bg-signal/10 text-signal border-signal/20",
      };
    case "work_order.updated":
      return {
        icon: RefreshCwIcon,
        color: "text-signal",
        bg: "bg-signal-wash border-signal/30",
        badge: "bg-signal/10 text-signal border-signal/20",
      };
    case "investigation.created":
      return {
        icon: FileSearchIcon,
        color: "text-amber-500",
        bg: "bg-amber-500/10 border-amber-500/30",
        badge: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
      };
    case "investigation.stopped":
      return {
        icon: OctagonAlertIcon,
        color: "text-amber-500",
        bg: "bg-amber-500/10 border-amber-500/30",
        badge: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
      };
    case "session.login":
    case "session.guest":
      return {
        icon: UserCheckIcon,
        color: "text-ink",
        bg: "bg-surface-2 border-hairline",
        badge: "bg-surface-2 text-ink border-hairline",
      };
    case "session.login_failed":
      return {
        icon: ShieldAlertIcon,
        color: "text-fail",
        bg: "bg-fail-wash border-fail/30",
        badge: "bg-fail/10 text-fail border-fail/20",
      };
    case "session.logout":
    case "session.revoked":
      return {
        icon: LogOutIcon,
        color: "text-ink-3",
        bg: "bg-surface-2 border-hairline",
        badge: "bg-surface-2 text-ink-3 border-hairline",
      };
    default:
      return {
        icon: ActivityIcon,
        color: "text-ink-2",
        bg: "bg-surface-2 border-hairline",
        badge: "bg-surface-2 text-ink-2 border-hairline",
      };
  }
}

/** Formats a detail value cleanly with links */
function DetailPill({ label, value }: { label: string; value: unknown }) {
  if (value == null) return null;

  let display: React.ReactNode = String(value);

  if (typeof value === "string") {
    if (/^inv_[0-9a-z]+$/.test(value)) {
      display = (
        <Link
          href={investigationHref(value)}
          className="font-medium text-ink underline decoration-hairline-strong underline-offset-2 hover:decoration-ink"
        >
          {value.length > 14 ? `${value.slice(0, 10)}…` : value}
        </Link>
      );
    } else if (/^WO-\d{6}$/.test(value)) {
      display = (
        <Link
          href={workOrderHref(value)}
          className="font-semibold text-ink underline decoration-hairline-strong underline-offset-2 hover:decoration-ink"
        >
          {value}
        </Link>
      );
    }
  } else if (Array.isArray(value)) {
    display = (
      <span>
        {value.map((v) => (typeof v === "object" ? JSON.stringify(v) : String(v))).join(", ")}
      </span>
    );
  }

  const humanLabel = label.replaceAll("_", " ");

  return (
    <div className="inline-flex items-center gap-1.5 rounded-md border border-hairline bg-surface px-2 py-0.5 text-[12px] text-ink-2 shadow-2xs">
      <span className="text-ink-3 font-medium capitalize">{humanLabel}:</span>
      <span className="font-mono text-ink">{display}</span>
    </div>
  );
}

/**
 * Every action taken in this workspace, newest first, from the API's audit log.
 * Rendered as an organized activity timeline.
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
      title={targetId ? "Work Order History" : "Audit Log"}
      description={
        targetId
          ? "Chronological history of recorded actions on this work order."
          : total != null
            ? `Complete workspace activity stream (${formatInt(total)} entries).`
            : "Complete workspace activity stream, newest first."
      }
      actions={
        targetId ? null : (
          <Select value={action} onValueChange={(v) => setAction(v as Action | "all")}>
            <SelectTrigger size="sm" className="w-[200px] rounded-full" aria-label="Action Filter">
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
      bodyClassName="px-4 sm:px-6 py-4"
    >
      {query.isError ? (
        <div className="rounded-[16px] border border-amber-500/25 bg-amber-500/10 p-5 text-center">
          <div className="mx-auto flex size-10 items-center justify-center rounded-full bg-amber-500/15 text-amber-600 dark:text-amber-400">
            <RefreshCwIcon className="size-5" />
          </div>
          <h4 className="mt-3 text-[14px] font-[650] text-ink">
            Audit Stream Synchronizing
          </h4>
          <p className="mx-auto mt-1 max-w-[36ch] text-[12.5px] leading-relaxed text-ink-2">
            The remote telemetry backend was waking up from idle. Click retry to load the timeline.
          </p>
          <div className="mt-3.5">
            <Button
              size="sm"
              variant="outline"
              onClick={() => void query.refetch()}
              className="gap-1.5"
            >
              <RefreshCwIcon className="size-3.5" />
              Reconnect &amp; Refresh
            </Button>
          </div>
        </div>
      ) : !query.data ? (
        <Placeholder className="h-48" label="Loading the audit log" />
      ) : entries.length === 0 ? (
        <EmptyState
          className="unexposed border-solid bg-surface py-8"
          title="No recorded events"
        >
          {action === "all" ? "No activity recorded in this workspace yet." : "No events match the selected action."}
        </EmptyState>
      ) : (
        <div className="relative pl-6 sm:pl-8">
          {/* Continuous Timeline rail */}
          <div
            aria-hidden="true"
            className="absolute top-3 bottom-3 left-[15px] sm:left-[19px] w-px bg-hairline"
          />

          <ol className="space-y-4">
            {entries.map((e) => {
              const href = targetHref(e.target_kind, e.target_id);
              const meta = getActionMeta(e.action);
              const Icon = meta.icon;
              const details = Object.entries(e.details ?? {});

              return (
                <li key={e.audit_id} className="relative group/entry">
                  {/* Timeline icon node */}
                  <div
                    aria-hidden="true"
                    className={cn(
                      "absolute -left-[24px] sm:-left-[28px] top-1.5 flex size-5 sm:size-6 items-center justify-center rounded-full border bg-surface shadow-xs transition-colors duration-200",
                      meta.bg,
                    )}
                  >
                    <Icon className={cn("size-3 sm:size-3.5", meta.color)} />
                  </div>

                  {/* Entry Card Content */}
                  <div className="rounded-[14px] border border-hairline bg-surface-2/40 p-3 sm:p-4 transition-all duration-200 hover:border-hairline-strong hover:bg-surface-2 hover:shadow-2xs">
                    <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={cn(
                            "inline-flex items-center rounded-full border px-2.5 py-0.5 text-[12px] font-[600]",
                            meta.badge,
                          )}
                        >
                          {AUDIT_ACTION[e.action] ?? e.action}
                        </span>

                        {e.target_id ? (
                          href ? (
                            <Link
                              href={href}
                              className="font-mono text-[13px] font-[550] text-ink hover:underline"
                            >
                              {formatTargetLabel(e.target_kind, e.target_id)}
                            </Link>
                          ) : (
                            <span className="font-mono text-[13px] font-[550] text-ink">
                              {formatTargetLabel(e.target_kind, e.target_id)}
                            </span>
                          )
                        ) : null}

                        {e.example ? (
                          <Tag className="bg-surface-3 text-ink-2">Example</Tag>
                        ) : null}
                      </div>

                      <LocalDateTime
                        iso={e.at}
                        className="font-mono text-[11.5px] text-ink-3"
                      />
                    </div>

                    {/* Actor information */}
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-[12.5px] text-ink-2">
                      <span className="inline-flex items-center gap-1 font-[520] text-ink">
                        <UserCheckIcon className="size-3.5 text-ink-3" />
                        {e.actor_name || "Guest engineer"}
                      </span>
                      <span className="text-ink-3">·</span>
                      <span className="text-ink-3">
                        {ACTOR_ROLE[e.actor_role] ?? e.actor_role}
                      </span>
                    </div>

                    {/* Details badges */}
                    {details.length > 0 ? (
                      <div className="mt-2.5 flex flex-wrap items-center gap-1.5 border-t border-hairline/60 pt-2">
                        {details.map(([k, v]) => (
                          <DetailPill key={k} label={k} value={v} />
                        ))}
                      </div>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ol>

          {query.hasNextPage && !targetId ? (
            <div className="pt-4">
              <Button
                variant="outline"
                size="sm"
                onClick={() => void query.fetchNextPage()}
                disabled={query.isFetchingNextPage}
                className="w-full sm:w-auto"
              >
                {query.isFetchingNextPage ? "Loading more entries…" : "Show older entries"}
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </Panel>
  );
}
