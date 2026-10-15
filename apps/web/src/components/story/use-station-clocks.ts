"use client";

import { useEffect, useMemo, useState, useSyncExternalStore } from "react";

import type { RunState, StageId } from "@/lib/live/run-state";
import { STATION_STAGES, type StationTone } from "@/lib/live/stations";

import type { ClockStation, StationClock } from "./bay";

const CLOCK_STAGES: Record<ClockStation, readonly StageId[]> = {
  ...STATION_STAGES,
  final_test: ["final_test"],
};
const CLOCKED = Object.keys(CLOCK_STAGES) as ClockStation[];

interface Snapshot {
  now: number;
  since: ReadonlyMap<ClockStation, number>;
}

/**
 * A stopwatch per station, measured on this page: it starts when a station's stage is first
 * seen running and stops when no stage of it runs. Ticks ten times a second while one runs, and
 * not at all otherwise.
 */
function createStopwatch() {
  let run: string | null = null;
  const since = new Map<ClockStation, number>();
  let now = 0;
  let timer: number | null = null;
  const listeners = new Set<() => void>();
  let snapshot: Snapshot = { now, since: new Map() };
  const emit = () => {
    snapshot = { now, since: new Map(since) };
    for (const listener of listeners) listener();
  };
  return {
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    get: () => snapshot,
    sync(runId: string | null, running: readonly ClockStation[]) {
      let changed = false;
      if (runId !== run) {
        run = runId;
        changed = since.size > 0;
        since.clear();
      }
      now = performance.now();
      for (const station of running) {
        if (!since.has(station)) {
          since.set(station, now);
          changed = true;
        }
      }
      for (const station of [...since.keys()]) {
        if (!running.includes(station)) {
          since.delete(station);
          changed = true;
        }
      }
      if (running.length && timer == null) {
        timer = window.setInterval(() => {
          now = performance.now();
          emit();
        }, 100);
      } else if (!running.length && timer != null) {
        window.clearInterval(timer);
        timer = null;
      }
      if (changed) emit();
    },
    stop() {
      if (timer != null) window.clearInterval(timer);
      timer = null;
    },
  };
}

/**
 * What each station's chip says while it works: "Waiting" before its first stage starts,
 * "Computing" with the time measured here while the server computes, and "Computed in" with the
 * server's own time once the result is in and the line is showing it.
 */
export function useStationClocks(state: RunState | null, tones: Record<ClockStation, StationTone>) {
  const [watch] = useState(createStopwatch);
  const running = useMemo(
    () =>
      state
        ? CLOCKED.filter(
            (c) =>
              tones[c] === "working" &&
              CLOCK_STAGES[c].some((s) => state.stages[s].status === "running"),
          )
        : [],
    [state, tones],
  );
  const key = running.join(" ");
  const runId = state?.runId ?? null;
  useEffect(() => {
    watch.sync(runId, key ? (key.split(" ") as ClockStation[]) : []);
  }, [watch, runId, key]);
  useEffect(() => () => watch.stop(), [watch]);
  const snapshot = useSyncExternalStore(watch.subscribe, watch.get, watch.get);

  return useMemo(() => {
    const clocks = {} as Record<ClockStation, StationClock>;
    for (const c of CLOCKED) {
      if (!state || tones[c] !== "working") {
        clocks[c] = null;
        continue;
      }
      const stages = CLOCK_STAGES[c].map((s) => state.stages[s]);
      const started = snapshot.since.get(c);
      if (stages.some((s) => s.status === "running")) {
        clocks[c] = {
          kind: "computing",
          ms: started != null ? Math.max(0, snapshot.now - started) : 0,
        };
      } else if (stages.some((s) => s.status === "done")) {
        clocks[c] = {
          kind: "computed",
          ms: stages.reduce((sum, s) => sum + (s.status === "done" ? (s.elapsedMs ?? 0) : 0), 0),
        };
      } else {
        clocks[c] = { kind: "waiting", ms: 0 };
      }
    }
    return clocks;
  }, [state, tones, snapshot]);
}
