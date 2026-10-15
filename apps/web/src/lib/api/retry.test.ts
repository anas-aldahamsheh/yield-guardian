import { ApiError } from "./errors";
import { MAX_RETRIES, retryAfterMs, retryDelay, shouldRetry, withRetry } from "./retry";

const noAnswer = new ApiError(0, null, "Failed to fetch");
const waking = new ApiError(503, null, undefined, 4_000);
const broken = new ApiError(502, null);
const notFound = new ApiError(404, {
  type: "about:blank",
  title: "Not found",
  status: 404,
  code: "not_found",
});

describe("the retry policy", () => {
  it("reads Retry-After in seconds or as a date, within bounds", () => {
    expect(retryAfterMs(null)).toBeNull();
    expect(retryAfterMs("soon")).toBeNull();
    expect(retryAfterMs("3")).toBe(3_000);
    expect(retryAfterMs("1.5")).toBe(1_500);
    expect(retryAfterMs("0")).toBe(500);
    expect(retryAfterMs("86400")).toBe(30_000);
    const now = Date.parse("2026-10-15T12:00:00Z");
    expect(retryAfterMs("Thu, 15 Oct 2026 12:00:10 GMT", now)).toBe(10_000);
  });

  it("asks again after no answer or a server error, never after a 4xx", () => {
    expect(shouldRetry(0, noAnswer)).toBe(true);
    expect(shouldRetry(0, waking)).toBe(true);
    expect(shouldRetry(0, broken)).toBe(true);
    expect(shouldRetry(0, notFound)).toBe(false);
    expect(shouldRetry(0, new ApiError(410, null))).toBe(false);
    expect(shouldRetry(0, new Error("render"))).toBe(false);
    expect(shouldRetry(MAX_RETRIES - 1, noAnswer)).toBe(true);
    expect(shouldRetry(MAX_RETRIES, noAnswer)).toBe(false);
  });

  it("waits 1, 2, 4 and then 8 seconds, or as long as the API asked when that is longer", () => {
    expect([0, 1, 2, 3, 4, 9].map((n) => retryDelay(n, noAnswer))).toEqual([
      1_000, 2_000, 4_000, 8_000, 8_000, 8_000,
    ]);
    expect([0, 1, 2, 3].map((n) => retryDelay(n, waking))).toEqual([4_000, 4_000, 4_000, 8_000]);
    // A short Retry-After does not make the tries come faster.
    const soon = new ApiError(503, null, undefined, 500);
    expect([0, 1, 2].map((n) => retryDelay(n, soon))).toEqual([1_000, 2_000, 4_000]);
  });

  it("asks about ten times while the API wakes for a minute", () => {
    const soon = new ApiError(503, null, undefined, 1_000);
    let waited = 0;
    let tries = 1;
    while (waited < 60_000) {
      waited += retryDelay(tries - 1, soon);
      tries += 1;
    }
    expect(tries).toBeLessThanOrEqual(11);
  });

  it("waits about a minute and a half in all before giving up", () => {
    let total = 0;
    for (let n = 0; n < MAX_RETRIES; n += 1) total += retryDelay(n, noAnswer);
    expect(total).toBeGreaterThanOrEqual(90_000);
    expect(total).toBeLessThanOrEqual(100_000);
  });
});

describe("withRetry", () => {
  it("asks until the API answers, saying each wait", async () => {
    const answers = [waking, noAnswer, "ok"];
    const waits: number[] = [];
    const heard: unknown[] = [];
    const result = await withRetry(
      async () => {
        const next = answers.shift();
        if (next instanceof Error) throw next;
        return next;
      },
      { wait: async (ms) => void waits.push(ms), onWaiting: (error) => heard.push(error) },
    );
    expect(result).toBe("ok");
    expect(waits).toEqual([4_000, 2_000]);
    expect(heard).toEqual([waking, noAnswer]);
  });

  it("gives up at once on a 4xx", async () => {
    const read = vi.fn(async () => {
      throw notFound;
    });
    await expect(withRetry(read, { wait: async () => {} })).rejects.toBe(notFound);
    expect(read).toHaveBeenCalledTimes(1);
  });

  it("sends a write again only on what retryIf allows (a 503)", async () => {
    const only503 = (e: unknown) => e instanceof ApiError && e.status === 503;
    const write = vi.fn(async () => {
      throw noAnswer;
    });
    await expect(withRetry(write, { retryIf: only503, wait: async () => {} })).rejects.toBe(
      noAnswer,
    );
    expect(write).toHaveBeenCalledTimes(1);
    let n = 0;
    const second = await withRetry(
      async () => {
        n += 1;
        if (n === 1) throw waking;
        return n;
      },
      { retryIf: only503, wait: async () => {} },
    );
    expect(second).toBe(2);
  });

  it("stops after the last try", async () => {
    const read = vi.fn(async () => {
      throw broken;
    });
    await expect(withRetry(read, { wait: async () => {} })).rejects.toBe(broken);
    expect(read).toHaveBeenCalledTimes(MAX_RETRIES + 1);
  });

  it("stops when the page aborts", async () => {
    const controller = new AbortController();
    const read = vi.fn(async () => {
      controller.abort();
      throw noAnswer;
    });
    await expect(withRetry(read, { signal: controller.signal })).rejects.toBe(noAnswer);
    expect(read).toHaveBeenCalledTimes(1);
  });
});
