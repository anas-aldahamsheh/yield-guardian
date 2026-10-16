import type { RunEvent } from "@yield-guardian/contracts";

import { RUN_ID, sampleEvents, sseBody } from "../../../e2e/story/fixture";

import { reduceRunEvents, applyRunEvent, emptyRunState } from "./run-state";
import {
  RUN_GONE_MESSAGE,
  RUN_NOT_FOUND_MESSAGE,
  RunStreamError,
  createSseParser,
  followRun,
  parseRunEvent,
  runEventsUrl,
  type SseMessage,
} from "./sse";

function collect(chunks: string[]) {
  const messages: SseMessage[] = [];
  const retries: number[] = [];
  const parser = createSseParser(
    (m) => messages.push(m),
    (ms) => retries.push(ms),
  );
  for (const chunk of chunks) parser.push(chunk);
  parser.end();
  return { messages, retries };
}

describe("SSE parser", () => {
  it("reads events, ids and multi-line data", () => {
    const { messages } = collect([
      'event: alarm\nid: 4\ndata: {"a":\ndata: 1}\n\n: keep-alive\n\ndata: plain\n\n',
    ]);
    expect(messages).toEqual([
      { event: "alarm", data: '{"a":\n1}', id: "4" },
      { event: "message", data: "plain", id: "4" },
    ]);
  });

  it("handles chunks that split lines and CRLF anywhere", () => {
    const text = "event: run_done\r\nid: 9\r\ndata: x\r\n\r\nevent: alarm\rdata: y\r\r";
    for (let size = 1; size <= text.length; size += 1) {
      const chunks: string[] = [];
      for (let i = 0; i < text.length; i += size) chunks.push(text.slice(i, i + size));
      expect(collect(chunks).messages).toEqual([
        { event: "run_done", data: "x", id: "9" },
        { event: "alarm", data: "y", id: "9" },
      ]);
    }
  });

  it("reports retry, ignores unknown fields and a leading BOM", () => {
    const { messages, retries } = collect(["﻿retry: 2500\nretry: soon\nfoo: bar\ndata\n\n"]);
    expect(retries).toEqual([2500]);
    expect(messages).toEqual([{ event: "message", data: "", id: null }]);
  });

  it("drops a message the stream cut off", () => {
    expect(collect(["event: alarm\ndata: half"]).messages).toEqual([]);
  });
});

describe("parseRunEvent", () => {
  it("accepts run events whose type matches the SSE event", () => {
    const event = sampleEvents[0]!;
    expect(parseRunEvent({ event: event.type, data: JSON.stringify(event), id: "1" })).toEqual(
      event,
    );
  });

  it("refuses other events, bad JSON and mismatched types", () => {
    const event = sampleEvents[0]!;
    expect(parseRunEvent({ event: "message", data: JSON.stringify(event), id: null })).toBeNull();
    expect(parseRunEvent({ event: "alarm", data: JSON.stringify(event), id: null })).toBeNull();
    expect(parseRunEvent({ event: "run_started", data: "{nope", id: null })).toBeNull();
    expect(
      parseRunEvent({ event: "run_started", data: '{"type":"run_started"}', id: null }),
    ).toBeNull();
  });
});

/** A Response whose body arrives in the given chunks, then ends (or stays open). */
function streamResponse(chunks: string[], { hang = false } = {}): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      if (!hang) controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

function problemResponse(status: number, code: string) {
  return new Response(
    JSON.stringify({ type: "about:blank", title: "x", status, code, detail: "d" }),
    {
      status,
      headers: { "Content-Type": "application/problem+json" },
    },
  );
}

interface Harness {
  calls: { url: string; lastEventId: string | null }[];
  sleeps: number[];
  statuses: string[];
}

function follow(
  responses: (() => Response | Promise<Response>)[],
  extra: { signal?: AbortSignal } = {},
) {
  const harness: Harness = { calls: [], sleeps: [], statuses: [] };
  let state = emptyRunState(RUN_ID);
  let call = 0;
  const fetchStub = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const headers = new Headers(init?.headers);
    harness.calls.push({ url: String(url), lastEventId: headers.get("Last-Event-ID") });
    const next = responses[Math.min(call, responses.length - 1)]!;
    call += 1;
    return next();
  });
  const done = followRun({
    runId: RUN_ID,
    resumeFrom: () => state.contiguousSeq,
    onEvent: (event) => {
      state = applyRunEvent(state, event);
    },
    onStatus: (status) => harness.statuses.push(status),
    signal: extra.signal ?? new AbortController().signal,
    fetch: fetchStub as unknown as typeof fetch,
    initialDelayMs: 100,
    maxDelayMs: 1000,
    sleep: async (ms) => {
      harness.sleeps.push(ms);
    },
  });
  return { harness, done, state: () => state };
}

