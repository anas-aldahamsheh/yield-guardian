import type { RunEvent } from "@yield-guardian/contracts";
import { act, renderHook, waitFor } from "@testing-library/react";

import { RUN_ID, sampleEvents, snapshotOf, sseBody } from "../../../e2e/story/fixture";

import { runEventsUrl } from "./sse";
import type { StoredRun } from "./stored-run";
import { RUN_NOT_FOUND_MESSAGE, forgetShownRuns, useRun, type RunHandle } from "./use-run";

/**
 * What the run reader asks the API for after a reload, a link and back and forward: the stored
 * state the server put in the page is shown from the first render, and the browser asks only
 * for what came after it.
 */

interface Call {
  url: string;
  lastEventId: string | null;
}

const events = sampleEvents as RunEvent[];
const runUrl = `/api/v1/runs/${RUN_ID}`;

function stream(list: readonly RunEvent[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(sseBody(list)));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

/** fetch answered by `answer`, recording each request. */
function api(answer: (call: Call, n: number) => Response | Promise<Response>) {
  const calls: Call[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input instanceof Request ? input.url : input);
    const call = { url, lastEventId: new Headers(init?.headers).get("Last-Event-ID") };
    calls.push(call);
    return answer(call, calls.length);
  });
  return calls;
}

function stored(list: readonly RunEvent[]): StoredRun {
  return { kind: "run", run: snapshotOf(list) };
}

