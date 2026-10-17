"use client";

import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import type { WorkRun, WorkRunPage } from "@yield-guardian/contracts";
import { KeyRound, MonitorSmartphoneIcon, MoreHorizontal } from "lucide-react";
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
import { DRAFT_KEYS, writeDraft } from "@/lib/live/drafts";
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
      className="-mr-1.5 size-7"
    >
      <MoreHorizontal aria-hidden="true" className="size-4" />
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
const DeleteRunDialog = dynamic(() => loadDialogs().then((m) => m.DeleteRunDialog), {
  ssr: false,
});

/** Every card and the strip's placeholders take this height, so nothing moves when runs arrive. */
const CARD_HEIGHT = "min-h-[11.5rem]";
const LIVE_EVERY_MS = 2_000;
const IDLE_EVERY_MS = 20_000;

type Dialog =
  | { kind: "rename"; run: WorkRun }
  | { kind: "compare"; run: WorkRun }
  | { kind: "delete"; run: WorkRun }
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
  vertical = false,
}: {
  /** What the Line page shows now. */
  current: LineUrlState;
  /**
   * Shows a run on the Line page, at a station and item; once it is on the line the focus goes to
   * the run, or to its alarms (`to`).
   */
  onOpen: (view: LineUrlState, to?: "run" | "alarms") => void;
  /** When true, renders runs vertically spanning the full width (for sidebar sheet or full page). */
  vertical?: boolean;
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
    refetchOnMount: "always",
    staleTime: 0,
    refetchInterval: (query) =>
      query.state.data?.pages.some((page: WorkRunPage) => page.items.some(isLive))
        ? LIVE_EVERY_MS
        : IDLE_EVERY_MS,
  });
  const summary = useQuery({
    ...wq.summary(api),
    enabled: workspace != null,
    refetchOnWindowFocus: true,
    refetchOnMount: "always",
    staleTime: 0,
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
    open: (run) => {
      writeDraft(DRAFT_KEYS.way, null);
      onOpen(viewOf(run));
    },
    // The alarms rail lists each alarm with its Investigate button.
    alarms: (run) => {
      writeDraft(DRAFT_KEYS.way, null);
      onOpen(viewOf(run), "alarms");
    },
    rename: (run) => setDialog({ kind: "rename", run }),
    compare: (run) => setDialog({ kind: "compare", run }),
    again: (run) => {
      writeDraft(DRAFT_KEYS.way, null);
      again.mutate(run.run_id, {
        onSuccess: (created) =>
          onOpen({ runId: created.run_id, station: null, focus: null, alarm: null }),
      });
    },
    archive: (run, value) => update.mutate({ runId: run.run_id, body: { archived: value } }),
    remove: (run) => setDialog({ kind: "delete", run }),
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
      className={cn(vertical ? "w-full" : "mt-16 border-t border-hairline pt-8 sm:mt-20")}
    >
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
        <div className="min-w-0">
          <h2
            id="your-work-title"
            className={cn(
              "font-[640] tracking-[-0.02em] text-ink [font-stretch:108%]",
              vertical
                ? "text-[18px] leading-6 sm:text-[20px]"
                : "text-[26px] leading-8 sm:text-[30px] sm:leading-9",
            )}
          >
            {archived ? "Your archived runs" : vertical ? "Saved Production Runs" : "Your work"}
          </h2>
          <p
            className={cn(
              "mt-1 text-ink-2",
              vertical ? "text-[13px] leading-4" : "min-h-10 text-[14px] leading-5 sm:min-h-5",
            )}
          >
            {!workspace && unavailable ? (
              "Not kept on this server right now."
            ) : !workspace ? (
              "Opening this device's workspace."
            ) : runs.isPending ? (
              "Reading your runs."
            ) : (
              <>
                <span className="tnum font-[560] whitespace-nowrap text-ink">
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
          <Button size="sm" variant="outline" asChild>
            <Link href="/join" className="inline-flex items-center gap-1.5">
              <KeyRound aria-hidden="true" className="size-3.5" />
              <span>Join workspace with code</span>
            </Link>
          </Button>
          <Button size="sm" variant="outline" disabled={!workspace} onClick={actions.handoff}>
            <MonitorSmartphoneIcon aria-hidden="true" strokeWidth={1.8} />
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

      <div className={cn(vertical ? "mt-4" : "mt-6")}>
        {!workspace && unavailable ? (
          <EmptyState
            className={cn(
              vertical ? "min-h-[9.5rem] w-full" : CARD_HEIGHT,
              "unexposed rounded-[20px] border-solid bg-surface",
            )}
            title="Your runs are not listed"
          >
            This device&apos;s workspace could not be opened: the API keeps workspaces in its
            database, and it did not answer or has none. Runs still work; reload the page to try
            again.
          </EmptyState>
        ) : !workspace || runs.isPending ? (
          // Still, as the whole Line is when the page loads or reloads: nothing moves that is not
          // new (the line above says what is being read).
          <Placeholder
            still
            className={cn(
              vertical ? "min-h-[9.5rem] w-full" : CARD_HEIGHT,
              "unexposed w-full rounded-[20px] bg-surface shadow-[inset_0_0_0_1px_var(--hairline)]",
            )}
            label="Loading your runs"
          />
        ) : runs.isError ? (
          <ErrorState
            error={runs.error}
            onRetry={() => void runs.refetch()}
            className={cn(vertical ? "min-h-[9.5rem] w-full" : CARD_HEIGHT)}
          />
        ) : items.length === 0 ? (
          <EmptyState
            className={cn(
              vertical ? "min-h-[9.5rem] w-full" : CARD_HEIGHT,
              "unexposed rounded-[20px] border-solid bg-surface px-6 py-7 sm:px-8",
            )}
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
        ) : vertical ? (
          <ul className="flex flex-col gap-3.5 w-full">
            {items.map((run) => (
              <li key={run.run_id} className="w-full">
                <RunCard
                  run={run}
                  onLine={run.run_id === onLine}
                  actions={actions}
                  canCompare={items.length > 1 || total > 1}
                  menuLoaded={menusLoaded === run.run_id}
                  onMenu={() => setMenusLoaded(run.run_id)}
                  vertical={true}
                />
              </li>
            ))}
            {runs.hasNextPage ? (
              <li className="flex w-full justify-center pt-2 pb-2">
                <Button
                  size="sm"
                  variant="outline"
                  className="w-full"
                  disabled={runs.isFetchingNextPage}
                  onClick={() => void runs.fetchNextPage()}
                >
                  {runs.isFetchingNextPage ? "Reading more runs" : "Show older runs"}
                </Button>
              </li>
            ) : null}
          </ul>
        ) : (
          <ScrollRegion label="Your runs" className="-mx-2 snap-x scroll-px-2 px-2 pt-1 pb-3">
            <ul className="flex w-max gap-4">
              {items.map((run) => (
                <li key={run.run_id} className="w-[18.5rem] shrink-0 snap-start">
                  <RunCard
                    run={run}
                    onLine={run.run_id === onLine}
                    actions={actions}
                    canCompare={items.length > 1 || total > 1}
                    menuLoaded={menusLoaded === run.run_id}
                    onMenu={() => setMenusLoaded(run.run_id)}
                    vertical={false}
                  />
                </li>
              ))}
              {runs.hasNextPage ? (
                <li className={cn("flex w-[12rem] shrink-0 snap-start items-center", CARD_HEIGHT)}>
                  <Button
                    size="sm"
                    variant="outline"
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
      {dialog?.kind === "delete" ? (
        <DeleteRunDialog
          run={dialog.run}
          open
          onOpenChange={(open) => !open && setDialog(null)}
          onDeleted={(run) => {
            // The run on the line is gone: the line goes back to idle.
            if (run.run_id === onLine)
              onOpen({ runId: null, station: null, focus: null, alarm: null });
          }}
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

/**
 * One run of the workspace: its name, its state with the dot that repeats it, what it needs
 * next and the one action for that; the rest is in its menu. The run on the line is lit.
 */
function RunCard({
  run,
  onLine,
  actions,
  canCompare,
  menuLoaded,
  onMenu,
  vertical = false,
}: {
  run: WorkRun;
  onLine: boolean;
  actions: RunActions;
  canCompare: boolean;
  menuLoaded: boolean;
  onMenu: () => void;
  vertical?: boolean;
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
        "flex flex-col rounded-[20px] bg-surface px-4 pt-3.5 pb-4 transition-shadow duration-(--dur-3)",
        vertical ? "w-full min-h-[9.5rem]" : cn("h-full", CARD_HEIGHT),
        onLine
          ? "shadow-[inset_0_0_0_1.5px_var(--signal),var(--highlight)]"
          : "shadow-[inset_0_0_0_1px_var(--hairline),var(--highlight)] hover:shadow-[inset_0_0_0_1px_var(--hairline-strong),var(--highlight),var(--elev-float)]",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <h3
          id={titleId}
          className="min-w-0 truncate text-[15px] leading-6 font-[620] tracking-[-0.005em] text-ink"
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
            className="-mr-1.5 size-7"
            onClick={onMenu}
            onPointerEnter={() => void loadMenus()}
            onFocus={() => void loadMenus()}
          >
            <MoreHorizontal aria-hidden="true" className="size-4" />
          </Button>
        )}
      </div>
      {/* The state is never cut short: the start time moves to the next line when it must. */}
      <p className="mt-0.5 flex min-w-0 items-start gap-2 text-[12.5px] leading-[18px] text-ink-2">
        <span
          aria-hidden="true"
          className={cn("mt-[6px] inline-block size-1.5 shrink-0 rounded-full", statusDot(run))}
        />
        <span className="min-w-0">
          {runStatus(run)}
          <span aria-hidden="true" className="text-ink-3">
            {" · "}
          </span>
          <LocalDateTime iso={run.created_at} className="tnum whitespace-nowrap text-ink-3" />
        </span>
      </p>
      <p className="mt-2.5 line-clamp-2 text-[13.5px] leading-5 text-ink">{run.next.text}</p>
      {run.note ? (
        <p className="mt-1 truncate text-[12.5px] leading-4 text-ink-3" title={run.note}>
          {run.note}
        </p>
      ) : null}
      {listed.length ? (
        <p className="mt-1.5 truncate text-[12.5px] leading-4 text-ink-3">
          {listed.map((inv, i) => (
            <span key={inv.investigation_id}>
              {i ? ", " : null}
              <Link
                href={investigationHref(inv.investigation_id)}
                className="tnum text-ink-2 underline decoration-hairline-strong underline-offset-2 transition-colors duration-(--dur-1) hover:text-ink hover:decoration-ink"
              >
                {`${inv.alarm_id} ${(INVESTIGATION_STATUS[inv.status] ?? inv.status).toLowerCase()}`}
              </Link>
            </span>
          ))}
          {more > 0 ? `, ${more} more` : null}
        </p>
      ) : null}
      <div className="mt-auto flex flex-wrap items-center gap-x-2.5 gap-y-2 pt-3.5">
        {primary?.kind === "link" ? (
          <>
            <Button asChild size="sm">
              <Link href={primary.href}>{primary.label}</Link>
            </Button>
            {!onLine && (
              <Button size="sm" variant="outline" onClick={() => actions.open(run)}>
                Reopen
              </Button>
            )}
          </>
        ) : primary?.kind === "alarms" ? (
          <>
            <Button size="sm" variant="default" onClick={() => actions.alarms(run)}>
              {primary.label}
            </Button>
            {!onLine && (
              <Button size="sm" variant="outline" onClick={() => actions.open(run)}>
                Reopen
              </Button>
            )}
          </>
        ) : primary?.kind === "restore" ? (
          <Button size="sm" variant="outline" onClick={() => actions.archive(run, false)}>
            {primary.label}
          </Button>
        ) : primary?.kind === "open" ? (
          <Button size="sm" variant="outline" onClick={() => actions.open(run)}>
            {primary.label}
          </Button>
        ) : !onLine ? (
          <Button size="sm" variant="outline" onClick={() => actions.open(run)}>
            Reopen
          </Button>
        ) : null}

        {onLine ? (
          <span className="inline-flex items-center gap-1.5 text-[12px] leading-4 font-[560] text-signal">
            <span aria-hidden="true" className="size-1.5 rounded-full bg-signal" />
            On the line now
          </span>
        ) : null}
      </div>
    </article>
  );
}
