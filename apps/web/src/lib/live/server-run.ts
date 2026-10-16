import "server-only";

import { API_PREFIX, type Run } from "@yield-guardian/contracts";
import { connection } from "next/server";

import { serverApiOrigin } from "@/lib/api/config";
import { sessionCookieHeader } from "@/lib/api/server";

import { glanceOf, type GlanceView } from "./glance";
import { pack } from "./packed";
import type { StoredRun } from "./stored-run";

/**
 * The run's stored state as the API holds it, read by the Next.js server while it renders the
 * Line page, so the first paint already shows every result. What goes into the page is its
 * compact form (lib/live/glance.ts), packed (lib/live/packed.ts): about 100 KB for the largest
 * real sample, whose full state is 4.6 MB, and under 0.4 MB for all 1,567 SECOM units (7.9 MB),
 * so any run is in the first paint and the page stays light.
 *
 * The request carries the visitor's session cookie and no other cookie of theirs (as every
 * server-side read does: lib/api/server.ts), since a run is visible only to its workspace: another
 * workspace's run reads as not found, exactly as an ID that never existed. The API it goes to is
 * API_INTERNAL_URL, never an address from the request. No answer within `timeoutMs` (the API
 * asleep or starting) leaves the reading to the browser, which says so and waits; once the API
 * has answered, its body has `bodyTimeoutMs`.
 */

export const READ_TIMEOUT_MS = 2_500;
export const BODY_TIMEOUT_MS = 10_000;
/** A guard on what the server parses, far above any run the API makes (the largest are ~20 MB). */
export const MAX_READ_CHARS = 128_000_000;

export async function readStoredRun(
  runId: string,
  view: GlanceView,
  {
    timeoutMs = READ_TIMEOUT_MS,
    bodyTimeoutMs = BODY_TIMEOUT_MS,
    maxChars = MAX_READ_CHARS,
  }: { timeoutMs?: number; bodyTimeoutMs?: number; maxChars?: number } = {},
): Promise<StoredRun | null> {
  await connection();
  const cookie = await sessionCookieHeader();
  const controller = new AbortController();
  let timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(
      `${serverApiOrigin()}${API_PREFIX}/runs/${encodeURIComponent(runId)}`,
      {
        headers: { Accept: "application/json", ...cookie },
        cache: "no-store",
        signal: controller.signal,
      },
    );
    clearTimeout(timer);
    timer = setTimeout(() => controller.abort(), bodyTimeoutMs);
    if (response.status === 404) return { kind: "not_found", runId };
    if (response.status === 410) return { kind: "gone", runId };
    if (!response.ok) return null;
    const length = Number(response.headers.get("content-length"));
    if (Number.isFinite(length) && length > maxChars) {
      await response.body?.cancel();
      return null;
    }
    const text = await response.text();
    if (text.length > maxChars) return null;
    const run = JSON.parse(text) as Run;
    if (run.run_id !== runId) return null;
    const glance = glanceOf(run, view);
    return { kind: "run", runId, packed: pack(glance.run), partial: glance.partial };
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}
