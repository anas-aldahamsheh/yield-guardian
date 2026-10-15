import { API_PREFIX, type Problem, type RunEvent } from "@yield-guardian/contracts";

import { isProblem } from "@/lib/api/errors";
import { retryAfterMs } from "@/lib/api/retry";

/**
 * The run's event stream (GET /runs/{id}/events) read with fetch rather than EventSource, so the
 * page sees the HTTP status (410 for an expired run, 404 for an unknown one) and decides itself
 * when to reconnect: with `Last-Event-ID` set to the last event it applied, after a growing
 * pause, and never again once `run_done` has arrived.
 */

export const RUN_EVENT_TYPES = [
  "run_started",
  "stage_started",
  "stage_result",
  "stage_skipped",
  "stage_failed",
  "alarm",
  "run_done",
] as const satisfies readonly RunEvent["type"][];

const EVENT_TYPES: ReadonlySet<string> = new Set(RUN_EVENT_TYPES);

export const RUN_GONE_MESSAGE = "This run has expired (runs are kept 24 hours). Start a new one.";

export function runEventsUrl(runId: string): string {
  return `${API_PREFIX}/runs/${encodeURIComponent(runId)}/events`;
}

// ---------------------------------------------------------------------------------------------
// The text/event-stream format (WHATWG HTML, "Parsing an event stream")
// ---------------------------------------------------------------------------------------------

export interface SseMessage {
  /** "message" when the server sent no `event:` field. */
  event: string;
  data: string;
  /** The last `id:` seen on the stream so far, as the spec keeps it. */
  id: string | null;
}

export interface SseParser {
  /** Feeds decoded text; chunks may split lines and line endings anywhere. */
  push(text: string): void;
  /** The stream ended: an unfinished message is dropped, as the spec says. */
  end(): void;
}

/**
 * A parser for one stream. Lines end in CRLF, LF or CR; a blank line dispatches the message;
 * lines starting with ":" are comments; `retry:` with digits only reports the server's
 * reconnection time.
 */
export function createSseParser(
  onMessage: (message: SseMessage) => void,
  onRetry: (ms: number) => void = () => {},
): SseParser {
  let buffer = "";
  let started = false;
  let skipLf = false;
  let event = "";
  let data: string[] = [];
  let hasData = false;
  let lastId: string | null = null;

  const line = (text: string) => {
    if (text === "") {
      if (hasData) onMessage({ event: event || "message", data: data.join("\n"), id: lastId });
      event = "";
      data = [];
      hasData = false;
      return;
    }
    if (text.startsWith(":")) return;
    const colon = text.indexOf(":");
    const field = colon === -1 ? text : text.slice(0, colon);
    let value = colon === -1 ? "" : text.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    switch (field) {
      case "event":
        event = value;
        break;
      case "data":
        data.push(value);
        hasData = true;
        break;
      case "id":
        if (!value.includes("\0")) lastId = value;
        break;
      case "retry":
        if (/^\d+$/.test(value)) onRetry(Number.parseInt(value, 10));
        break;
      default:
        break;
    }
  };

  return {
    push(text) {
      if (!started && text.length > 0) {
        started = true;
        if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
      }
      if (skipLf && text.startsWith("\n")) text = text.slice(1);
      skipLf = false;
      buffer += text;
      let at = 0;
      for (;;) {
        const cr = buffer.indexOf("\r", at);
        const lf = buffer.indexOf("\n", at);
        if (cr === -1 && lf === -1) break;
        const end = cr === -1 ? lf : lf === -1 ? cr : Math.min(cr, lf);
        line(buffer.slice(at, end));
        if (buffer[end] === "\r") {
          if (end + 1 === buffer.length) {
            // A CR at the end of the chunk: its LF, if any, starts the next one.
            skipLf = true;
            at = end + 1;
            break;
          }
          at = buffer[end + 1] === "\n" ? end + 2 : end + 1;
        } else {
          at = end + 1;
        }
      }
      buffer = buffer.slice(at);
    },
    end() {
      buffer = "";
      event = "";
      data = [];
      hasData = false;
    },
  };
}

/** Reads one SSE message as a run event, or null when it is not one. */
export function parseRunEvent(message: SseMessage): RunEvent | null {
  if (!EVENT_TYPES.has(message.event)) return null;
  let value: unknown;
  try {
    value = JSON.parse(message.data);
  } catch {
    return null;
  }
  if (typeof value !== "object" || value === null) return null;
  const event = value as Partial<RunEvent>;
  if (
    event.type !== message.event ||
    typeof event.seq !== "number" ||
    !Number.isInteger(event.seq)
  ) {
    return null;
  }
  return value as RunEvent;
}

// ---------------------------------------------------------------------------------------------
// Following a run
// ---------------------------------------------------------------------------------------------

export type RunStreamStatus = "connecting" | "streaming" | "reconnecting" | "ended";

export type RunStreamErrorKind = "gone" | "not_found" | "rejected";

