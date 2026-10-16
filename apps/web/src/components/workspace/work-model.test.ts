import type { WorkRun, WorkRunInvestigation } from "@yield-guardian/contracts";
import { describe, expect, it } from "vitest";

import { endedSince, primaryOf, runName, runStatus, viewOf } from "./work-model";

const RUN = "run_01m4zc9a4mk6a13y2rvambdcfg";
const OTHER = "run_01m4zc9a4mk6a13y2rvambdczz";

/** A run as GET /workspace/runs lists it; the values are test inputs, not results. */
function run(change: Partial<WorkRun> = {}): WorkRun {
  return {
    run_id: RUN,
    created_at: "2026-10-15T09:00:00Z",
    expires_at: "2026-11-14T09:00:00Z",
    status: "done",
    source: "case",
    datasets: ["secom"],
    title: "Case: SPE alarm",
    rule: "A real SECOM unit whose SPE is past its limit",
    filename: null,
    seed: null,
    upload_id: null,
    again_of: null,
    units: 40,
    wafers: 0,
    stages_total: 8,
    stages_finished: 8,
    current_stage: null,
    failed_stages: [],
    alarms: 2,
    warnings: 0,
    alarms_not_listed: 0,
    alarms_open: 2,
    investigations: [],
    label: null,
    note: null,
    archived: false,
    view: null,
    next: { kind: "investigate", text: "2 alarms not investigated." },
    ...change,
  };
}

function investigation(change: Partial<WorkRunInvestigation>): WorkRunInvestigation {
  return {
    investigation_id: "inv_01m4zc9a4mk6a13y2rvambdcaa",
    alarm_id: "RA-1",
    title: "Run alarm RA-1",
    status: "running",
    updated_at: "2026-10-15T09:05:00Z",
    work_order_id: null,
    ...change,
  };
}

describe("a run's card", () => {
  it("is named by the name given to it, else by how its input was chosen", () => {
    expect(runName(run())).toBe("Case: SPE alarm");
    expect(runName(run({ label: "Tool 7 after the fix" }))).toBe("Tool 7 after the fix");
  });

  it("says how far a run has got", () => {
    expect(runStatus(run({ status: "running", stages_finished: 3 }))).toBe(
      "Computing, 3 of 8 stages",
    );
    expect(runStatus(run())).toBe("Done, 2 alarms");
    // Counted as the alarms rail counts them.
    expect(runStatus(run({ warnings: 4 }))).toBe("Done, 2 alarms, 4 warnings");
    expect(runStatus(run({ alarms: 0, warnings: 1 }))).toBe("Done, 1 warning");
    expect(runStatus(run({ alarms: 0 }))).toBe("Done, no alarms");
    expect(runStatus(run({ status: "failed" }))).toBe("Stopped");
  });

  it("offers what the run needs next, and nothing to reopen when it is on the line", () => {
    expect(primaryOf(run(), false)).toEqual({ kind: "alarms", label: "Investigate alarms" });
    expect(primaryOf(run(), true)).toEqual({ kind: "alarms", label: "Investigate alarms" });
    const quiet = run({ next: { kind: "none", text: "No alarms: nothing to follow up." } });
    expect(primaryOf(quiet, false)).toEqual({ kind: "open", label: "Reopen" });
    expect(primaryOf(quiet, true)).toBeNull();
    const running = run({ status: "running", next: { kind: "running", text: "Computing." } });
    expect(primaryOf(running, false)?.label).toBe("Watch it run");
    expect(primaryOf(running, true)).toBeNull();
    expect(primaryOf(run({ archived: true }), true)).toEqual({
      kind: "restore",
      label: "Restore",
    });
  });

  it("sends a report waiting for a decision, or a running investigation, to its page", () => {
    const waiting = run({
      investigations: [
        investigation({ status: "running" }),
        investigation({
          investigation_id: "inv_01m4zc9a4mk6a13y2rvambdcbb",
          status: "awaiting_decision",
        }),
      ],
      next: { kind: "decide", text: "A report is waiting for your decision." },
    });
    expect(primaryOf(waiting, false)).toEqual({
      kind: "link",
      label: "Decide on the report",
      href: "/investigations/inv_01m4zc9a4mk6a13y2rvambdcbb",
    });
    const watching = run({
      investigations: [investigation({ status: "queued" })],
      next: { kind: "watch", text: "An investigation is running." },
    });
    expect(primaryOf(watching, false)).toMatchObject({
      kind: "link",
      href: "/investigations/inv_01m4zc9a4mk6a13y2rvambdcaa",
    });
  });

  it("reopens where the run was left, and ignores a saved view of another run", () => {
    expect(viewOf(run({ view: `run=${RUN}&station=2&unit=14&alarm=RA-2` }))).toEqual({
      runId: RUN,
      station: 2,
      focus: { kind: "unit", index: 14 },
      alarm: "RA-2",
    });
    const plain = { runId: RUN, station: null, focus: null, alarm: null };
    expect(viewOf(run())).toEqual(plain);
    expect(viewOf(run({ view: `run=${OTHER}&station=2` }))).toEqual(plain);
  });

  it("announces runs that ended off the line, once", () => {
    const before = new Map<string, WorkRun["status"]>([
      [RUN, "running"],
      [OTHER, "running"],
    ]);
    const now = [run(), run({ run_id: OTHER, status: "done" })];
    expect(endedSince(before, now, OTHER)).toBe(
      "Case: SPE alarm finished. 2 alarms not investigated.",
    );
    expect(endedSince(new Map([[RUN, "done"]]), [run()], null)).toBe("");
  });
});
