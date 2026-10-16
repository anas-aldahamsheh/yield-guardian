import { ApiError } from "./errors";

/**
 * One way to wait for the API, for every read the browser makes.
 *
 * The deployed API can be asleep: the first requests after a quiet spell wait while it wakes,
 * and while it loads its models and finds the case catalog it answers 503 with Retry-After. So
 * a read that got no answer (status 0), a server error (5xx) or "not ready" (503) is tried
 * again: after 1, 2, 4 and then 8 seconds, or later when the Retry-After the API gave is longer,
 * for about a minute and a half in all. A wake of a minute costs a read about ten tries, however
 * short the Retry-After. Any 4xx is an answer (not found, gone, not allowed) and is never tried
 * again.
 */

/** Tries after the first failure: 1 + 2 + 4 + 8 × 11 seconds is about 95 s of waiting. */
export const MAX_RETRIES = 14;
const FIRST_DELAY_MS = 1_000;
const MAX_DELAY_MS = 8_000;
/** Retry-After is honoured within these bounds, so a wrong header neither spins nor stalls. */
const RETRY_AFTER_BOUNDS: [number, number] = [500, 30_000];

/** A Retry-After header (seconds or an HTTP date) in ms, or null when there is none. */
export function retryAfterMs(header: string | null, now = Date.now()): number | null {
  if (!header) return null;
  const trimmed = header.trim();
  const ms = /^\d+(\.\d+)?$/.test(trimmed) ? Number(trimmed) * 1000 : Date.parse(trimmed) - now;
  if (!Number.isFinite(ms)) return null;
  return Math.min(RETRY_AFTER_BOUNDS[1], Math.max(RETRY_AFTER_BOUNDS[0], ms));
}

/** The API may answer next time: it did not answer, or failed on its side. */
export function isRetryable(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 0 || error.status >= 500);
}

/** For TanStack Query's `retry`: `failures` counts the failures before this one (0 first). */
export function shouldRetry(failures: number, error: unknown): boolean {
  return isRetryable(error) && failures < MAX_RETRIES;
}

/** For TanStack Query's `retryDelay`: a doubling wait, never shorter than what the API asked. */
export function retryDelay(failures: number, error: unknown): number {
  const asked = error instanceof ApiError ? error.retryAfterMs : null;
  return Math.max(asked ?? 0, Math.min(MAX_DELAY_MS, FIRST_DELAY_MS * 2 ** Math.max(0, failures)));
}

/** Waits `ms`, or less when the signal aborts. */
export function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal?.aborted) return resolve();
    const done = () => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", done);
      resolve();
    };
    const timer = setTimeout(done, ms);
    signal?.addEventListener("abort", done, { once: true });
  });
}

/**
 * Calls `read` until it answers, with the policy above, outside TanStack Query (the run reader).
 * `onWaiting` hears each wait, with the error that caused it. `retryIf` narrows which failures
 * are asked again: a write is sent again only on a 503, which the API (or the proxy in front of
 * it while it wakes) answers without having done anything.
 */
export async function withRetry<T>(
  read: () => Promise<T>,
  {
    signal,
    onWaiting,
    retryIf = isRetryable,
    wait = sleep,
  }: {
    signal?: AbortSignal;
    onWaiting?: (error: unknown, failures: number) => void;
    retryIf?: (error: unknown) => boolean;
    wait?: (ms: number, signal?: AbortSignal) => Promise<void>;
  } = {},
): Promise<T> {
  for (let failures = 0; ; failures += 1) {
    try {
      return await read();
    } catch (error) {
      if (signal?.aborted || failures >= MAX_RETRIES || !retryIf(error) || !isRetryable(error))
        throw error;
      onWaiting?.(error, failures);
      await wait(retryDelay(failures, error), signal);
      if (signal?.aborted) throw new DOMException("The read was stopped.", "AbortError");
    }
  }
}
