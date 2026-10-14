import type { LineEvent, LineState } from "@yield-guardian/contracts";

import { fixture } from "@/mocks/fixtures";

import { applyLineEvent, countKpis, parseLineEvent, reconnectDelay } from "./line-state";

const state = () => fixture<LineState>("get_line_state");
const events = () => fixture<LineEvent[]>("line_socket");
const ofType = <T extends LineEvent["type"]>(type: T) =>
  events().find((e) => e.type === type) as Extract<LineEvent, { type: T }>;

describe("countKpis", () => {
  it("matches the API's counts on the fixture", () => {
    const s = state();
    expect(countKpis(s.recent)).toEqual(s.kpis);
  });
});

describe("applyLineEvent", () => {
  it("appends a new unit, keeps the window and moves the clock", () => {
    const s = state();
    const event = ofType("unit");
    const { state: next, followUp } = applyLineEvent(s, event, s.recent.length);
    expect(followUp).toBe("none");
    expect(next.recent).toHaveLength(s.recent.length);
    expect(next.recent.at(-1)).toEqual(event.unit);
    expect(next.recent[0]!.sequence).toBe(s.recent[1]!.sequence);
    expect(next.clock.position).toBe(event.clock.position);
    expect(next.kpis).toEqual(countKpis(next.recent));
  });

  it("asks for a refetch when units were missed", () => {
    const s = state();
    const event = ofType("unit");
    const skipped = { ...event, unit: { ...event.unit, sequence: event.unit.sequence + 3 }, clock: { ...event.clock, position: event.clock.position + 3 } };
    expect(applyLineEvent(s, skipped, 120).followUp).toBe("refetch");
  });

  it("reveals a final-test result on the unit it belongs to", () => {
    const s = state();
    const target = s.recent.find((u) => u.final_test === null)!;
    const { state: next } = applyLineEvent(
      s,
      { type: "final_test", unit_id: target.unit_id, sequence: target.sequence, result: "fail" },
      120,
    );
    expect(next.recent.find((u) => u.sequence === target.sequence)!.final_test).toBe("fail");
    expect(next.kpis.failures_revealed).toBe(s.kpis.failures_revealed + 1);
  });

  it("adds open alarms newest first and drops closed ones", () => {
    const s = { ...state(), open_alarms: [] };
    const alarm = ofType("alarm").alarm;
    const opened = applyLineEvent(s, { type: "alarm", alarm }, 120).state;
    expect(opened.open_alarms.map((a) => a.alarm_id)).toEqual([alarm.alarm_id]);
    const closed = applyLineEvent(opened, { type: "alarm", alarm: { ...alarm, status: "closed" } }, 120).state;
    expect(closed.open_alarms).toEqual([]);
  });

  it("keeps history on a hello in the same cycle and never shows units past the clock", () => {
    const s = state();
    const hello = ofType("hello");
    const short = { ...hello, state: { ...hello.state, recent: hello.state.recent.slice(-10) } };
    const next = applyLineEvent(s, short, 120).state;
    expect(next.recent).toHaveLength(s.recent.length);
    expect(Math.max(...next.recent.map((u) => u.sequence))).toBeLessThanOrEqual(next.clock.position);
  });

  it("clears the window and refetches when the replay starts a new cycle", () => {
    const { state: next, followUp } = applyLineEvent(state(), ofType("cycle"), 120);
    expect(next.recent).toEqual([]);
    expect(followUp).toBe("refetch");
  });
});

describe("parseLineEvent", () => {
  it("accepts known events and ignores anything else", () => {
    expect(parseLineEvent(JSON.stringify(ofType("heartbeat")))?.type).toBe("heartbeat");
    expect(parseLineEvent("not json")).toBeNull();
    expect(parseLineEvent(JSON.stringify({ type: "surprise" }))).toBeNull();
    expect(parseLineEvent(new ArrayBuffer(2))).toBeNull();
  });
});

describe("reconnectDelay", () => {
  it("grows from about a second to at most 30 seconds", () => {
    expect(reconnectDelay(0, () => 1)).toBe(1000);
    expect(reconnectDelay(0, () => 0)).toBe(500);
    expect(reconnectDelay(3, () => 1)).toBe(8000);
    expect(reconnectDelay(20, () => 1)).toBe(30_000);
  });
});
