"use client";

import type { WorkRun } from "@yield-guardian/contracts";
import { MoreHorizontal } from "lucide-react";
import Link from "next/link";
import { useRef } from "react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { reportHref, resultsCsvHref } from "@/lib/api/workspace";

/** What a run's menu and the workspace menu can do; the panel carries them out. */
export interface RunActions {
  open: (run: WorkRun) => void;
  alarms: (run: WorkRun) => void;
  rename: (run: WorkRun) => void;
  compare: (run: WorkRun) => void;
  again: (run: WorkRun) => void;
  archive: (run: WorkRun, archived: boolean) => void;
  showArchived: (archived: boolean) => void;
  handoff: () => void;
  fresh: () => void;
}

/** Investigation statuses that have a written report. */
const REPORTED = new Set(["awaiting_decision", "approved", "rejected"]);

/** A run's other actions, loaded when its menu button is first pressed; it opens at once. */
export function RunMenu({
  run,
  name,
  onLine,
  canCompare,
  actions,
}: {
  run: WorkRun;
  name: string;
  onLine: boolean;
  canCompare: boolean;
  actions: RunActions;
}) {
  const reports = run.investigations.filter((i) => REPORTED.has(i.status));
  // Reopening the run, or its alarms, moves the focus to the line (the page does): it happens
  // once the menu has closed and let go of the focus, which then stays where the page puts it
  // rather than going back to the menu's button.
  const after = useRef<(() => void) | null>(null);
  return (
    <DropdownMenu defaultOpen>
      <DropdownMenuTrigger asChild>
        <Button
          size="icon-xs"
          variant="ghost"
          aria-label={`More actions for ${name}`}
          className="-mr-1.5 size-7"
        >
          <MoreHorizontal aria-hidden="true" className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        className="w-64"
        onCloseAutoFocus={(event) => {
          const next = after.current;
          after.current = null;
          if (!next) return;
          event.preventDefault();
          next();
        }}
      >
        {!onLine ? (
          <DropdownMenuItem onSelect={() => (after.current = () => actions.open(run))}>
            Reopen where you left it
          </DropdownMenuItem>
        ) : null}
        {run.alarms_open > 0 ? (
          <DropdownMenuItem onSelect={() => (after.current = () => actions.alarms(run))}>
            Investigate its alarms
          </DropdownMenuItem>
        ) : null}
        <DropdownMenuItem onSelect={() => actions.rename(run)}>
          Rename or add a note
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => actions.again(run)}>
          Run the same input again
        </DropdownMenuItem>
        <DropdownMenuItem disabled={!canCompare} onSelect={() => actions.compare(run)}>
          Compare with another run
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild disabled={run.status !== "done"}>
          <a href={resultsCsvHref(run.run_id)} download>
            Download the results (CSV)
          </a>
        </DropdownMenuItem>
        {reports.map((inv) => (
          <DropdownMenuItem key={inv.investigation_id} asChild>
            <a href={reportHref(inv.investigation_id)} download>
              {reports.length > 1
                ? `Download the report on ${inv.alarm_id}`
                : "Download the investigation report"}
            </a>
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => actions.archive(run, !run.archived)}>
          {run.archived ? "Restore to your runs" : "Archive"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** The workspace's menu: archived runs, joining another workspace, starting a fresh one. */
export function WorkspaceMenu({ archived, actions }: { archived: boolean; actions: RunActions }) {
  return (
    <DropdownMenu defaultOpen>
      <DropdownMenuTrigger asChild>
        <Button size="icon-sm" variant="ghost" aria-label="Workspace options">
          <MoreHorizontal aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuCheckboxItem
          checked={archived}
          onCheckedChange={(checked) => actions.showArchived(checked === true)}
        >
          Show archived runs
        </DropdownMenuCheckboxItem>
        <DropdownMenuItem onSelect={actions.handoff}>Continue on another device</DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/join">Join another workspace with a code</Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem variant="destructive" onSelect={actions.fresh}>
          Start a fresh workspace on this device
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