describe("followRun", () => {
  const events = sampleEvents as RunEvent[];
  const cut = 20;

  it("reads the whole run and stops after run_done", async () => {
    const { harness, done, state } = follow([
      () => streamResponse([sseBody(events)], { hang: true }),
    ]);
    await expect(done).resolves.toEqual({ finished: true });
    expect(harness.calls).toEqual([{ url: runEventsUrl(RUN_ID), lastEventId: null }]);
    expect(state().status).toBe("done");
    expect(harness.statuses).toEqual(["connecting", "streaming", "ended"]);
  });

  it("resumes with Last-Event-ID after a dropped connection and ends with the same state", async () => {
    const replayFrom = (seq: number) => events.filter((e) => e.seq > seq);
    const { harness, done, state } = follow([
      () => streamResponse([sseBody(events.slice(0, cut)).slice(0, -7)]), // cut mid-message
      () => {
        const from = Number(harness.calls.at(-1)!.lastEventId);
        return streamResponse([sseBody(replayFrom(from))]);
      },
    ]);
    await expect(done).resolves.toEqual({ finished: true });
    expect(harness.calls).toHaveLength(2);
    // The last message of the first connection was cut, so the resume point is the one before.
    expect(harness.calls[1]!.lastEventId).toBe(String(events[cut - 2]!.seq));
    expect(harness.sleeps).toEqual([100]);
    const whole = reduceRunEvents(RUN_ID, events);
    expect(state().stages).toEqual(whole.stages);
    expect(state().alarms).toEqual(whole.alarms);
  });

  it("tolerates a server that replays events it already sent", async () => {
    const { done, state } = follow([
      () => streamResponse([sseBody(events.slice(0, cut))]),
      () => streamResponse([sseBody(events)]), // ignores Last-Event-ID
    ]);
    await done;
    expect(state().arrivals).toEqual(reduceRunEvents(RUN_ID, events).arrivals);
  });

  it("backs off, doubling up to the maximum, and resets once events arrive", async () => {
    const fail = () => Promise.reject(new TypeError("Failed to fetch"));
    const { harness, done } = follow([
      fail,
      fail,
      () => new Response("", { status: 503 }),
      fail,
      fail,
      () => streamResponse([sseBody(events.slice(0, 3))]),
      () => streamResponse([sseBody(events)]),
    ]);
    await done;
    expect(harness.sleeps).toEqual([100, 200, 400, 800, 1000, 100]);
  });

  it("waits as long as a 503 asks (Retry-After) while the API wakes", async () => {
    const { harness, done } = follow([
      () => new Response("", { status: 503, headers: { "Retry-After": "3" } }),
      () => streamResponse([sseBody(events)]),
    ]);
    await expect(done).resolves.toEqual({ finished: true });
    expect(harness.sleeps).toEqual([3000]);
  });

  it("uses the server's retry time as the first pause", async () => {
    const { harness, done } = follow([
      () => streamResponse([sseBody(events.slice(0, 2), { retryMs: 3000 })]),
      () => streamResponse([sseBody(events)]),
    ]);
    await done;
    expect(harness.sleeps).toEqual([1000]); // capped by maxDelayMs
  });

  it("stops with the expiry message when the run is gone (410)", async () => {
    const { harness, done } = follow([() => problemResponse(410, "gone")]);
    const error = await done.catch((e: unknown) => e);
    expect(error).toBeInstanceOf(RunStreamError);
    expect((error as RunStreamError).kind).toBe("gone");
    expect((error as RunStreamError).message).toBe(RUN_GONE_MESSAGE);
    expect(RUN_GONE_MESSAGE).toBe("This run is no longer kept. Start a new one.");
    expect(harness.calls).toHaveLength(1);
  });

  it("stops on an unknown run (404) without retrying", async () => {
    const { harness, done } = follow([() => problemResponse(404, "not_found")]);
    await expect(done).rejects.toMatchObject({
      kind: "not_found",
      status: 404,
      message: RUN_NOT_FOUND_MESSAGE,
    });
    expect(harness.calls).toHaveLength(1);
  });

  it("ends quietly when the page aborts", async () => {
    const controller = new AbortController();
    const { done } = follow(
      [
        () => {
          queueMicrotask(() => controller.abort());
          return Promise.reject(new DOMException("aborted", "AbortError"));
        },
      ],
      { signal: controller.signal },
    );
    await expect(done).resolves.toEqual({ finished: false });
  });
});
