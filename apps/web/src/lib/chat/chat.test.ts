import type { ChatEvent } from "@yield-guardian/contracts";
import { describe, expect, it } from "vitest";

import { fixture } from "@/mocks/fixtures";

import { applyChatEvent, contextFromLocation, emptyAnswer, parseSse, segmentAnswer } from "./chat";

function streamOf(chunks: string[]) {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(c) {
      for (const chunk of chunks) c.enqueue(encoder.encode(chunk));
      c.close();
    },
  });
}

describe("parseSse", () => {
  it("joins frames split across chunks and skips comments", async () => {
    const frames = [];
    for await (const f of parseSse(streamOf([": keep-alive\n\nevent: tok", 'en\ndata: {"a":1}\n', "\nevent: done\r\ndata: {}\r\n\r\n"]))) frames.push(f);
    expect(frames).toEqual([
      { event: "token", data: '{"a":1}' },
      { event: "done", data: "{}" },
    ]);
  });
});

describe("applyChatEvent", () => {
  it("builds the fixture answer with its citation and done event", () => {
    const answer = fixture<ChatEvent[]>("chat").reduce(applyChatEvent, emptyAnswer());
    expect(answer.route?.route).toBe("deterministic");
    expect(answer.tools).toHaveLength(1);
    expect(answer.citations.map((c) => c.evidence_id)).toEqual(["E1"]);
    expect(answer.text).toContain("[E1]");
    expect(answer.done?.usage).toBeNull();
  });
  it("ignores a repeated citation", () => {
    const ev = fixture<ChatEvent[]>("chat").find((e) => e.type === "citation")!;
    expect([ev, ev].reduce(applyChatEvent, emptyAnswer()).citations).toHaveLength(1);
  });
});

describe("segmentAnswer", () => {
  it("separates citations, the unverified marker and flagged numbers", () => {
    const parts = segmentAnswer("Risk 18.4% [E1], then [unverified] and 7.2 here, not 17.2.", ["7.2"]);
    expect(parts.filter((p) => p.cite).map((p) => p.cite)).toEqual(["E1"]);
    expect(parts.some((p) => p.unverified)).toBe(true);
    expect(parts.filter((p) => p.flagged).map((p) => p.text)).toEqual(["7.2"]);
  });
});

describe("contextFromLocation", () => {
  it("reads the object on screen", () => {
    expect(contextFromLocation("/units/1062", new URLSearchParams())).toEqual({ unit_id: 1062 });
    expect(contextFromLocation("/sensors", new URLSearchParams("sensor=S060"))).toEqual({ sensor: "S060" });
    expect(contextFromLocation("/wafers", new URLSearchParams("wafer=lot1-2"))).toEqual({ wafer_id: "lot1-2" });
    expect(contextFromLocation("/line", new URLSearchParams())).toBeNull();
  });
});
