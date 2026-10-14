import type { Investigation, InvestigationEvent, NumberRef } from "@yield-guardian/contracts";

import { fixture } from "@/mocks/fixtures";

import {
  applyInvestigationEvent,
  emptyRun,
  issuesByTarget,
  readPointer,
  segmentNumbers,
  triggerUnit,
} from "./events";

const stored = () => fixture<Investigation>("get_investigation");
const stream = () => fixture<InvestigationEvent[]>("stream_investigation_events");

const ref = (as_written: string): NumberRef => ({
  value: Number.parseFloat(as_written),
  as_written,
  unit: null,
  evidence_id: "E1",
  path: "/x",
});

describe("applyInvestigationEvent", () => {
  it("rebuilds the stored run from its recorded stream", () => {
    const inv = stored();
    const rebuilt = stream().reduce(applyInvestigationEvent, emptyRun(inv));
    expect(rebuilt.status).toBe(inv.status);
    expect(rebuilt.steps).toEqual(inv.steps);
    expect(rebuilt.evidence.map((e) => e.evidence_id)).toEqual(inv.evidence.map((e) => e.evidence_id));
    expect(rebuilt.report).toEqual(inv.report);
    expect(rebuilt.verification).toEqual(inv.verification);
  });

  it("replaces a running step with its finished version", () => {
    const events = stream().filter((e) => e.type === "step").slice(0, 2);
    const run = events.reduce(applyInvestigationEvent, emptyRun(stored()));
    expect(run.steps).toHaveLength(1);
    expect(run.steps[0]!.status).toBe("completed");
  });

  it("ignores evidence it already has (a reconnect resends nothing twice)", () => {
    const evidence = stream().find((e) => e.type === "evidence")!;
    const once = applyInvestigationEvent(emptyRun(stored()), evidence);
    expect(applyInvestigationEvent(once, evidence).evidence).toHaveLength(1);
  });

  it("records a decision and the work order it opened", () => {
    const inv = stored();
    const next = applyInvestigationEvent(inv, {
      type: "decision",
      seq: 99,
      at: "2026-10-14T12:00:00Z",
      decision: { verdict: "approve", actions: [0], note: null, decided_by: "engineer", decided_at: "2026-10-14T12:00:00Z" },
      work_order_id: "WO-000013",
    });
    expect(next.status).toBe("approved");
    expect(next.work_order_id).toBe("WO-000013");
  });
});

describe("segmentNumbers", () => {
  it("links each listed number where it is written", () => {
    const segments = segmentNumbers("Risk 18.4% above 15%.", [ref("18.4%"), ref("15%")]);
    expect(segments).toEqual([
      { text: "Risk " },
      { text: "18.4%", number: 0 },
      { text: " above " },
      { text: "15%", number: 1 },
      { text: "." },
    ]);
  });

  it("does not match inside a longer number", () => {
    expect(segmentNumbers("21.5 and 1.5", [ref("1.5")])).toEqual([
      { text: "21.5 and " },
      { text: "1.5", number: 0 },
    ]);
    expect(segmentNumbers("q = 0.021.", [ref("0.021")])).toEqual([
      { text: "q = " },
      { text: "0.021", number: 0 },
      { text: "." },
    ]);
  });

  it("prefers the longer written form", () => {
    expect(segmentNumbers("99.9% limit", [ref("99.9"), ref("99.9%")])[0]).toEqual({ text: "99.9%", number: 1 });
  });

  it("finds every number of the fixture report in its text", () => {
    const report = stored().report!;
    const text = [report.summary, ...report.findings.map((f) => f.claim)].join(" ");
    const found = new Set(segmentNumbers(text, report.numbers).flatMap((s) => (s.number != null ? [s.number] : [])));
    expect(found.size).toBe(report.numbers.length);
  });
});

describe("issues and pointers", () => {
  it("groups issues by the part they flag", () => {
    const map = issuesByTarget(stored().verification!.issues);
    expect(map.get("numbers[3]")).toHaveLength(1);
  });

  it("reads JSON pointers into evidence data", () => {
    const data = { a: [{ "b/c": 2 }], risk: 0.2 };
    expect(readPointer(data, "/risk")).toBe(0.2);
    expect(readPointer(data, "/a/0/b~1c")).toBe(2);
    expect(readPointer(data, "/missing/x")).toBeUndefined();
  });
});

describe("unverified marker", () => {
  it("splits [unverified] out as its own segment", () => {
    const segs = segmentNumbers("Yield fell to [unverified] after 18.4%.", [{ as_written: "18.4%" } as never]);
    expect(segs.map((s) => s.text)).toEqual(["Yield fell to ", "[unverified]", " after ", "18.4%", "."]);
    expect(segs[1]!.unverified).toBe(true);
    expect(segs[3]!.number).toBe(0);
  });
});

describe("triggerUnit", () => {
  it("reads the unit from an alarm ID or a unit trigger", () => {
    expect(triggerUnit({ kind: "alarm", ref: "AL-1303-t2" })).toBe(1303);
    expect(triggerUnit({ kind: "unit", ref: "522" })).toBe(522);
  });
  it("has none for wafers, lots or odd refs", () => {
    expect(triggerUnit({ kind: "wafer", ref: "lot10291-1" })).toBeNull();
    expect(triggerUnit({ kind: "lot", ref: "lot10291" })).toBeNull();
    expect(triggerUnit({ kind: "alarm", ref: "nope" })).toBeNull();
    expect(triggerUnit({ kind: "unit", ref: "12a" })).toBeNull();
  });
});
