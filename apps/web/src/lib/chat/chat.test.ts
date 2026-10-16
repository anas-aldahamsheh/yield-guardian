import type { ChatEvent } from "@yield-guardian/contracts";
import { describe, expect, it } from "vitest";

import { fixture } from "@/mocks/fixtures";

import {
  applyChatEvent,
  contextFromLocation,
  describeContext,
  emptyAnswer,
  extractVisiblePageContent,
  formatAnswerMarkdown,
  lineChatContext,
  parseLineLocation,
  parseSse,
  runChatContext,
  segmentAnswer,
} from "./chat";

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
    for await (const f of parseSse(
      streamOf([
        ": keep-alive\n\nevent: tok",
        'en\ndata: {"a":1}\n',
        "\nevent: done\r\ndata: {}\r\n\r\n",
      ]),
    ))
      frames.push(f);
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
  it("keeps each offered investigation once", () => {
    // A test input in the contract's shape.
    const offer: ChatEvent = {
      type: "suggestion",
      action: "start_investigation",
      trigger: { kind: "run_alarm", ref: "run_01jb2c3d4e:RA-3" },
      title: "Alarm RA-3 of this run",
    };
    const answer = [offer, offer].reduce(applyChatEvent, emptyAnswer());
    expect(answer.offers).toEqual([{ trigger: offer.trigger, title: offer.title }]);
    expect(emptyAnswer().offers).toEqual([]);
  });
});

describe("segmentAnswer", () => {
  it("separates citations, the unverified marker and flagged numbers", () => {
    const parts = segmentAnswer("Risk 18.4% [E1], then [unverified] and 7.2 here, not 17.2.", [
      "7.2",
    ]);
    expect(parts.filter((p) => p.cite).map((p) => p.cite)).toEqual(["E1"]);
    expect(parts.some((p) => p.unverified)).toBe(true);
    expect(parts.filter((p) => p.flagged).map((p) => p.text)).toEqual(["7.2"]);
  });
});

describe("formatAnswerMarkdown", () => {
  it("encodes citations, unverified marks, and flagged numbers into custom anchor schemas", () => {
    const raw = "### Wafer Pattern\nEdge-Ring pattern observed [E1]. Yield: 98.4% [unverified], sensor drift at 42.5.";
    const formatted = formatAnswerMarkdown(raw, ["42.5"]);
    expect(formatted).toContain("[E1](#cite:E1)");
    expect(formatted).toContain("[unverified](#unverified)");
    expect(formatted).toContain("[42.5](#flagged:42.5)");
    expect(formatted).toContain("### Wafer Pattern");
  });
});

describe("parseLineLocation", () => {
  const parse = (query: string) => parseLineLocation(new URLSearchParams(query));

  it("reads the run, the station and the item of the Line's address", () => {
    expect(parse("run=run_01jb2c3d4e&station=2&unit=14")).toEqual({
      runId: "run_01jb2c3d4e",
      station: 2,
      item: { kind: "unit", index: 14 },
      alarm: null,
      pick: null,
      sensor: null,
    });
    expect(parse("run=run_01jb2c3d4e&station=3&wafer=0").item).toEqual({ kind: "wafer", index: 0 });
    expect(parse("run=run_01jb2c3d4e&station=3&lot=lot47542").item).toEqual({
      kind: "lot",
      lot: "lot47542",
    });
  });

  it("drops values that are not well formed", () => {
    expect(parse("run=inv_123&station=9&unit=-1&wafer=x&lot=&alarm=AL-1")).toEqual({
      runId: null,
      station: null,
      item: null,
      alarm: null,
      pick: null,
      sensor: null,
    });
    expect(parse("station=0").station).toBeNull();
    expect(parse("station=2.5").station).toBeNull();
    expect(parse("sensor=S06").sensor).toBeNull();
  });

  it("reads the run's alarm", () => {
    expect(parse("run=run_01jb2c3d4e&station=4&alarm=RA-3").alarm).toBe("RA-3");
    expect(parse("alarm=RA-").alarm).toBeNull();
  });

  it("reads a pick and a sensor from v1 links", () => {
    expect(parse("pick=unit:1062").pick).toEqual({ kind: "unit", id: 1062 });
    expect(parse("station=2&sensor=S060").sensor).toBe("S060");
  });
});

