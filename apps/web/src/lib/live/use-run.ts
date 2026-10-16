"use client";

import type { Investigation } from "@yield-guardian/contracts";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import { ApiError } from "@/lib/api/errors";
import { withRetry } from "@/lib/api/retry";

import { getRun, isGone } from "./api";
import { unpack } from "./packed";
import {
  applyRunEvent,
  applyRunGlance,
  applyRunSnapshot,
  emptyRunState,
  fillIn,
  isFinished,
  linkInvestigation,
  type RunState,
  type StoredRunData,
} from "./run-state";
import {
  RUN_GONE_MESSAGE,
  RUN_NOT_FOUND_MESSAGE,
  RunStreamError,
  followRun,
  type RunStreamStatus,
} from "./sse";
import { storedRunId, type StoredRun } from "./stored-run";

/**
 * "loading": reading the run's stored state; "waking": the API has not answered yet (it may be
 * asleep or starting), the page waits and asks again.
 */
export type RunConnection = RunStreamStatus | "idle" | "loading" | "waking";

export interface RunProblem {
  kind: "gone" | "not_found" | "other";
  message: string;
}

export interface RunHandle {
  state: RunState | null;
  connection: RunConnection;
  problem: RunProblem | null;
  /** Records an investigation started from one of the run's alarms. */
  linkInvestigation: (
    alarmId: string,
    investigationId: string,
    status?: Investigation["status"] | null,
  ) => void;
}

export { RUN_NOT_FOUND_MESSAGE };

const NOT_FOUND: RunProblem = { kind: "not_found", message: RUN_NOT_FOUND_MESSAGE };
const GONE: RunProblem = { kind: "gone", message: RUN_GONE_MESSAGE };

function problemOf(error: unknown): RunProblem {
  if (error instanceof RunStreamError) {
    if (error.kind === "gone") return GONE;
    if (error.kind === "not_found") return NOT_FOUND;
    return { kind: "other", message: error.message };
  }
  if (isGone(error)) return GONE;
  if (error instanceof ApiError && error.status === 404) return NOT_FOUND;
  if (error instanceof ApiError && (error.status === 0 || error.status >= 500)) {
    return {
      kind: "other",
      message:
        "The service did not answer for a minute and a half. Check your connection, then reload.",
    };
  }
  return {
    kind: "other",
    message: error instanceof Error ? error.message : "The run could not be read.",
  };
}

// ---------------------------------------------------------------------------------------------
// What this page has shown of each run (browser only)
// ---------------------------------------------------------------------------------------------

/**
 * The last state of the few runs this page showed, so going back or forward to one shows it at
 * once, as it was. Only in the browser: the server renders for many visitors and keeps nothing.
 */
const shown = new Map<string, RunState>();
const SHOWN_RUNS = 4;

function remember(state: RunState) {
  if (typeof window === "undefined") return;
  shown.delete(state.runId);
  shown.set(state.runId, state);
  while (shown.size > SHOWN_RUNS) shown.delete(shown.keys().next().value!);
}

/** A run shown before, at rest: what the line played then is not queued to play again. */
function recall(runId: string): RunState | null {
  if (typeof window === "undefined") return null;
  const state = shown.get(runId);
  return state ? { ...state, arrivals: [] } : null;
}

/** For tests: forget every run shown. */
export function forgetShownRuns() {
  shown.clear();
}

interface Held {
  runId: string;
  state: RunState;
  connection: RunConnection;
  problem: RunProblem | null;
}

/** The stored run the page came with, unpacked once however often the page starts from it. */
const unpacked = new WeakMap<StoredRun, StoredRunData>();

function storedRunData(stored: Extract<StoredRun, { kind: "run" }>): StoredRunData {
  let run = unpacked.get(stored);
  if (!run) {
    run = unpack(stored.packed);
    unpacked.set(stored, run);
  }
  return run;
}

/**
 * Where the page starts for a run, before any request: what it showed of it before, merged with
 * what the server read while rendering the page (in its compact form: the stages it carried in
 * part are noted, and read in full just after). The same on the server and in hydration.
 */
function startFor(runId: string, stored: StoredRun | null, fresh: boolean): Held {
  const before = recall(runId);
  const mine = storedRunId(stored) === runId ? stored : null;
  let state = before ?? emptyRunState(runId);
  if (mine?.kind === "run") state = applyRunGlance(state, storedRunData(mine), mine.partial);
  const problem =
    !before && mine?.kind === "not_found"
      ? NOT_FOUND
      : !before && mine?.kind === "gone"
        ? GONE
        : null;
  const connection: RunConnection = problem
    ? "ended"
    : isFinished(state)
      ? "ended"
      : fresh || state.contiguousSeq != null
        ? "connecting"
        : "loading";
  return { runId, state, connection, problem };
}

const noSubscribe = () => () => {};

