"use client";

import { API_PREFIX, type SessionInfo } from "@yield-guardian/contracts";

import { ApiError, isProblem } from "./errors";
import { retryAfterMs, sleep, withRetry } from "./retry";

/**
 * Opening this device's session and workspace (POST /session/workspace), once per page load.
 * Its answer is the session itself, in the shape GET /session answers with, so it is also the
 * page's first read of the session: a first visit asks the API once, and nothing on the page
 * shows the "no workspace yet" of a read made before the workspace was open.
 *
 * The first visit after a quiet spell finds the API asleep. The opening then waits for it as
 * every read does (lib/api/retry.ts): it asks again when no answer came, on a 503, and on any 5xx
 * of the proxy in front of the API, after 1, 2, 4 and then 8 seconds, or later when a Retry-After
 * asks for longer, for about a minute and a half. Asking again is safe: a device that has its
 * session gets the same one back. Until the workspace is open the session reads as loading, and
 * what is made meanwhile waits for it, so a run or an upload of the first visit is recorded in
 * it. Any other answer, or none in all that time, leaves the page without a workspace, as an API
 * that keeps none (no database) does.
 */

/** One page load's opening: what it is doing, and when it asks again while the API wakes. */
class Opening {
  phase: "asking" | "waiting" | "done" = "asking";
  /** When it asks again (ms since the epoch), while it waits for the API. */
  nextTry = 0;
  readonly session: Promise<SessionInfo | null>;
  private moved: (() => void)[] = [];

  constructor() {
    this.session = withRetry(() => this.ask(), {
      retryIf: isWaking,
      wait: (ms) => {
        this.nextTry = Date.now() + ms;
        this.enter("waiting");
        return sleep(ms);
      },
    }).then(
      (session) => this.end(session),
      () => this.end(null),
    );
  }

  /** Resolves when the opening next changes what it is doing. */
  changed(): Promise<void> {
    return new Promise((resolve) => this.moved.push(resolve));
  }

  private enter(phase: Opening["phase"]) {
    this.phase = phase;
    for (const resolve of this.moved.splice(0)) resolve();
  }

  private end(session: SessionInfo | null): SessionInfo | null {
    this.enter("done");
    return session;
  }

  /** One request: the session, or an ApiError (status 0 when no answer came). */
  private async ask(): Promise<SessionInfo> {
    this.enter("asking");
    let response: Response;
    try {
      response = await fetch(`${API_PREFIX}/session/workspace`, {
        method: "POST",
        credentials: "include",
        headers: { Accept: "application/json" },
      });
    } catch (error) {
      throw new ApiError(0, null, error instanceof Error ? error.message : "No answer");
    }
    if (response.ok) return (await response.json()) as SessionInfo;
    const body: unknown = await response.json().catch(() => null);
    throw new ApiError(
      response.status,
      isProblem(body) ? body : null,
      undefined,
      retryAfterMs(response.headers.get("Retry-After")),
    );
  }
}

/**
 * The API is waking: no answer came; or a 5xx came from the proxy in front of it, which carries
 * no problem of the API's own (the API answers every error of its own as one): a 503 while it
 * wakes, a 502 while the API does not take connections yet, a 504 when the proxy gave up
 * waiting; or the API's own 503 while it starts, with a Retry-After. Any other answer of the
 * API's own is an answer: a 4xx, a 500, and the 503 that names no wait, which an API that keeps
 * no workspaces (no database) answers.
 */
function isWaking(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false;
  if (error.status === 0) return true;
  if (error.status < 500) return false;
  return error.problem === null || (error.status === 503 && error.retryAfterMs !== null);
}

let opening: Opening | null = null;
let firstRead = true;

/**
 * Opens this device's session and workspace (made on its first visit, no sign-up), once per page
 * load, waiting for the API while it wakes; the call also renews the cookie. Null when the API
 * keeps no workspaces (no database) or did not answer in time: the page then works without one.
 */
export function openWorkspace(): Promise<SessionInfo | null> {
  opening ??= new Opening();
  return opening.session;
}

/**
 * Resolves once the workspace is open (or cannot be), so what is made next is recorded in it.
 *
 * With `refuseWhileWaking`, a call made while the opening waits between two tries for the API is
 * refused as the API refuses one then: an ApiError 503 that asks to wait until the next try. A
 * caller that waits and asks again on a 503 (the Line page's run start, lib/api/retry.ts) then
 * says the service is starting. A request of the opening on its way is waited for either way.
 */
export async function workspaceReady({ refuseWhileWaking = false } = {}): Promise<void> {
  const current = (opening ??= new Opening());
  if (refuseWhileWaking) {
    while (current.phase === "asking") await current.changed();
    if (current.phase === "waiting") {
      throw new ApiError(503, null, undefined, Math.max(0, current.nextTry - Date.now()));
    }
  }
  await current.session;
}

/**
 * The session as the page reads it (browser only). Its first read waits for the workspace to
 * open and is that answer; `read` (GET /session) is asked only when the workspace could not be
 * opened, and for every later read, such as the one after signing out.
 */
export async function readSession(read: () => Promise<SessionInfo>): Promise<SessionInfo> {
  if (firstRead) {
    firstRead = false;
    const opened = await openWorkspace();
    if (opened) return opened;
  }
  return read();
}

/** For tests: as if the page had just loaded. */
export function forgetOpening() {
  opening = null;
  firstRead = true;
}
