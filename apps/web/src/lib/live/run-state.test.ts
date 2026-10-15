import type { RunEvent } from "@yield-guardian/contracts";

import {
  RUN_ID,
  eventsOf,
  sampleEvents,
  SENSORS_ONLY_ID,
  sensorsOnlyEvents,
  snapshotOf,
} from "../../../e2e/story/fixture";

import {
  STAGES,
  applyRunEvent,
  applyRunSnapshot,
  arrivedLive,
  emptyRunState,
  isFinished,
  knownBefore,
  linkInvestigation,
  reduceRunEvents,
  runStateFrom,
  stageResult,
  type RunState,
} from "./run-state";

/** The parts of the state that must not depend on delivery order. */
function settled(state: RunState) {
  return {
    status: state.status,
    origin: state.origin,
    stages: state.stages,
    alarms: state.alarms,
    alarmsNotListed: state.alarmsNotListed,
    contiguousSeq: state.contiguousSeq,
  };
}

/**
 * Without the stages' start times: a stage that finished before a snapshot was read has no
 * start in it (only a running stage's start counts there, for its clock).
 */
function withoutStarts(view: ReturnType<typeof settled>) {
  return {
    ...view,
    stages: Object.fromEntries(
      Object.entries(view.stages).map(([id, { startedAt: _, ...rest }]) => [id, rest]),
    ),
  };
}

function shuffled<T>(items: readonly T[], seed: number): T[] {
  // A fixed permutation (Park-Miller), so a failure can be repeated.
  const out = items.slice();
  let s = seed;
  for (let i = out.length - 1; i > 0; i -= 1) {
    s = (s * 48271) % 2147483647;
    const j = s % (i + 1);
    [out[i], out[j]] = [out[j]!, out[i]!];
  }
  return out;
}

const lastSeq = Math.max(...sampleEvents.map((e) => e.seq));

