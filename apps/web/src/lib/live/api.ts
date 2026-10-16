import {
  API_PREFIX,
  type DrawLayoutList,
  type Investigation,
  type InvestigationTrigger,
  type Run,
  type RunCaseList,
  type RunCreate,
  type RunCreated,
  type UnitChartResult,
  type UploadSummary,
} from "@yield-guardian/contracts";

import { ApiError, isProblem } from "@/lib/api/errors";
import { retryAfterMs } from "@/lib/api/retry";
import { workspaceReady } from "@/lib/api/workspace";

import { RUN_GONE_MESSAGE } from "./sse";

/**
 * Calls of the live run API (PLAN_V2 §3.3). Plain fetch on the page's own origin, typed by the
 * generated contracts; every refusal becomes an ApiError with the API's problem.
 */

type Fetch = typeof fetch;

/**
 * The service is up but not ready for this yet (503 with Retry-After): the case catalog is still
 * being found in the data after a start. Callers wait and ask again (the shared retry policy,
 * lib/api/retry.ts, waits as told); it is not a failure.
 */
export class NotReadyYet extends ApiError {
  constructor(problem: ApiError["problem"], retryAfter: number) {
    super(503, problem, undefined, retryAfter);
  }
}

export type UploadFormat = "csv" | "xlsx";
export type UploadKind = UploadSummary["kind"];

/** The ref of a run alarm as an investigation trigger (PLAN_V2 §3.4). */
export function runAlarmRef(runId: string, alarmId: string): string {
  return `${runId}:${alarmId}`;
}

async function call<T>(
  path: string,
  init: RequestInit,
  doFetch: Fetch = globalThis.fetch.bind(globalThis),
): Promise<T> {
  let response: Response;
  try {
    response = await doFetch(`${API_PREFIX}${path}`, { credentials: "include", ...init });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, null, error instanceof Error ? error.message : "Network error");
  }
  let body: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }
  if (!response.ok) {
    const problem = isProblem(body) ? body : null;
    const wait = response.status >= 500 ? retryAfterMs(response.headers.get("Retry-After")) : null;
    if (wait != null && response.status === 503) throw new NotReadyYet(problem, wait);
    throw new ApiError(
      response.status,
      problem,
      response.status === 410 ? RUN_GONE_MESSAGE : undefined,
      wait,
    );
  }
  return body as T;
}

function json(body: unknown, headers: Record<string, string> = {}): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json", ...headers },
    body: JSON.stringify(body),
  };
}

/** Starts a run, recorded in this device's workspace (opened first on a first visit). */
export async function createRun(
  body: RunCreate,
  csrf: Record<string, string> = {},
  doFetch?: Fetch,
) {
  await workspaceReady();
  return call<RunCreated>("/runs", json(body, csrf), doFetch);
}

export function getRun(runId: string, init: RequestInit = {}, doFetch?: Fetch) {
  return call<Run>(`/runs/${encodeURIComponent(runId)}`, { cache: "no-store", ...init }, doFetch);
}

/**
 * One unit's control-chart result with its standardised readings. The stream and GET /runs/{id}
 * carry `z` for the first 200 units only; the sensor bank and the drawer read the rest here.
 */
export function getUnitChart(
  runId: string,
  index: number,
  init: RequestInit = {},
  doFetch?: Fetch,
) {
  return call<UnitChartResult>(
    `/runs/${encodeURIComponent(runId)}/units/${index}/chart`,
    init,
    doFetch,
  );
}

export function getRunCases(init: RequestInit = {}, doFetch?: Fetch) {
  return call<RunCaseList>("/runs/cases", init, doFetch);
}

export function getDrawLayouts(init: RequestInit = {}, doFetch?: Fetch) {
  return call<DrawLayoutList>("/runs/layouts", init, doFetch);
}

/** Sends a file to be parsed and validated (multipart field `file`), into this workspace. */
export async function uploadFile(file: File, csrf: Record<string, string> = {}, doFetch?: Fetch) {
  await workspaceReady();
  const form = new FormData();
  form.append("file", file, file.name);
  return call<UploadSummary>(
    "/uploads",
    { method: "POST", headers: { Accept: "application/json", ...csrf }, body: form },
    doFetch,
  );
}

/** Header-only template of the upload format. */
export function templateUrl(kind: UploadKind, format: UploadFormat): string {
  return `${API_PREFIX}/uploads/templates/${kind}.${format}`;
}

/** Real SECOM units or a real WM-811K lot, in the upload format. */
export function exampleUrl(kind: UploadKind, format: UploadFormat): string {
  return `${API_PREFIX}/uploads/examples/${kind}.${format}`;
}

/** Starts an investigation of one run alarm (needs an engineer session and its CSRF token). */
export function investigateRunAlarm(
  runId: string,
  alarmId: string,
  csrf: Record<string, string>,
  doFetch?: Fetch,
) {
  const trigger: InvestigationTrigger = { kind: "run_alarm", ref: runAlarmRef(runId, alarmId) };
  return call<Investigation>("/investigations", json({ trigger }, csrf), doFetch);
}

/** The run is no longer kept (410): the page offers a new run instead of retrying. */
export function isGone(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 410 || error.problem?.code === "gone");
}
