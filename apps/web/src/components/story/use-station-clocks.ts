"use client";

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

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
 * How long the station had been computing when the run's stored state was read, by the server's
 * own clock (the stage's start and the read), so a reload goes on counting from there instead of
 * from nothing. 0 for a stage that started after the read, or with no stored state.
 */
export function computingWhenRead(state: RunState, station: ClockStation): number {
  const read = state.readAt ? Date.parse(state.readAt) : Number.NaN;
  if (!Number.isFinite(read)) return 0;
  let ms = 0;
  for (const s of CLOCK_STAGES[station]) {
    const stage = state.stages[s];
    if (stage.status !== "running" || !stage.startedAt) continue;
    const started = Date.parse(stage.startedAt);
    if (Number.isFinite(started)) ms = Math.max(ms, read - started);
  }
  return ms;
}

/**
 * A stopwatch per station, measured on this page: it starts when a station's stage is first
 * seen running (from what it had already run when the run's state was read) and stops when no
 * stage of it runs. Ticks ten times a second while one runs, and not at all otherwise.
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
    /** `running`: each station computing now, with the time it had computed before this page saw it. */
    sync(runId: string | null, running: ReadonlyMap<ClockStation, number>) {
      let changed = false;
      if (runId !== run) {
        run = runId;
        changed = since.size > 0;
        since.clear();
      }
      now = performance.now();
      for (const [station, before] of running) {
        if (!since.has(station)) {
          since.set(station, now - before);
          changed = true;
        }
      }
      for (const station of [...since.keys()]) {
        if (!running.has(station)) {
          since.delete(station);
          changed = true;
        }
      }
      if (running.size && timer == null) {
        timer = window.setInterval(() => {
          now = performance.now();
          emit();
        }, 100);
      } else if (!running.size && timer != null) {
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
  const latest = useRef(state);
  useEffect(() => {
    latest.current = state;
  });
  useEffect(() => {
    const now = latest.current;
    watch.sync(
      runId,
      new Map(
        key
          ? (key.split(" ") as ClockStation[]).map((c) => [c, now ? computingWhenRead(now, c) : 0])
          : [],
      ),
    );
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
          // Before the stopwatch has seen it (the first paint): what it had run when read.
          ms: Math.max(0, started != null ? snapshot.now - started : computingWhenRead(state, c)),
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