describe("run state", () => {
  it("applies a run's events in order", () => {
    const state = reduceRunEvents(RUN_ID, sampleEvents);
    expect(state.status).toBe("done");
    expect(isFinished(state)).toBe(true);
    for (const stage of STAGES) expect(state.stages[stage].status).toBe("done");
    expect(state.alarms.map((a) => a.alarm_id)).toEqual(
      eventsOf(sampleEvents, "alarm").map((e) => e.alarm.alarm_id),
    );
    expect(state.contiguousSeq).toBe(lastSeq);
    expect(state.origin?.source).toBe("sample");
    const risk = stageResult(state, "sensor_risk");
    expect(risk?.units).toHaveLength(40);
    expect(state.stages.sensor_risk.elapsedMs).toBe(
      eventsOf(sampleEvents, "stage_result").find((e) => e.stage === "sensor_risk")!.elapsed_ms,
    );
    expect(state.stages.control_charts.startedAt).toBe(
      eventsOf(sampleEvents, "stage_started").find((e) => e.stage === "control_charts")!.at,
    );
  });

  it("queues each result, alarm and the end once, in arrival order", () => {
    const state = reduceRunEvents(RUN_ID, sampleEvents);
    const expected = sampleEvents.flatMap((e) =>
      e.type === "stage_result"
        ? [{ kind: "result", stage: e.stage, seq: e.seq }]
        : e.type === "alarm"
          ? [{ kind: "alarm", alarmId: e.alarm.alarm_id, seq: e.seq }]
          : e.type === "run_done"
            ? [{ kind: "done", seq: e.seq }]
            : [],
    );
    expect(state.arrivals).toEqual(expected);
  });

  it("ignores events delivered twice", () => {
    const twice = sampleEvents.flatMap((e) => [e, e]);
    const once = reduceRunEvents(RUN_ID, sampleEvents);
    const doubled = reduceRunEvents(RUN_ID, twice);
    expect(settled(doubled)).toEqual(settled(once));
    expect(doubled.arrivals).toEqual(once.arrivals);
  });

  it("returns the same object when an event changes nothing", () => {
    const state = reduceRunEvents(RUN_ID, sampleEvents);
    expect(applyRunEvent(state, sampleEvents[3]!)).toBe(state);
  });

  it.each([1, 7, 42, 2026])("reaches the same state from any delivery order (seed %i)", (seed) => {
    const inOrder = reduceRunEvents(RUN_ID, sampleEvents);
    const mixed = reduceRunEvents(RUN_ID, shuffled(sampleEvents, seed));
    expect(settled(mixed)).toEqual(settled(inOrder));
    // Every result still reaches the animation once, whatever the order.
    expect(mixed.arrivals.filter((a) => a.kind === "result")).toHaveLength(STAGES.length);
  });

  it("does not let a late stage_started undo a result", () => {
    const result = eventsOf(sampleEvents, "stage_result")[0]!;
    const started = eventsOf(sampleEvents, "stage_started").find((e) => e.stage === result.stage)!;
    const state = [sampleEvents[0]!, result, started].reduce(applyRunEvent, emptyRunState(RUN_ID));
    expect(state.stages[result.stage].status).toBe("done");
    expect(state.stages[result.stage].result).toEqual(result.result);
  });

  it("tracks the last seq without a gap, for Last-Event-ID", () => {
    const [first, second, third, fourth] = sampleEvents;
    let state = applyRunEvent(emptyRunState(RUN_ID), second!);
    expect(state.contiguousSeq).toBeNull(); // run_started not seen yet
    state = applyRunEvent(state, first!);
    expect(state.contiguousSeq).toBe(second!.seq);
    state = applyRunEvent(state, fourth!);
    expect(state.contiguousSeq).toBe(second!.seq);
    state = applyRunEvent(state, third!);
    expect(state.contiguousSeq).toBe(fourth!.seq);
  });

  it("rebuilds from GET /runs/{id} after a reload, without replaying the animation", () => {
    const run = snapshotOf(sampleEvents);
    const state = applyRunSnapshot(emptyRunState(RUN_ID), run);
    expect(state.status).toBe("done");
    expect(state.arrivals).toEqual([]);
    expect(state.units).toBe(40);
    expect(state.wafers).toBe(stageResult(state, "wafer_pattern")?.wafers.length);
    expect(state.wafers).toBeGreaterThan(1);
    expect(state.expiresAt).toBe(run.expires_at);
    for (const stage of STAGES) expect(state.stages[stage].result).not.toBeNull();
    expect(state.alarms).toHaveLength(run.alarms.length);
  });

  it("keeps an expiry of null: the run is kept while an investigation uses it", () => {
    const run = { ...snapshotOf(sampleEvents), expires_at: null };
    expect(applyRunSnapshot(emptyRunState(RUN_ID), run).expiresAt).toBeNull();
    expect(emptyRunState(RUN_ID).expiresAt).toBeUndefined();
  });

  it("merges a mid-run snapshot with the stream after its last event (a reload mid-run)", () => {
    const cut = 12;
    const snapshot = snapshotOf(sampleEvents.slice(0, cut));
    let state = applyRunSnapshot(emptyRunState(RUN_ID), snapshot);
    expect(state.status).toBe("running");
    // The snapshot names the last event it includes: the stream resumes right after it.
    expect(state.contiguousSeq).toBe(snapshot.last_seq);
    expect(snapshot.last_seq).toBe(sampleEvents[cut - 1]!.seq);
    const after = sampleEvents.filter((e) => e.seq > snapshot.last_seq!);
    state = after.reduce(applyRunEvent, state);
    const full = reduceRunEvents(RUN_ID, sampleEvents);
    expect(withoutStarts(settled(state))).toEqual(withoutStarts(settled(full)));
    // Results the snapshot already had are not queued again; the rest are, once each.
    const known = new Set(snapshot.stages.filter((s) => s.status === "done").map((s) => s.stage));
    expect(known.size).toBeGreaterThan(0);
    expect(state.arrivals.some((a) => a.kind === "result" && known.has(a.stage))).toBe(false);
    expect(state.arrivals.filter((a) => a.kind === "result")).toHaveLength(
      STAGES.length - known.size,
    );
    expect(knownBefore(state)).toEqual(known);
    // A replay of the whole stream (a reconnect without Last-Event-ID) changes nothing more.
    expect(sampleEvents.reduce(applyRunEvent, state)).toBe(state);
  });

  it("merges a snapshot that names no last event with a replay of the stream from its start", () => {
    const cut = 12;
    const snapshot = { ...snapshotOf(sampleEvents.slice(0, cut)), last_seq: 0 };
    let state = applyRunSnapshot(emptyRunState(RUN_ID), snapshot);
    expect(state.contiguousSeq).toBeNull();
    state = sampleEvents.reduce(applyRunEvent, state);
    expect(settled(state)).toEqual(settled(reduceRunEvents(RUN_ID, sampleEvents)));
    const known = new Set(snapshot.stages.filter((s) => s.status === "done").map((s) => s.stage));
    expect(state.arrivals.some((a) => a.kind === "result" && known.has(a.stage))).toBe(false);
  });

  it("never moves the resume point back for an older snapshot", () => {
    const state = reduceRunEvents(RUN_ID, sampleEvents.slice(0, 20));
    const older = snapshotOf(sampleEvents.slice(0, 8));
    expect(applyRunSnapshot(state, older).contiguousSeq).toBe(state.contiguousSeq);
  });

  it("carries a running stage's start and the time the snapshot was read", () => {
    const cut = sampleEvents.findIndex(
      (e) => e.type === "stage_started" && e.stage === "control_charts",
    );
    const snapshot = snapshotOf(sampleEvents.slice(0, cut + 1));
    const state = runStateFrom(snapshot);
    expect(state.stages.control_charts.status).toBe("running");
    expect(state.stages.control_charts.startedAt).toBe(sampleEvents[cut]!.at);
    expect(state.readAt).toBe(snapshot.read_at);
  });

  it("shows a stored run at rest: nothing in it arrived on the stream", () => {
    const state = runStateFrom(snapshotOf(sampleEvents));
    expect(state.arrivals).toEqual([]);
    expect(knownBefore(state)).toEqual(new Set(STAGES));
    expect(arrivedLive(state, { stage: "wafer_pattern" })).toBe(false);
    expect(arrivedLive(state, { alarmId: state.alarms[0]!.alarm_id })).toBe(false);
    const streamed = reduceRunEvents(RUN_ID, sampleEvents);
    expect(knownBefore(streamed)).toEqual(new Set());
    expect(arrivedLive(streamed, { stage: "wafer_pattern" })).toBe(true);
    expect(arrivedLive(streamed, { alarmId: streamed.alarms[0]!.alarm_id })).toBe(true);
  });

  it("keeps an investigation link that either the snapshot or the stream carries", () => {
    const state = reduceRunEvents(RUN_ID, sampleEvents);
    const alarm = state.alarms[0]!;
    const run = snapshotOf(sampleEvents);
    run.alarms = run.alarms.map((a) =>
      a.alarm_id === alarm.alarm_id
        ? { ...a, investigation_id: "inv_1", investigation_status: "running" }
        : a,
    );
    const linked = applyRunSnapshot(state, run);
    expect(linked.alarms[0]!.investigation_id).toBe("inv_1");
    expect(linked.alarms[0]!.investigation_status).toBe("running");
    // A later replay of the alarm without the link keeps it.
    const again = applyRunSnapshot(linked, snapshotOf(sampleEvents));
    expect(again.alarms[0]!.investigation_id).toBe("inv_1");
    expect(again.alarms[0]!.investigation_status).toBe("running");
    // A newer read carries the status it has now.
    run.alarms = run.alarms.map((a) =>
      a.alarm_id === alarm.alarm_id ? { ...a, investigation_status: "awaiting_decision" } : a,
    );
    expect(applyRunSnapshot(again, run).alarms[0]!.investigation_status).toBe("awaiting_decision");
  });

  it("records an investigation started on this page, with its status", () => {
    const state = runStateFrom(snapshotOf(sampleEvents));
    const alarm = state.alarms[1]!;
    const linked = linkInvestigation(state, alarm.alarm_id, "inv_2", "queued");
    expect(linked.alarms[1]).toMatchObject({
      investigation_id: "inv_2",
      investigation_status: "queued",
    });
    expect(linkInvestigation(linked, alarm.alarm_id, "inv_2", "queued")).toBe(linked);
    // A link with no status keeps the one known.
    expect(linkInvestigation(linked, alarm.alarm_id, "inv_2").alarms[1]!.investigation_status).toBe(
      "queued",
    );
    expect(linkInvestigation(state, "RA-999", "inv_3")).toBe(state);
  });

  it("orders alarms by number whatever order they arrive in", () => {
    const alarms = eventsOf(sampleEvents, "alarm");
    const state = [sampleEvents[0]!, ...alarms.slice().reverse()].reduce(
      applyRunEvent,
      emptyRunState(RUN_ID),
    );
    expect(state.alarms.map((a) => a.alarm_id)).toEqual(alarms.map((e) => e.alarm.alarm_id));
  });

  it("shows skipped stages with what they need", () => {
    const events = sensorsOnlyEvents();
    const state = reduceRunEvents(SENSORS_ONLY_ID, events);
    expect(state.stages.wafer_pattern.status).toBe("skipped");
    expect(state.stages.wafer_pattern.needs).toMatch(/wafer maps/);
    expect(state.stages.lot.status).toBe("skipped");
    expect(state.stages.sensor_risk.status).toBe("done");
    expect(stageResult(state, "intake")?.two_sources).toBe(false);
  });

  it("records a skipped or failed stage as it arrives", () => {
    const start = sampleEvents[0]!;
    const skipped: RunEvent = {
      type: "stage_skipped",
      seq: 2,
      at: start.at,
      stage: "drift_health",
      needs: "At least 20 units in time order.",
    };
    const failed: RunEvent = {
      type: "stage_failed",
      seq: 3,
      at: start.at,
      stage: "lot",
      problem: {
        type: "about:blank",
        title: "Lot test failed",
        status: 500,
        code: "internal_error",
      },
    };
    const state = [start, skipped, failed].reduce(applyRunEvent, emptyRunState(RUN_ID));
    expect(state.stages.drift_health).toMatchObject({
      status: "skipped",
      needs: "At least 20 units in time order.",
    });
    expect(state.stages.lot.status).toBe("failed");
    expect(state.stages.lot.problem?.title).toBe("Lot test failed");
    expect(state.arrivals.map((a) => a.kind)).toEqual(["skipped", "failed"]);
  });

  it("counts the alarms the per-run cap left out", () => {
    const events = sampleEvents.map((e) =>
      e.type === "run_done" ? { ...e, alarms_not_listed: 12 } : e,
    );
    expect(reduceRunEvents(RUN_ID, events).alarmsNotListed).toBe(12);
    const run = { ...snapshotOf(sampleEvents), alarms_not_listed: 4 };
    expect(applyRunSnapshot(emptyRunState(RUN_ID), run).alarmsNotListed).toBe(4);
  });

  it("keeps a finished status when a stale snapshot says running", () => {
    const done = reduceRunEvents(RUN_ID, sampleEvents);
    const stale = snapshotOf(sampleEvents.slice(0, 5));
    expect(applyRunSnapshot(done, stale).status).toBe("done");
  });
});