/** Lets pending effects, requests and stream reads settle. */
async function settle() {
  await act(async () => {
    for (let i = 0; i < 5; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

beforeEach(() => {
  forgetShownRuns();
});

describe("useRun after a reload", () => {
  it("shows a finished stored run from the first render and asks the API nothing", async () => {
    const calls = api(() => json({}, 500));
    const seen: RunHandle[] = [];
    renderHook(() => {
      const handle = useRun(RUN_ID, { fresh: false, stored: stored(events) });
      seen.push(handle);
      return handle;
    });
    await settle();
    const first = seen[0]!;
    expect(first.state?.status).toBe("done");
    expect(first.connection).toBe("ended");
    expect(first.state?.arrivals).toEqual([]);
    expect(first.state?.alarms.length).toBeGreaterThan(0);
    // Never an empty or "connecting" state on the way.
    expect(seen.every((h) => h.state?.status === "done" && h.connection === "ended")).toBe(true);
    expect(calls).toEqual([]);
  });

  it("follows a stored running run from right after its last event", async () => {
    const cut = 14;
    const snapshot = stored(events.slice(0, cut));
    const calls = api((call) => {
      if (call.url === runEventsUrl(RUN_ID))
        return stream(events.filter((e) => e.seq > Number(call.lastEventId)));
      if (call.url === runUrl) return json(snapshotOf(events));
      return json({}, 404);
    });
    const seen: RunHandle[] = [];
    const { result } = renderHook(() => {
      const handle = useRun(RUN_ID, { fresh: false, stored: snapshot });
      seen.push(handle);
      return handle;
    });
    expect(seen[0]!.state?.status).toBe("running");
    expect(seen[0]!.state?.stages.intake.status).toBe("done");
    await waitFor(() => expect(result.current.state?.status).toBe("done"));
    const streams = calls.filter((c) => c.url === runEventsUrl(RUN_ID));
    expect(streams).toEqual([
      { url: runEventsUrl(RUN_ID), lastEventId: String(events[cut - 1]!.seq) },
    ]);
    // Only what came after the stored state arrives as new.
    const after = events.filter((e) => e.seq > events[cut - 1]!.seq);
    expect(result.current.state!.arrivals.map((a) => a.seq)).toEqual(
      after.filter((e) => ["stage_result", "alarm", "run_done"].includes(e.type)).map((e) => e.seq),
    );
    // No snapshot was read before the stream: the page already had it.
    expect(calls.findIndex((c) => c.url === runUrl)).toBeGreaterThan(
      calls.findIndex((c) => c.url === runEventsUrl(RUN_ID)),
    );
  });

  it("shows a run of another workspace as not found at once, and asks nothing more", async () => {
    const calls = api(() => json({}, 500));
    const seen: RunHandle[] = [];
    renderHook(() => {
      const handle = useRun(RUN_ID, {
        fresh: false,
        stored: { kind: "not_found", runId: RUN_ID },
      });
      seen.push(handle);
      return handle;
    });
    await settle();
    expect(seen[0]!.problem).toEqual({ kind: "not_found", message: RUN_NOT_FOUND_MESSAGE });
    expect(seen.every((h) => h.connection === "ended")).toBe(true);
    expect(calls).toEqual([]);
  });

  it("reads a run the page did not carry, waiting while the API wakes (503)", async () => {
    let reads = 0;
    const calls = api((call) => {
      if (call.url !== runUrl) return json({}, 404);
      reads += 1;
      return reads === 1
        ? new Response("", { status: 503, headers: { "Retry-After": "0" } })
        : json(snapshotOf(events));
    });
    const seen: RunHandle[] = [];
    const { result } = renderHook(() => {
      const handle = useRun(RUN_ID, { fresh: false, stored: null });
      seen.push(handle);
      return handle;
    });
    expect(seen[0]!.connection).toBe("loading");
    await waitFor(() => expect(result.current.connection).toBe("waking"));
    await waitFor(() => expect(result.current.state?.status).toBe("done"), { timeout: 3000 });
    expect(result.current.connection).toBe("ended");
    expect(result.current.state!.arrivals).toEqual([]);
    expect(calls.map((c) => c.url)).toEqual([runUrl, runUrl]);
  });

  it("says not found when the API answers 404, without asking again", async () => {
    const calls = api(() =>
      json({ type: "about:blank", title: "Not found", status: 404, code: "not_found" }, 404),
    );
    const { result } = renderHook(() => useRun(RUN_ID, { fresh: false }));
    await waitFor(() => expect(result.current.problem?.kind).toBe("not_found"));
    expect(result.current.connection).toBe("ended");
    expect(calls).toHaveLength(1);
  });

  it("shows a run again as it was after going back to it, with nothing replayed", async () => {
    const calls = api((call) => (call.url === runUrl ? json(snapshotOf(events)) : json({}, 404)));
    const { result, rerender } = renderHook(
      ({ id }: { id: string | null }) => useRun(id, { fresh: false, stored: stored(events) }),
      { initialProps: { id: RUN_ID as string | null } },
    );
    await settle();
    expect(result.current.state?.status).toBe("done");
    rerender({ id: null });
    expect(result.current.state).toBeNull();
    rerender({ id: RUN_ID });
    // At once, as it stood: no reading state and nothing queued to play.
    expect(result.current.state?.status).toBe("done");
    expect(result.current.connection).toBe("ended");
    expect(result.current.state?.arrivals).toEqual([]);
    await settle();
    // One quiet read for an investigation started from it since, and no stream.
    expect(calls.map((c) => c.url)).toEqual([runUrl]);
  });

  it("keeps an investigation started from an alarm, with its status", async () => {
    api(() => json({}, 500));
    const { result } = renderHook(() => useRun(RUN_ID, { fresh: false, stored: stored(events) }));
    await settle();
    const alarm = result.current.state!.alarms[0]!;
    act(() => result.current.linkInvestigation(alarm.alarm_id, "inv_1", "queued"));
    expect(result.current.state!.alarms[0]).toMatchObject({
      investigation_id: "inv_1",
      investigation_status: "queued",
    });
  });
});

describe("useRun for a run this page started", () => {
  it("plays every result as it arrives, then reads the expiry once", async () => {
    const calls = api((call) =>
      call.url === runEventsUrl(RUN_ID) ? stream(events) : json(snapshotOf(events)),
    );
    const { result } = renderHook(() => useRun(RUN_ID, { fresh: true }));
    expect(result.current.connection).toBe("connecting");
    await waitFor(() => expect(result.current.state?.status).toBe("done"));
    expect(result.current.state!.arrivals.filter((a) => a.kind === "result")).toHaveLength(8);
    await waitFor(() => expect(calls.map((c) => c.url)).toEqual([runEventsUrl(RUN_ID), runUrl]));
    expect(calls[0]!.lastEventId).toBeNull();
  });

  it("is shown at rest after going back and forward to it: what played is not queued again", async () => {
    const calls = api((call) =>
      call.url === runEventsUrl(RUN_ID) ? stream(events) : json(snapshotOf(events)),
    );
    const seen: RunHandle[] = [];
    const { result, rerender } = renderHook(
      ({ id, fresh }: { id: string | null; fresh: boolean }) => {
        const handle = useRun(id, { fresh });
        seen.push(handle);
        return handle;
      },
      { initialProps: { id: RUN_ID as string | null, fresh: true } },
    );
    await waitFor(() => expect(result.current.state?.status).toBe("done"));
    await settle();
    expect(result.current.state!.arrivals.length).toBeGreaterThan(0);
    rerender({ id: null, fresh: false });
    expect(result.current.state).toBeNull();
    const from = seen.length;
    rerender({ id: RUN_ID, fresh: false });
    // From the first render back: the run as it stood, with no arrival left to play.
    expect(seen.slice(from).every((h) => h.state?.arrivals.length === 0)).toBe(true);
    expect(result.current.state?.status).toBe("done");
    expect(result.current.connection).toBe("ended");
    await settle();
    expect(seen.slice(from).every((h) => h.state?.arrivals.length === 0)).toBe(true);
    // No stream again: one quiet read for an investigation started from it since.
    expect(calls.filter((c) => c.url === runEventsUrl(RUN_ID))).toHaveLength(1);
  });
});
