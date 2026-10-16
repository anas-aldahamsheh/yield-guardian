"use client";

import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import type { WorkRun, WorkRunPage } from "@yield-guardian/contracts";
import { MoreHorizontal } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useState } from "react";

import { LocalDateTime } from "@/components/local-date-time";
import { ScrollRegion } from "@/components/scroll-region";
import { EmptyState, ErrorState, Placeholder } from "@/components/states";
import { Button } from "@/components/ui/button";
import { useApi } from "@/lib/api/context";
import { useSession } from "@/lib/api/session";
import { isLive, openWorkspace, useRunAgain, useUpdateWorkRun, wq } from "@/lib/api/workspace";
import { plural } from "@/lib/format";
import { INVESTIGATION_STATUS } from "@/lib/labels";
import { lineQuery, type LineUrlState } from "@/lib/live/url-state";
import { investigationHref } from "@/lib/routes";
import { cn } from "@/lib/utils";

import {
  endedSince,
  primaryOf,
  runName,
  runStatus,
  statusDot,
  viewOf,
  type Statuses,
} from "./work-model";
import type { RunActions } from "./your-work-menus";

/*
 * The menus (Radix and its positioning code) and the dialogs load when first pressed, as the top
 * bar's menus do: the Line page's first paint carries neither.
 */
const loadMenus = () => import("./your-work-menus");
const loadDialogs = () => import("./your-work-dialogs");
const RunMenu = dynamic(() => loadMenus().then((m) => m.RunMenu), {
  ssr: false,
  loading: () => (
    <Button
      size="icon-xs"
      variant="ghost"
      aria-label="More actions"
      disabled
      className="-mt-0.5 -mr-1"
    >
      <MoreHorizontal aria-hidden="true" />
    </Button>
  ),
});
const WorkspaceMenu = dynamic(() => loadMenus().then((m) => m.WorkspaceMenu), {
  ssr: false,
  loading: () => (
    <Button size="icon-sm" variant="ghost" aria-label="Workspace options" disabled>
      <MoreHorizontal aria-hidden="true" />
    </Button>
  ),
});
const RenameDialog = dynamic(() => loadDialogs().then((m) => m.RenameDialog), { ssr: false });
const CompareDialog = dynamic(() => loadDialogs().then((m) => m.CompareDialog), { ssr: false });
const HandoffDialog = dynamic(() => loadDialogs().then((m) => m.HandoffDialog), { ssr: false });
const FreshDialog = dynamic(() => loadDialogs().then((m) => m.FreshDialog), { ssr: false });

/** Every card and the strip's placeholders take this height, so nothing moves when runs arrive. */
const CARD_HEIGHT = "min-h-[11.5rem]";
const LIVE_EVERY_MS = 2_000;
const IDLE_EVERY_MS = 20_000;

type Dialog =
  | { kind: "rename"; run: WorkRun }
  | { kind: "compare"; run: WorkRun }
  | { kind: "handoff" }
  | { kind: "fresh" }
  | null;

/**
 * Your work, on the Line page: this workspace's runs, newest first, each with its live status
 * (runs go on computing on the server whatever is on screen), the investigations started from
 * its alarms and what it still needs. One press reopens a run where it was left; the view is
 * saved as it changes. The rest of a run's actions are in its menu. "Continue on another device"
 * attaches a phone or another computer to the same workspace.
 */
