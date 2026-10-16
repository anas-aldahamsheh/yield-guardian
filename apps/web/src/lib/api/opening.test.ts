import type { SessionInfo } from "@yield-guardian/contracts";

import { createRun } from "@/lib/live/api";

import { ApiError } from "./errors";
import { forgetOpening, openWorkspace, readSession, workspaceReady } from "./opening";
import { MAX_RETRIES, withRetry } from "./retry";

/**
 * Opening this device's workspace (POST /session/workspace) on the first visit, the API asleep
 * included: it waits for the API as every read does, and what is made meanwhile waits for it.
 */

const OPENED: SessionInfo = {
  role: "visitor",
  display_name: null,
  expires_at: null,
  csrf_token: "test-csrf",
  workspace: {
    workspace_id: "0b8f3c1e-6a52-4c47-9d0e-2f8a1b7c4d55",
    session_expires_at: "2026-11-14T09:00:00Z",
  },
};

const NO_WORKSPACE: SessionInfo = { ...OPENED, csrf_token: null, workspace: null };

const opened = () =>
  new Response(JSON.stringify(OPENED), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });

/** The proxy in front of a sleeping API: 503 with Retry-After, and no problem of the API's own. */
const asleep = (retryAfter = "1") =>
  new Response("Starting.", {
    status: 503,
    headers: { "Content-Type": "text/plain", "Retry-After": retryAfter },
  });

/** A problem of the API's own (RFC 9457), as it answers it. */
const problem = (status: number, code: string, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify({ title: "Refused", status, code, detail: "As the API says." }), {
    status,
    headers: { "Content-Type": "application/problem+json", ...headers },
  });

/** fetch answering each request with the next answer: a response, a promise of one, or an error. */
function answers(...queue: (Response | Promise<Response> | Error)[]) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
    const next = queue.shift();
    if (next === undefined) throw new Error("The test has no answer left for this request.");
    if (next instanceof Error) throw next;
    return next;
  });
}

