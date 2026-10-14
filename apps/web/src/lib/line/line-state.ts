import type { Alarm, LineEvent, LineKpis, LineState, UnitSummary } from "@yield-guardian/contracts";

/**
 * Applies /ws/line events to the line state that GET /line/state returned, so the screen moves
 * with the plant without polling. Pure, so it is unit-tested against the contract fixtures.
 */

/** Same definitions as the API's LineKpis: counts over the units in `recent`. */
export function countKpis(recent: UnitSummary[]): LineKpis {
  let high = 0;
  let elevated = 0;
  let warnings = 0;
  let alarms = 0;
  let failures = 0;
  for (const u of recent) {
    if (u.risk_band === "high") high += 1;
    else if (u.risk_band === "elevated") elevated += 1;
    if (u.fdc_alarm === "warning") warnings += 1;
    else if (u.fdc_alarm === "alarm") alarms += 1;
    if (u.final_test === "fail") failures += 1;
  }
  return {
    window_units: recent.length,
    high_risk: high,
    elevated_risk: elevated,
    fdc_warnings: warnings,
    fdc_alarms: alarms,
    failures_revealed: failures,
  };
}

function withRecent(state: LineState, recent: UnitSummary[], window: number): LineState {
  const position = state.clock.position;
  const bySequence = new Map<number, UnitSummary>();
  for (const unit of recent) if (unit.sequence <= position) bySequence.set(unit.sequence, unit);
  const kept = [...bySequence.values()].sort((a, b) => a.sequence - b.sequence).slice(-window);
  return { ...state, recent: kept, kpis: countKpis(kept) };
}

function upsertAlarm(alarms: Alarm[], alarm: Alarm): Alarm[] {
  const rest = alarms.filter((a) => a.alarm_id !== alarm.alarm_id);
  if (alarm.status !== "open") return rest;
  return [alarm, ...rest].sort((a, b) => b.sequence - a.sequence);
}

/** What the caller should do after an event, beyond showing the new state. */
export type LineFollowUp = "none" | "refetch";

export function applyLineEvent(
  state: LineState,
  event: LineEvent,
  window: number,
): { state: LineState; followUp: LineFollowUp } {
  switch (event.type) {
    case "hello": {
      const next = event.state;
      // A new replay cycle replaces everything; otherwise keep the history this view already has.
      const sameCycle = next.clock.cycle === state.clock.cycle;
      const merged = sameCycle ? [...state.recent, ...next.recent] : next.recent;
      return { state: withRecent({ ...next }, merged, window), followUp: "none" };
    }
    case "unit": {
      const last = state.recent.at(-1)?.sequence;
      const missed = last !== undefined && event.unit.sequence > last + 1;
      const next = withRecent({ ...state, clock: event.clock }, [...state.recent, event.unit], window);
      return { state: next, followUp: missed ? "refetch" : "none" };
    }
    case "alarm":
      return {
        state: { ...state, open_alarms: upsertAlarm(state.open_alarms, event.alarm) },
        followUp: "none",
      };
    case "final_test": {
      const recent = state.recent.map((u) =>
        u.sequence === event.sequence ? { ...u, final_test: event.result } : u,
      );
      return { state: { ...state, recent, kpis: countKpis(recent) }, followUp: "none" };
    }
    case "heartbeat":
      return { state: { ...state, clock: event.clock }, followUp: "none" };
    case "cycle":
      // The replay started again from the first unit: the old window no longer exists.
      return {
        state: { ...state, clock: event.clock, recent: [], open_alarms: [], kpis: countKpis([]) },
        followUp: "refetch",
      };
    default:
      return { state, followUp: "none" };
  }
}

const EVENT_TYPES = new Set(["hello", "unit", "alarm", "final_test", "heartbeat", "cycle"]);

/** Parses one WebSocket text frame; anything that is not a known event is ignored. */
export function parseLineEvent(data: unknown): LineEvent | null {
  if (typeof data !== "string") return null;
  try {
    const value: unknown = JSON.parse(data);
    if (
      value &&
      typeof value === "object" &&
      "type" in value &&
      typeof value.type === "string" &&
      EVENT_TYPES.has(value.type)
    ) {
      return value as LineEvent;
    }
  } catch {
    // Not JSON: ignore the frame.
  }
  return null;
}

/** Reconnection delay: exponential from 1 s to 30 s, with jitter so clients spread out. */
export function reconnectDelay(attempt: number, random = Math.random): number {
  const base = Math.min(30_000, 1000 * 2 ** Math.max(0, attempt));
  return Math.round(base * (0.5 + random() * 0.5));
}
