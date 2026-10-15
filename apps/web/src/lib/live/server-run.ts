import "server-only";

import { API_PREFIX, type Run } from "@yield-guardian/contracts";
import { headers } from "next/headers";
import { connection } from "next/server";

import { serverApiOrigin } from "@/lib/api/config";

import type { StoredRun } from "./stored-run";

/**
 * The run's stored state as the API holds it, read by the Next.js server while it renders the
 * Line page, so the first paint already shows every result.
 *
 * The request carries the visitor's own cookies (and nothing else of theirs), since a run is
 * visible only to its workspace; the API it goes to is API_INTERNAL_URL, never an address from
 * the request. Anything but an answer within `timeoutMs` leaves the reading to the browser, and
 * so does a run whose state is larger than `maxChars`: it would make the page itself that large.
 */

/** About 3 MB of JSON: a real sample with its lot is about 1 MB; full SECOM uploads are larger. */
export const MAX_EMBEDDED_CHARS = 3_000_000;
export const READ_TIMEOUT_MS = 2_500;

export async function readStoredRun(
  runId: string,
  {
    timeoutMs = READ_TIMEOUT_MS,
    maxChars = MAX_EMBEDDED_CHARS,
  }: { timeoutMs?: number; maxChars?: number } = {},
): Promise<StoredRun | null> {
  await connection();
  const cookie = (await headers()).get("cookie");
  let response: Response;
  try {
    response = await fetch(`${serverApiOrigin()}${API_PREFIX}/runs/${encodeURIComponent(runId)}`, {
      headers: { Accept: "application/json", ...(cookie ? { Cookie: cookie } : {}) },
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch {
    return null;
  }
  if (response.status === 404) return { kind: "not_found", runId };
  if (response.status === 410) return { kind: "gone", runId };
  if (!response.ok) return null;
  try {
    const length = Number(response.headers.get("content-length"));
    if (Number.isFinite(length) && length > maxChars) {
      await response.body?.cancel();
      return null;
    }
    const text = await response.text();
    if (text.length > maxChars) return null;
    const run = JSON.parse(text) as Run;
    return run.run_id === runId ? { kind: "run", run } : null;
  } catch {
    return null;
  }
}
