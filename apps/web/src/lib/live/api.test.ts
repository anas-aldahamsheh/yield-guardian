import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/errors";

import { NotReadyYet, getRunCases, retryWhenNotReady } from "./api";

const problem = {
  type: "about:blank",
  title: "Not ready",
  status: 503,
  detail: "Finding cases.",
  code: "not_ready",
};

function answer(status: number, body: unknown, headers: Record<string, string> = {}) {
  return async () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json", ...headers },
    });
}

describe("the runs API client", () => {
  it("waits as told while the case catalog is still being found", async () => {
    const error = await getRunCases({}, answer(503, problem, { "Retry-After": "5" })).catch(
      (e: unknown) => e,
    );
    expect(error).toBeInstanceOf(NotReadyYet);
    expect((error as NotReadyYet).retryAfterMs).toBe(5_000);
    expect(retryWhenNotReady.retry(3, error as Error)).toBe(true);
    expect(retryWhenNotReady.retryDelay(3, error as Error)).toBe(5_000);
  });

  it("treats a 503 without Retry-After as a failure", async () => {
    const error = await getRunCases({}, answer(503, problem)).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).not.toBeInstanceOf(NotReadyYet);
    expect(retryWhenNotReady.retry(1, error as Error)).toBe(false);
  });
});
