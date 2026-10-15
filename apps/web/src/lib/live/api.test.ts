import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/errors";
import { retryDelay, shouldRetry } from "@/lib/api/retry";

import { NotReadyYet, getRun, getRunCases } from "./api";

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
  it("waits at least as long as told while the case catalog is still being found", async () => {
    const error = await getRunCases({}, answer(503, problem, { "Retry-After": "5" })).catch(
      (e: unknown) => e,
    );
    expect(error).toBeInstanceOf(NotReadyYet);
    expect((error as NotReadyYet).retryAfterMs).toBe(5_000);
    expect(shouldRetry(3, error)).toBe(true);
    expect(retryDelay(0, error)).toBe(5_000);
    // Later tries wait longer still: the pause doubles past what was asked.
    expect(retryDelay(3, error)).toBe(8_000);
  });

  it("waits with a growing pause on a 503 without Retry-After", async () => {
    const error = await getRunCases({}, answer(503, problem)).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).not.toBeInstanceOf(NotReadyYet);
    expect(shouldRetry(1, error)).toBe(true);
    expect(retryDelay(1, error)).toBe(2_000);
  });

  it("never asks again after a 4xx", async () => {
    const missing = { ...problem, title: "Not found", status: 404, code: "not_found" };
    const error = await getRun("run_01jaf3k9x2m4q7r8s0t1v2w3x4", {}, answer(404, missing)).catch(
      (e: unknown) => e,
    );
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(404);
    expect(shouldRetry(0, error)).toBe(false);
  });
});
