"use client";

import { API_PREFIX, type SessionInfo } from "@yield-guardian/contracts";

/**
 * Opening this device's session and workspace (POST /session/workspace), once per page load.
 * Its answer is the session itself, in the shape GET /session answers with, so it is also the
 * page's first read of the session: a first visit asks the API once, and nothing on the page
 * shows the "no workspace yet" of a read made before the workspace was open.
 */

let opening: Promise<SessionInfo | null> | null = null;
let firstRead = true;

/**
 * Opens this device's session and workspace (made on its first visit, no sign-up), once per page
 * load; the call also renews the cookie. Null when the API keeps no workspaces (no database) or
 * did not answer: the page then works without one.
 */
export function openWorkspace(): Promise<SessionInfo | null> {
  opening ??= fetch(`${API_PREFIX}/session/workspace`, {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json" },
  })
    .then(async (response) => (response.ok ? ((await response.json()) as SessionInfo) : null))
    .catch(() => null);
  return opening;
}

/** Resolves once the workspace is open (or cannot be), so what is made next is recorded in it. */
export async function workspaceReady(): Promise<void> {
  await openWorkspace();
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