/**
 * Follows one run.
 *
 * A run this page just created (`fresh`) is read from its event stream from the first event, so
 * every result reaches the line as it arrives. Any other run (a reload, a link, back and
 * forward) starts from its stored state, shown as it stands with nothing replayed: what the
 * server read while rendering the page (`stored`, compact: the bulk it leaves out is read just
 * after and drawn in place), or what this page showed of it before, or else GET /runs/{id},
 * which waits while the API wakes. A run still going is then followed on
 * its stream from right after the last event that state includes (Last-Event-ID), so what
 * arrives then reaches the line as it comes.
 */
export function useRun(
  runId: string | null,
  { fresh, stored = null }: { fresh: boolean; stored?: StoredRun | null },
): RunHandle {
  // True while hydrating the server's HTML: the stored state was read for this very load.
  const hydrating = useSyncExternalStore(
    noSubscribe,
    () => false,
    () => true,
  );
  const [first] = useState(() =>
    runId ? { ...startFor(runId, stored, fresh), fromDocument: hydrating } : null,
  );
  const [held, setHeld] = useState<Held | null>(first);
  // A run left (for no run, or another one) is let go of as it was held: what reached the page
  // on its stream has played. Coming back to it starts from what the page showed, at rest.
  const [shownRun, setShownRun] = useState(runId);
  if (shownRun !== runId) {
    setShownRun(runId);
    if (held && held.runId !== runId) setHeld(null);
  }
  /** The run's state as the snapshot and the stream have built it, read by the stream to resume. */
  const latest = useRef<RunState | null>(first?.state ?? null);
  const following = useRef<string | null>(null);

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
      remember(state);
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
    const start =
      latest.current?.runId === runId
        ? null // this page already holds the run (the stream follows on from it)
        : startFor(runId, stored, fresh);
    if (start) {
      latest.current = start.state;
      setHeld(start);
    }
    const fromDocument = first?.runId === runId && first.fromDocument;
    const known = latest.current!;
    const problemShown = start?.problem ?? (held?.runId === runId ? held.problem : null);

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
    /** GET /runs/{id}; `quiet` when the page already shows the run: no waiting note, no error. */
    const read = async ({ quiet }: { quiet: boolean }) => {
      try {
        const run = await withRetry(() => getRun(runId, { signal }), {
          signal,
          onWaiting: quiet ? undefined : () => patch(runId, { connection: "waking" }),
        });
        if (!signal.aborted)
          patch(runId, { problem: null }, (current) => applyRunSnapshot(current, run));
      } catch (error) {
        if (!quiet) throw error;
      }
    };
    /**
     * The bulk of the results the page's first paint carried in part (lib/live/glance.ts), read
     * after hydration and drawn in place: only those stages change, so nothing the stream brings
     * meanwhile is taken from it, and nothing is queued to play. Quiet: the page already shows
     * the run, and the details it waits for say they are being read.
     */
    const fill = async () => {
      try {
        const run = await withRetry(() => getRun(runId, { signal }), { signal });
        if (!signal.aborted) patch(runId, {}, (current) => fillIn(current, run));
      } catch {
        // Left as shown; the next read of the run (a reload, back and forward) fills it in.
      }
    };

    const go = async () => {
      // The API answered 404 or 410 while the server rendered the page: that answer is final.
      if (problemShown) return;
      try {
        // Known up to an event (a snapshot, or this page's own stream): shown as it stands.
        const knownUpTo = known.contiguousSeq != null;
        if (fresh || knownUpTo) {
          if (!isFinished(known)) {
            const following = follow();
            const filling = known.partial.size ? fill() : null;
            await following;
            // The stream has every result; the snapshot adds the expiry and any investigation
            // link made since.
            if (!signal.aborted) await filling;
            if (!signal.aborted) await read({ quiet: true });
          } else if (!fromDocument && start !== null) {
            // A finished run shown from what this page held before (back and forward): one
            // quiet read picks up an investigation started from it since, on any device (and
            // draws in place any bulk still to read).
            await read({ quiet: true });
            if (!signal.aborted) patch(runId, { connection: "ended" });
          } else if (known.partial.size) {
            await fill();
          }
          return;
        }
        patch(runId, { connection: "loading" });
        await read({ quiet: false });
        if (signal.aborted) return;
        if (isFinished(latest.current!)) {
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
    // `stored` and `first` are read for the run being opened only; a new stored state for the
    // same run (a refresh of the page's data) needs no new reader.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, fresh, patch]);

  const link = useCallback(
    (alarmId: string, investigationId: string, status: Investigation["status"] | null = null) => {
      const id = following.current;
      if (id)
        patch(id, {}, (current) => linkInvestigation(current, alarmId, investigationId, status));
    },
    [patch],
  );

  // Another run than the one held, until the effect takes it up: where the page starts for it.
  const heldRun = held?.runId ?? null;
  const opening = useMemo(
    () => (runId && heldRun !== runId ? startFor(runId, stored, fresh) : null),
    [runId, heldRun, stored, fresh],
  );
  const current = held && heldRun === runId ? held : opening;
  return {
    state: current?.state ?? null,
    connection: current?.connection ?? "idle",
    problem: current?.problem ?? null,
    linkInvestigation: link,
  };
}

export { isFinished };