export function YourWork({
  current,
  onOpen,
}: {
  /** What the Line page shows now. */
  current: LineUrlState;
  /**
   * Shows a run on the Line page, at a station and item; once it is on the line the focus goes to
   * the run, or to its alarms (`to`).
   */
  onOpen: (view: LineUrlState, to?: "run" | "alarms") => void;
}) {
  const api = useApi();
  const client = useQueryClient();
  const { session } = useSession();
  const [archived, setArchived] = useState(false);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [menusLoaded, setMenusLoaded] = useState<string | null>(null);
  const workspace = session.workspace ?? null;
  // The API keeps no workspaces (no database), or did not answer when the page opened.
  const [unavailable, setUnavailable] = useState(false);
  useEffect(() => {
    let mounted = true;
    void openWorkspace().then((opened) => {
      if (mounted && !opened) setUnavailable(true);
    });
    return () => {
      mounted = false;
    };
  }, []);

  const runs = useInfiniteQuery({
    ...wq.runs(api, archived),
    enabled: workspace != null,
    refetchOnWindowFocus: true,
    refetchInterval: (query) =>
      query.state.data?.pages.some((page: WorkRunPage) => page.items.some(isLive))
        ? LIVE_EVERY_MS
        : IDLE_EVERY_MS,
  });
  const summary = useQuery({
    ...wq.summary(api),
    enabled: workspace != null,
    refetchOnWindowFocus: true,
  });
  const items = runs.data?.pages.flatMap((page) => page.items) ?? [];
  const total = runs.data?.pages[0]?.total ?? 0;

  // Runs that end while another is on the line are announced once.
  const [statuses, setStatuses] = useState<{
    data: typeof runs.data;
    seen: Statuses | null;
    said: string;
  }>({ data: undefined, seen: null, said: "" });
  if (runs.data !== statuses.data) {
    const said = statuses.seen ? endedSince(statuses.seen, items, current.runId) : "";
    setStatuses({
      data: runs.data,
      seen: new Map(items.map((run) => [run.run_id, run.status])),
      said: said || statuses.said,
    });
  }

  // A run started on this page joins the list at once.
  const onLine = current.runId;
  const listed = onLine != null && items.some((run) => run.run_id === onLine);
  useEffect(() => {
    if (onLine && !listed && !archived)
      void client.invalidateQueries({ queryKey: ["workspace", "runs", false] });
  }, [client, onLine, listed, archived]);

  // The view on the line is saved with its run, so the run reopens where it was left.
  const save = useUpdateWorkRun({ quiet: true }).mutate;
  const view = onLine ? lineQuery(current) : "";
  const shown = items.find((run) => run.run_id === onLine);
  const savedView = shown?.view ?? null;
  const ownRun = shown != null && !shown.archived;
  useEffect(() => {
    if (!onLine || !ownRun || !view || savedView === view) return;
    const timer = window.setTimeout(() => save({ runId: onLine, body: { view } }), 800);
    return () => window.clearTimeout(timer);
  }, [onLine, ownRun, view, savedView, save]);

  const update = useUpdateWorkRun();
  const again = useRunAgain();

  const actions: RunActions = {
    open: (run) => onOpen(viewOf(run)),
    // The alarms rail lists each alarm with its Investigate button.
    alarms: (run) => onOpen(viewOf(run), "alarms"),
    rename: (run) => setDialog({ kind: "rename", run }),
    compare: (run) => setDialog({ kind: "compare", run }),
    again: (run) =>
      again.mutate(run.run_id, {
        onSuccess: (created) =>
          onOpen({ runId: created.run_id, station: null, focus: null, alarm: null }),
      }),
    archive: (run, value) => update.mutate({ runId: run.run_id, body: { archived: value } }),
    showArchived: setArchived,
    handoff: () => setDialog({ kind: "handoff" }),
    fresh: () => setDialog({ kind: "fresh" }),
  };

  const keptUntil = items[0]?.expires_at ?? null;
  const devices = summary.data?.devices.length ?? 0;

  return (
    <section
      aria-labelledby="your-work-title"
      data-your-work=""
      className="mt-6 border-t border-hairline pt-4"
    >
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <h2 id="your-work-title" className="text-[17px] leading-6 font-semibold text-ink">
            {archived ? "Your archived runs" : "Your work"}
          </h2>
          <p className="min-h-10 text-[13px] leading-5 text-ink-3 sm:min-h-5">
            {!workspace && unavailable ? (
              "Not kept on this server right now."
            ) : !workspace ? (
              "Opening this device's workspace."
            ) : runs.isPending ? (
              "Reading your runs."
            ) : (
              <>
                <span className="whitespace-nowrap">
                  {archived ? plural(total, "archived run") : plural(total, "run")}
                </span>
                {keptUntil ? (
                  <span className="whitespace-nowrap">
                    {" · kept until "}
                    <LocalDateTime iso={keptUntil} />
                  </span>
                ) : (
                  <span className="whitespace-nowrap">
                    {` · kept ${summary.data?.session_days ?? 30} days after the last visit`}
                  </span>
                )}
                {devices > 1 ? (
                  <span className="whitespace-nowrap">{` · on ${plural(devices, "device")}`}</span>
                ) : null}
              </>
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            className="border-hairline-strong"
            disabled={!workspace}
            onClick={actions.handoff}
          >
            Continue on another device
          </Button>
          {menusLoaded === "workspace" ? (
            <WorkspaceMenu archived={archived} actions={actions} />
          ) : (
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label="Workspace options"
              aria-haspopup="menu"
              aria-expanded={false}
              disabled={!workspace}
              onClick={() => setMenusLoaded("workspace")}
              onPointerEnter={() => void loadMenus()}
              onFocus={() => void loadMenus()}
            >
              <MoreHorizontal aria-hidden="true" />
            </Button>
          )}
        </div>
      </div>

      <div className="mt-3">
        {!workspace && unavailable ? (
          <EmptyState className={CARD_HEIGHT} title="Your runs are not listed">
            This device&apos;s workspace could not be opened: the API keeps workspaces in its
            database, and it did not answer or has none. Runs still work; reload the page to try
            again.
          </EmptyState>
        ) : !workspace || runs.isPending ? (
          // Still, as the whole Line is when the page loads or reloads: nothing moves that is not
          // new (the line above says what is being read).
          <Placeholder
            className={cn(CARD_HEIGHT, "w-full animate-none")}
            label="Loading your runs"
          />
        ) : runs.isError ? (
          <ErrorState
            error={runs.error}
            onRetry={() => void runs.refetch()}
            className={CARD_HEIGHT}
          />
        ) : items.length === 0 ? (
          <EmptyState
            className={CARD_HEIGHT}
            title={archived ? "No archived runs" : "No runs yet"}
            action={
              archived ? (
                <Button size="sm" variant="outline" onClick={() => setArchived(false)}>
                  Show your runs
                </Button>
              ) : null
            }
          >
            {archived
              ? "Runs you archive are kept here until the workspace is deleted."
              : "Choose an input above and run it. Every run you start here is kept with its live status, so you can come back to it, compare it with another or run it again. Open this page on another device with “Continue on another device”."}
          </EmptyState>
        ) : (
          <ScrollRegion label="Your runs" className="-mx-1 px-1 pb-2">
            <ul className="flex w-max gap-3">
              {items.map((run) => (
                <li key={run.run_id} className="w-[17.5rem] shrink-0">
                  <RunCard
                    run={run}
                    onLine={run.run_id === onLine}
                    actions={actions}
                    canCompare={items.length > 1 || total > 1}
                    menuLoaded={menusLoaded === run.run_id}
                    onMenu={() => setMenusLoaded(run.run_id)}
                  />
                </li>
              ))}
              {runs.hasNextPage ? (
                <li className={cn("flex w-[12rem] shrink-0 items-center", CARD_HEIGHT)}>
                  <Button
                    size="sm"
                    variant="outline"
                    className="border-hairline-strong"
                    disabled={runs.isFetchingNextPage}
                    onClick={() => void runs.fetchNextPage()}
                  >
                    {runs.isFetchingNextPage ? "Reading more runs" : "Show older runs"}
                  </Button>
                </li>
              ) : null}
            </ul>
          </ScrollRegion>
        )}
      </div>

      <div aria-live="polite" className="sr-only">
        {statuses.said}
      </div>

      {dialog?.kind === "rename" ? (
        <RenameDialog run={dialog.run} open onOpenChange={(open) => !open && setDialog(null)} />
      ) : null}
      {dialog?.kind === "compare" ? (
        <CompareDialog
          run={dialog.run}
          runs={items}
          open
          onOpenChange={(open) => !open && setDialog(null)}
        />
      ) : null}
      {dialog?.kind === "handoff" ? (
        <HandoffDialog open onOpenChange={(open) => !open && setDialog(null)} />
      ) : null}
      {dialog?.kind === "fresh" ? (
        <FreshDialog
          open
          onOpenChange={(open) => !open && setDialog(null)}
          onMoved={() => onOpen({ runId: null, station: null, focus: null, alarm: null })}
        />
      ) : null}
    </section>
  );
}

function RunCard({
  run,
  onLine,
  actions,
  canCompare,
  menuLoaded,
  onMenu,
}: {
  run: WorkRun;
  onLine: boolean;
  actions: RunActions;
  canCompare: boolean;
  menuLoaded: boolean;
  onMenu: () => void;
}) {
  const name = runName(run);
  const titleId = `work-${run.run_id}`;
  const primary = primaryOf(run, onLine);
  const listed = run.investigations.slice(0, 2);
  const more = run.investigations.length - listed.length;

  return (
    <article
      aria-labelledby={titleId}
      aria-current={onLine ? "true" : undefined}
      data-run={run.run_id}
      className={cn(
        "flex h-full flex-col gap-1 rounded-[2px] border bg-die p-3",
        CARD_HEIGHT,
        onLine ? "border-safelight-lamp" : "border-hairline",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <h3
          id={titleId}
          className="min-w-0 truncate text-[14px] leading-5 font-medium text-ink"
          title={name}
        >
          {name}
        </h3>
        {menuLoaded ? (
          <RunMenu
            run={run}
            name={name}
            onLine={onLine}
            canCompare={canCompare}
            actions={actions}
          />
        ) : (
          <Button
            size="icon-xs"
            variant="ghost"
            aria-label={`More actions for ${name}`}
            aria-haspopup="menu"
            aria-expanded={false}
            className="-mt-0.5 -mr-1"
            onClick={onMenu}
            onPointerEnter={() => void loadMenus()}
            onFocus={() => void loadMenus()}
          >
            <MoreHorizontal aria-hidden="true" />
          </Button>
        )}
      </div>
      {/* The state is never cut short: the start time moves to the next line when it must. */}
      <p className="flex min-w-0 items-start gap-1.5 text-[12px] leading-4 text-ink-3">
        <span
          aria-hidden="true"
          className={cn("mt-[5px] inline-block size-1.5 shrink-0 rounded-full", statusDot(run))}
        />
        <span className="min-w-0">
          {runStatus(run)}
          <span aria-hidden="true">{" · "}</span>
          <LocalDateTime iso={run.created_at} className="tnum whitespace-nowrap" />
        </span>
      </p>
      <p className="line-clamp-2 text-[13px] leading-5 text-ink-2">{run.next.text}</p>
      {run.note ? (
        <p className="truncate text-[12px] leading-4 text-ink-3" title={run.note}>
          {run.note}
        </p>
      ) : null}
      {listed.length ? (
        <p className="truncate text-[12px] leading-4 text-ink-3">
          {listed.map((inv, i) => (
            <span key={inv.investigation_id}>
              {i ? ", " : null}
              <Link
                href={investigationHref(inv.investigation_id)}
                className="text-ink underline underline-offset-2 hover:text-safelight"
              >
                {`${inv.alarm_id} ${(INVESTIGATION_STATUS[inv.status] ?? inv.status).toLowerCase()}`}
              </Link>
            </span>
          ))}
          {more > 0 ? `, ${more} more` : null}
        </p>
      ) : null}
      <div className="mt-auto flex items-center gap-2 pt-1.5">
        {primary?.kind === "link" ? (
          <Button asChild size="sm">
            <Link href={primary.href}>{primary.label}</Link>
          </Button>
        ) : primary ? (
          <Button
            size="sm"
            variant={primary.kind === "open" ? "outline" : "default"}
            className={primary.kind === "open" ? "border-hairline-strong" : undefined}
            onClick={() =>
              primary.kind === "restore"
                ? actions.archive(run, false)
                : primary.kind === "alarms"
                  ? actions.alarms(run)
                  : actions.open(run)
            }
          >
            {primary.label}
          </Button>
        ) : null}
        {onLine ? <span className="text-[12px] leading-4 text-ink-3">On the line now</span> : null}
      </div>
    </article>
  );
}