describe("run chat context", () => {
  const line = parseLineLocation(
    new URLSearchParams("run=run_01jb2c3d4e&station=3&wafer=4&pick=unit:1062"),
  );

  it("maps the run part to ChatContext's run fields", () => {
    expect(runChatContext(line)).toEqual({
      run_id: "run_01jb2c3d4e",
      station: "wafer_test",
      run_unit: null,
      run_wafer: 4,
      run_lot: null,
      run_alarm: null,
    });
    expect(runChatContext(parseLineLocation(new URLSearchParams("station=2")))).toBeNull();
  });

  it("sends the run before the item a v1 link picked", () => {
    expect(lineChatContext(line)).toEqual(runChatContext(line));
    expect(lineChatContext(parseLineLocation(new URLSearchParams("pick=unit:1062")))).toEqual({
      unit_id: 1062,
    });
  });

  it("describes a run context in words", () => {
    expect(describeContext(lineChatContext(line)!)).toBe("This run, Wafer test, wafer 5");
    const alarm = parseLineLocation(new URLSearchParams("run=run_01jb2c3d4e&station=4&alarm=RA-3"));
    expect(describeContext(lineChatContext(alarm)!)).toBe("This run, Investigation, alarm RA-3");
  });
});

describe("contextFromLocation", () => {
  it("reads the object on screen", () => {
    expect(contextFromLocation("/", new URLSearchParams("pick=unit:1062"))).toEqual({
      unit_id: 1062,
    });
    expect(contextFromLocation("/", new URLSearchParams("station=2&sensor=S060"))).toEqual({
      sensor: "S060",
    });
    expect(contextFromLocation("/", new URLSearchParams("pick=wafer:lot1-2"))).toEqual({
      wafer_id: "lot1-2",
    });
    expect(contextFromLocation("/", new URLSearchParams("pick=lot:lot47542"))).toEqual({
      lot: "lot47542",
    });
    expect(contextFromLocation("/investigations/inv_01jae5x9k3m2", new URLSearchParams())).toEqual({
      investigation_id: "inv_01jae5x9k3m2",
    });
    expect(
      contextFromLocation("/", new URLSearchParams("run=run_01jb2c3d4e&station=1&unit=0")),
    ).toEqual({
      run_id: "run_01jb2c3d4e",
      station: "manufacturing",
      run_unit: 0,
      run_wafer: null,
      run_lot: null,
      run_alarm: null,
    });
    expect(contextFromLocation("/", new URLSearchParams())).toBeNull();
    expect(contextFromLocation("/how", new URLSearchParams("pick=unit:1062"))).toBeNull();
  });
});

describe("extractVisiblePageContent", () => {
  it("extracts text from headings and tables while skipping hidden elements", () => {
    const div = document.createElement("div");
    div.innerHTML = `
      <h1>Line Overview</h1>
      <p>Current yield: 99.2%</p>
      <table>
        <tr><th>Sensor</th><th>Status</th></tr>
        <tr><td>S060</td><td>Normal</td></tr>
      </table>
      <script>console.log("secret");</script>
      <div aria-hidden="true">Hidden text</div>
      <div role="dialog">Modal text</div>
    `;
    const text = extractVisiblePageContent(div);
    expect(text).toContain("### Line Overview");
    expect(text).toContain("Current yield: 99.2%");
    expect(text).toContain("Sensor | Status");
    expect(text).toContain("S060 | Normal");
    expect(text).not.toContain("secret");
    expect(text).not.toContain("Hidden text");
    expect(text).not.toContain("Modal text");
  });
});
