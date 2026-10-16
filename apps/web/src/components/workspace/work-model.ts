import type { WorkRun } from "@yield-guardian/contracts";

import { plural } from "@/lib/format";
import { parseLineUrl, type LineUrlState } from "@/lib/live/url-state";
import { investigationHref } from "@/lib/routes";

/** What a run's card says and offers, from the run as the API lists it. */

export function runName(run: WorkRun): string {
  return run.label ?? run.title;
}

/** The run's alarms as the alarms rail counts them: "2 alarms, 4 warnings". */
export function alarmCount(counts: { alarms: number; warnings: number }): string {
  return (
    [
      counts.alarms ? plural(counts.alarms, "alarm") : null,
      counts.warnings ? plural(counts.warnings, "warning") : null,
    ]
      .filter(Boolean)
      .join(", ") || "no alarms"
  );
}

/** The run's state in a few words. */
export function runStatus(run: WorkRun): string {
  switch (run.status) {
    case "queued":
      return "Waiting to start";
    case "running":
      return `Computing, ${run.stages_finished} of ${run.stages_total} stages`;
    case "failed":
      return "Stopped";
    default:
      return `Done, ${alarmCount(run)}`;
  }
}

/** The dot beside the state: live while computing, the alarm colour while alarms wait. */
export function statusDot(run: WorkRun): string {
  if (run.status === "running") return "live-dot";
  if (run.status === "failed") return "bg-fail";
  if (run.status === "queued") return "bg-mark-muted";
  return run.alarms_open ? "bg-safelight" : "bg-pass";
}

/** The Line page's view a run reopens on: where it was left, or the run itself. */
export function viewOf(run: WorkRun): LineUrlState {
  const saved = run.view ? parseLineUrl(new URLSearchParams(run.view)) : null;
  return saved?.runId === run.run_id
    ? saved
    : { runId: run.run_id, station: null, focus: null, alarm: null };
}

export type Primary =
  | { kind: "open"; label: string }
  | { kind: "alarms"; label: string }
  | { kind: "link"; label: string; href: string }
  | { kind: "restore"; label: string };

/**
 * The one action a run's card shows: what the run needs next (its `next`, written by the API).
 * Null when the run is on the line and needs nothing there. The rest are in its menu.
 */
export function primaryOf(run: WorkRun, onLine: boolean): Primary | null {
  if (run.archived) return { kind: "restore", label: "Restore" };
  const decide = run.investigations.find((i) => i.status === "awaiting_decision");
  const live = run.investigations.find((i) => i.status === "queued" || i.status === "running");
  switch (run.next.kind) {
    case "decide":
      if (decide)
        return {
          kind: "link",
          label: "Decide on the report",
          href: investigationHref(decide.investigation_id),
        };
      break;
    case "watch":
      if (live)
        return {
          kind: "link",
          label: "Follow the investigation",
          href: investigationHref(live.investigation_id),
        };
      break;
    case "investigate":
      return { kind: "alarms", label: "Investigate alarms" };
    case "running":
      return onLine ? null : { kind: "open", label: "Watch it run" };
    case "failed":
      return onLine ? null : { kind: "open", label: "See where it stopped" };
  }
  return onLine ? null : { kind: "open", label: "Reopen" };
}

export type Statuses = ReadonlyMap<string, WorkRun["status"]>;

/** Sentences for runs that ended since `before`, other than the one on the line. */
export function endedSince(before: Statuses, runs: WorkRun[], onLine: string | null): string {
  return runs
    .filter((run) => {
      const was = before.get(run.run_id);
      return (
        run.run_id !== onLine &&
        (was === "queued" || was === "running") &&
        (run.status === "done" || run.status === "failed")
      );
    })
    .map(
      (run) =>
        `${runName(run)} ${run.status === "done" ? "finished" : "stopped"}. ${run.next.text}`,
    )
    .join(" ");
}
