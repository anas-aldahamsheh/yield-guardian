import { readFileSync } from "node:fs";
import path from "node:path";

import type {
  DrawLayoutList,
  Problem,
  Run,
  RunAlarm,
  RunCaseList,
  RunCreated,
  RunEvent,
  StageState,
  UploadSummary,
} from "@yield-guardian/contracts";

/**
 * The run fixture of the Line page's tests: the events of real runs made with the API's own run
 * code on the real bundles by build_fixture.py (see its docstring). Tests only; product code
 * never imports it.
 */

interface FixtureFile {
  created: RunCreated;
  events: RunEvent[];
  sensorsOnly: { created: RunCreated; events: RunEvent[] };
  layouts: DrawLayoutList;
  cases: RunCaseList;
  uploadOk: UploadSummary;
  uploadBad: UploadSummary;
  gone: Problem;
  doneAt: string;
}

const file = JSON.parse(
  readFileSync(path.join(import.meta.dirname, "run-fixture.json"), "utf-8"),
) as FixtureFile;

export const fixture = file;
export const RUN_ID = file.created.run_id;
export const sampleEvents: readonly RunEvent[] = file.events;

type Of<T extends RunEvent["type"]> = Extract<RunEvent, { type: T }>;

export function eventsOf<T extends RunEvent["type"]>(
  events: readonly RunEvent[],
  type: T,
): Of<T>[] {
  return events.filter((e): e is Of<T> => e.type === type);
}

/** GET /runs/{id} as the server would answer once the given events have happened. */
export function snapshotOf(events: readonly RunEvent[], runId = RUN_ID): Run {
  const started = eventsOf(events, "run_started")[0];
  if (!started) throw new Error("The events have no run_started");
  const stages = new Map<StageState["stage"], StageState>(
    started.stages.map((s) => [s.stage, { ...s }]),
  );
  const alarms: RunAlarm[] = [];
  let status: Run["status"] = "running";
  let notListed = 0;
  for (const event of events) {
    switch (event.type) {
      case "stage_started":
        stages.set(event.stage, {
          ...stages.get(event.stage)!,
          status: "running",
          started_at: event.at,
        });
        break;
      case "stage_result":
        stages.set(event.stage, {
          ...stages.get(event.stage)!,
          status: "done",
          result: event.result,
          elapsed_ms: event.elapsed_ms,
          started_at: null,
        });
        break;
      case "stage_skipped":
        stages.set(event.stage, {
          ...stages.get(event.stage)!,
          status: "skipped",
          needs: event.needs,
        });
        break;
      case "stage_failed":
        stages.set(event.stage, {
          ...stages.get(event.stage)!,
          status: "failed",
          problem: event.problem,
        });
        break;
      case "alarm":
        alarms.push(event.alarm);
        break;
      case "run_done":
        status = event.status;
        notListed = event.alarms_not_listed ?? 0;
        break;
      default:
        break;
    }
  }
  const intake = stages.get("intake")?.result;
  return {
    run_id: runId,
    created_at: started.at,
    status,
    origin: started.origin,
    units: intake && intake.stage === "intake" ? intake.units : 0,
    wafers: intake && intake.stage === "intake" ? intake.wafers : 0,
    stages: [...stages.values()],
    alarms,
    alarms_not_listed: notListed,
    expires_at: new Date(Date.parse(started.at) + 24 * 3600_000).toISOString(),
    last_seq: Math.max(...events.map((e) => e.seq)),
    read_at: events.at(-1)!.at,
  };
}

/**
 * The same units as the sample, picked by id with no wafers (a real run of its own, made by
 * build_fixture.py): the wafer stages are skipped with what they need.
 */
export const SENSORS_ONLY_ID = file.sensorsOnly.created.run_id;

export function sensorsOnlyEvents(): RunEvent[] {
  return file.sensorsOnly.events;
}

/** Encodes events as the SSE wire format (`event` is the type, `id` is the seq). */
export function sseBody(
  events: readonly RunEvent[],
  { retryMs }: { retryMs?: number } = {},
): string {
  const head = retryMs != null ? `retry: ${retryMs}\n\n` : "";
  return (
    head +
    events.map((e) => `event: ${e.type}\nid: ${e.seq}\ndata: ${JSON.stringify(e)}\n\n`).join("")
  );
}