beforeEach(() => {
  // The waits are timers; reading a response is not.
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
  forgetOpening();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("opening this device's workspace", () => {
  it("asks the API once per page load, however many callers wait for it", async () => {
    const fetch = answers(opened());
    const [a, b] = await Promise.all([openWorkspace(), openWorkspace(), workspaceReady()]);
    expect(a).toEqual(OPENED);
    expect(b).toBe(a);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0]![0]).toBe("/api/v1/session/workspace");
    expect(fetch.mock.calls[0]![1]).toMatchObject({ method: "POST", credentials: "include" });
  });

  it("asks again when no answer came and on a 503, as long as its Retry-After says", async () => {
    const fetch = answers(new TypeError("Failed to fetch"), asleep("3"), opened());
    const session = openWorkspace();
    await vi.advanceTimersByTimeAsync(999);
    expect(fetch).toHaveBeenCalledTimes(1);
    // No answer names no wait: the first wait of every read, a second.
    await vi.advanceTimersByTimeAsync(1);
    expect(fetch).toHaveBeenCalledTimes(2);
    // The proxy asked for 3 seconds, longer than the 2 the next wait would be.
    await vi.advanceTimersByTimeAsync(2_999);
    expect(fetch).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(1);
    expect(fetch).toHaveBeenCalledTimes(3);
    await expect(session).resolves.toEqual(OPENED);
  });

  it("asks again while the proxy in front answers for the API: a 502, 503 or 504 of its own", async () => {
    const proxy = (status: number) =>
      new Response("The API did not answer.", {
        status,
        headers: { "Content-Type": "text/plain" },
      });
    const fetch = answers(proxy(502), proxy(504), proxy(503), opened());
    const session = openWorkspace();
    // 1 + 2 + 4 seconds of waiting, as for any read.
    await vi.advanceTimersByTimeAsync(6_999);
    expect(fetch).toHaveBeenCalledTimes(3);
    await vi.advanceTimersByTimeAsync(1);
    await expect(session).resolves.toEqual(OPENED);
    expect(fetch).toHaveBeenCalledTimes(4);
  });

  it("waits for the API's own 503 while it starts, which names its wait", async () => {
    const fetch = answers(problem(503, "not_ready", { "Retry-After": "2" }), opened());
    const session = openWorkspace();
    await vi.advanceTimersByTimeAsync(1_999);
    expect(fetch).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    await expect(session).resolves.toEqual(OPENED);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("keeps the session loading while it waits: the first read is the opening's answer", async () => {
    const fetch = answers(asleep(), asleep(), opened());
    const read = vi.fn(async () => NO_WORKSPACE);
    const session = readSession(read);
    const settled = vi.fn();
    void session.then(settled);
    await vi.advanceTimersByTimeAsync(2_999);
    expect(settled).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    await expect(session).resolves.toEqual(OPENED);
    expect(read).not.toHaveBeenCalled();
    expect(fetch).toHaveBeenCalledTimes(3);
  });

  it("gives up as late as every read does, and the page goes on without a workspace", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async () => asleep());
    const read = vi.fn(async () => NO_WORKSPACE);
    const session = readSession(read);
    // 1 + 2 + 4 + 8 × 11 seconds of waiting, as for any read (lib/api/retry.ts).
    await vi.advanceTimersByTimeAsync(94_999);
    expect(read).not.toHaveBeenCalled();
    expect(fetch).toHaveBeenCalledTimes(MAX_RETRIES);
    await vi.advanceTimersByTimeAsync(1);
    await expect(session).resolves.toEqual(NO_WORKSPACE);
    expect(fetch).toHaveBeenCalledTimes(MAX_RETRIES + 1);
    expect(read).toHaveBeenCalledTimes(1);
    await expect(openWorkspace()).resolves.toBeNull();
    await expect(workspaceReady({ refuseWhileWaking: true })).resolves.toBeUndefined();
  });

  it.each([
    ["a 403", () => problem(403, "forbidden")],
    ["a 404", () => problem(404, "not_found")],
    ["the API's own 500", () => problem(500, "internal_error")],
    ["the API's own 502", () => problem(502, "upstream_error")],
    ["the API's own 503 when it keeps no workspaces", () => problem(503, "not_ready")],
  ])("takes %s as the answer, and asks no more", async (_, answer) => {
    const fetch = answers(answer());
    await expect(openWorkspace()).resolves.toBeNull();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});

describe("what is made while the API wakes", () => {
  it("is refused while the opening waits for the API, and waits for its request on the way", async () => {
    let answer!: (response: Response) => void;
    const fetch = answers(
      asleep("2"),
      new Promise<Response>((resolve) => {
        answer = resolve;
      }),
    );
    // The first request is on its way: a run waits for its answer, which is that the API wakes.
    await expect(workspaceReady({ refuseWhileWaking: true })).rejects.toMatchObject({
      status: 503,
      problem: null,
      retryAfterMs: 2_000,
    });
    // An upload waits for the workspace instead.
    const upload = vi.fn();
    void workspaceReady().then(upload);
    await vi.advanceTimersByTimeAsync(500);
    const again = await workspaceReady({ refuseWhileWaking: true }).catch((e: unknown) => e);
    expect(again).toBeInstanceOf(ApiError);
    expect(again).toMatchObject({ status: 503, retryAfterMs: 1_500 });

    // The opening asks again: a run asked for now waits for that answer.
    await vi.advanceTimersByTimeAsync(1_500);
    expect(fetch).toHaveBeenCalledTimes(2);
    const run = vi.fn();
    void workspaceReady({ refuseWhileWaking: true }).then(run);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(run).not.toHaveBeenCalled();
    expect(upload).not.toHaveBeenCalled();
    answer(opened());
    await vi.waitFor(() => expect(run).toHaveBeenCalledTimes(1));
    expect(upload).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("starts a run only once the workspace is open, saying meanwhile that the API wakes", async () => {
    answers(asleep(), asleep(), opened());
    const post = vi.fn<typeof fetch>(async () => new Response("{}", { status: 201 }));
    const waiting = vi.fn();
    // As the Line page starts a run: a 503 means the service is starting, and it asks again.
    const started = withRetry(() => createRun({ source: "sample", seed: null }, {}, post), {
      retryIf: (error) => error instanceof ApiError && error.status === 503,
      onWaiting: waiting,
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(waiting).toHaveBeenCalled();
    expect(post).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(10_000);
    await expect(started).resolves.toEqual({});
    expect(post).toHaveBeenCalledTimes(1);
    expect(post.mock.calls[0]![0]).toBe("/api/v1/runs");
  });
});
