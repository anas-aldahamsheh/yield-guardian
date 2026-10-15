import type { StageId, StoredRunData } from "./run-state";

/**
 * What the server read of a run when it rendered the Line page (app/page.tsx), handed to the
 * page so a reload, a link or another device of the workspace shows the run's stored state in
 * the first paint, with nothing replayed. The run comes in the compact form of lib/live/glance.ts
 * (whatever its size): `partial` names the stages whose bulk the page reads just after. Null when
 * the server did not read it (no run in the address, or no answer in time): the page reads it then.
 */
export type StoredRun =
  | { kind: "run"; run: StoredRunData; partial: StageId[] }
  /** The API answered 404: no such run, or one of another workspace. */
  | { kind: "not_found"; runId: string }
  /** The API answered 410: the run has expired. */
  | { kind: "gone"; runId: string };

export function storedRunId(stored: StoredRun | null): string | null {
  if (!stored) return null;
  return stored.kind === "run" ? stored.run.run_id : stored.runId;
}
