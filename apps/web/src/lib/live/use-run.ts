"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError } from "@/lib/api/errors";

import { getRun, isGone } from "./api";
import {
  applyRunEvent,
  applyRunSnapshot,
  emptyRunState,
  isFinished,
  linkInvestigation,
  type RunState,
} from "./run-state";
import { RUN_GONE_MESSAGE, RunStreamError, followRun, type RunStreamStatus } from "./sse";

export type RunConnection = RunStreamStatus | "idle" | "loading";

export interface RunProblem {
  kind: "gone" | "not_found" | "other";
  message: string;
}

export interface RunHandle {
  state: RunState | null;
  connection: RunConnection;
  problem: RunProblem | null;
  /** Records an investigation started from one of the run's alarms. */
  linkInvestigation: (alarmId: string, investigationId: string) => void;
}

function problemOf(error: unknown): RunProblem {
  if (error instanceof RunStreamError) {
    return {
      kind: error.kind === "gone" ? "gone" : error.kind === "not_found" ? "not_found" : "other",
      message: error.message,
    };
  }
  if (isGone(error)) return { kind: "gone", message: RUN_GONE_MESSAGE };
  if (error instanceof ApiError && error.status === 404) {
    return { kind: "not_found", message: "There is no run with this link. Start a new one." };
  }
  if (error instanceof ApiError && error.status === 0) {
    return {
      kind: "other",
      message: "The API did not answer. Check that it is running, then reload.",
    };
  }
  return {
    kind: "other",
    message: error instanceof Error ? error.message : "The run could not be read.",
  };
}

interface Held {
  runId: string;
  state: RunState;
  connection: RunConnection;
  problem: RunProblem | null;
}

/**
 * Follows one run. A run this page just created (`fresh`) is read from its event stream from the
 * first event, so every result reaches the line as it arrives. A run opened from a link is read
 * from GET /runs/{id} first: its results show as they stand, and the stream is followed only
 * while the run is still going (results that arrive then reach the line as they come).
 */
export function useRun(runId: string | null, { fresh }: { fresh: boolean }): RunHandle {
  const [held, setHeld] = useState<Held | null>(null);
  /** The run's state as the stream and snapshot have built it, read by the stream to resume. */
  const latest = useRef<RunState | null>(null);
  const following = useRef<string | null>(null);
  const empty = useMemo(() => (runId ? emptyRunState(runId) : null), [runId]);

  const patch = useCallback(
    (
      id: string,
      change: Partial<Omit<Held, "runId" | "state">>,
      next?: (current: RunState) => RunState,
    ) => {
      if (following.current !== id) return;
      const base = latest.current?.runId === id ? latest.current : emptyRunState(id);
      const state = next ? next(base) : base;
      latest.current = state;
      setHeld((current) => ({
        ...(current?.runId === id
          ? current
          : { runId: id, connection: "connecting" as RunConnection, problem: null }),
        ...change,
        state,
      }));
    },
    [],
  );

  useEffect(() => {
    following.current = runId;
    if (!runId) {
      latest.current = null;
      return;
    }
    const controller = new AbortController();
    const { signal } = controller;
    latest.current = emptyRunState(runId);

    const follow = async () => {
      await followRun({
        runId,
        resumeFrom: () => latest.current?.contiguousSeq ?? null,
        onEvent: (event) => patch(runId, {}, (current) => applyRunEvent(current, event)),
        onStatus: (status) => {
          if (!signal.aborted) patch(runId, { connection: status });
        },
        signal,
      });
    };
    const snapshot = async () => {
      const run = await getRun(runId, { signal });
      if (!signal.aborted) patch(runId, {}, (current) => applyRunSnapshot(current, run));
      return run;
    };

    const go = async () => {
      try {
        if (fresh) {
          await follow();
          // The stream has every result; the snapshot adds the expiry and any investigation link.
          if (!signal.aborted) await snapshot().catch(() => undefined);
          return;
        }
        patch(runId, { connection: "loading" });
        const run = await snapshot();
        if (signal.aborted) return;
        if (run.status === "done" || run.status === "failed") {
          patch(runId, { connection: "ended" });
          return;
        }
        await follow();
      } catch (error) {
        if (signal.aborted || (error instanceof DOMException && error.name === "AbortError"))
          return;
        patch(runId, { problem: problemOf(error), connection: "ended" });
      }
    };
    void go();
    return () => {
      controller.abort();
      if (following.current === runId) following.current = null;
    };
  }, [runId, fresh, patch]);

  const link = useCallback(
    (alarmId: string, investigationId: string) => {
      const id = following.current;
      if (id) patch(id, {}, (current) => linkInvestigation(current, alarmId, investigationId));
    },
    [patch],
  );

  const current = held && held.runId === runId ? held : null;
  return {
    state: current?.state ?? empty,
    connection: current?.connection ?? (runId ? "connecting" : "idle"),
    problem: current?.problem ?? null,
    linkInvestigation: link,
  };
}

export { isFinished };