/** The stream cannot go on: the run expired, does not exist, or the API refused it. */
export class RunStreamError extends Error {
  override readonly name = "RunStreamError";

  constructor(
    readonly kind: RunStreamErrorKind,
    readonly status: number,
    readonly problem: Problem | null,
    message: string,
  ) {
    super(message);
  }
}

export interface FollowRunOptions {
  runId: string;
  /** The last seq applied without a gap, sent as Last-Event-ID; null on the first connect. */
  resumeFrom: () => number | null;
  onEvent: (event: RunEvent) => void;
  onStatus?: (status: RunStreamStatus) => void;
  signal: AbortSignal;
  fetch?: typeof fetch;
  /** First pause before reconnecting; doubles per failed attempt up to `maxDelayMs`. */
  initialDelayMs?: number;
  maxDelayMs?: number;
  sleep?: (ms: number, signal: AbortSignal) => Promise<void>;
}

export interface FollowRunResult {
  /** run_done arrived (false when the caller aborted). */
  finished: boolean;
}

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) return resolve();
    const timer = setTimeout(done, ms);
    function done() {
      clearTimeout(timer);
      signal.removeEventListener("abort", done);
      resolve();
    }
    signal.addEventListener("abort", done, { once: true });
  });
}

async function problemOf(response: Response): Promise<Problem | null> {
  try {
    const body: unknown = await response.json();
    return isProblem(body) ? body : null;
  } catch {
    return null;
  }
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

/** A refusal that a reconnect cannot fix, or null when trying again may help. */
async function refusal(response: Response): Promise<RunStreamError | null> {
  if (response.status === 410) {
    return new RunStreamError("gone", 410, await problemOf(response), RUN_GONE_MESSAGE);
  }
  if (response.status === 404) {
    const problem = await problemOf(response);
    return new RunStreamError(
      "not_found",
      404,
      problem,
      "There is no run with this link. Start a new one.",
    );
  }
  // 408 and 429 may pass; any other 4xx will not.
  if (
    response.status >= 400 &&
    response.status < 500 &&
    response.status !== 408 &&
    response.status !== 429
  ) {
    const problem = await problemOf(response);
    return new RunStreamError(
      "rejected",
      response.status,
      problem,
      problem?.detail ?? problem?.title ?? `The API answered ${response.status}.`,
    );
  }
  return null;
}

/**
 * Follows a run until `run_done`, reconnecting with Last-Event-ID after a dropped connection or
 * a server error. Resolves when the run is finished or the signal aborts; rejects with a
 * RunStreamError when the run is gone, unknown or refused.
 */
export async function followRun(options: FollowRunOptions): Promise<FollowRunResult> {
  const doFetch = options.fetch ?? globalThis.fetch.bind(globalThis);
  const sleep = options.sleep ?? wait;
  const initial = options.initialDelayMs ?? 1000;
  const max = options.maxDelayMs ?? 15_000;
  const { signal } = options;
  let serverRetry: number | null = null;
  let failures = 0;

  while (!signal.aborted) {
    options.onStatus?.(failures === 0 ? "connecting" : "reconnecting");
    const headers: Record<string, string> = { Accept: "text/event-stream" };
    const resume = options.resumeFrom();
    if (resume != null) headers["Last-Event-ID"] = String(resume);

    let finished = false;
    /** What the API (or the proxy in front of it while it wakes) asked to wait, if it did. */
    let asked: number | null = null;
    try {
      const response = await doFetch(runEventsUrl(options.runId), {
        headers,
        credentials: "include",
        cache: "no-store",
        signal,
      });
      const refused = await refusal(response);
      if (refused) {
        options.onStatus?.("ended");
        throw refused;
      }
      if (!response.ok) asked = retryAfterMs(response.headers.get("Retry-After"));
      if (response.ok && response.body) {
        options.onStatus?.("streaming");
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        const parser = createSseParser(
          (message) => {
            if (finished) return;
            const event = parseRunEvent(message);
            if (!event) return;
            failures = 0;
            options.onEvent(event);
            if (event.type === "run_done") finished = true;
          },
          (ms) => {
            serverRetry = ms;
          },
        );
        try {
          while (!finished) {
            const { done, value } = await reader.read();
            if (done) break;
            parser.push(decoder.decode(value, { stream: true }));
          }
          if (!finished) parser.push(decoder.decode());
        } finally {
          parser.end();
          if (finished) await reader.cancel().catch(() => {});
          else reader.releaseLock();
        }
      }
    } catch (error) {
      if (error instanceof RunStreamError) throw error;
      if (isAbort(error) || signal.aborted) break;
      // A dropped connection or no answer: try again below.
    }
    if (finished) {
      options.onStatus?.("ended");
      return { finished: true };
    }
    if (signal.aborted) break;
    failures += 1;
    const base = serverRetry ?? initial;
    options.onStatus?.("reconnecting");
    await sleep(asked ?? Math.min(max, base * 2 ** (failures - 1)), signal);
  }
  return { finished: false };
}
