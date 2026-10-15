"use client";

import { useEffect, useRef, useState } from "react";

import type { RunState, StageId } from "@/lib/live/run-state";
import type { Focus } from "@/lib/live/url-state";

import { EMPTY_SCENE, createSceneStore, restScene, type SceneStore } from "./scene";
import type * as TimelineModule from "./timeline";
import type { LineTimeline } from "./timeline";

/** Stages whose result was known before this page followed the stream (a reload): shown at once. */
function knownBefore(state: RunState): Set<StageId> {
  const streamed = new Set(
    state.arrivals.flatMap((a) => (a.kind === "alarm" || a.kind === "done" ? [] : [a.stage])),
  );
  return new Set(
    (Object.keys(state.stages) as StageId[]).filter((s) => {
      const status = state.stages[s].status;
      return (status === "done" || status === "skipped" || status === "failed") && !streamed.has(s);
    }),
  );
}

/**
 * Drives the line's scene for a run. With motion, arrived results are handed to the run's GSAP
 * timeline (loaded on the first result, so the page's first load carries no animation code);
 * without it, the scene is always at rest with every arrived result.
 */
export function useLineScene(state: RunState | null, focus: Focus, reducedMotion: boolean) {
  const [store] = useState<SceneStore>(() => createSceneStore());
  const timeline = useRef<LineTimeline | null>(null);
  const consumed = useRef(0);
  const latest = useRef({ state, focus });
  const runId = state?.runId ?? null;
  const [loaded, setLoaded] = useState<typeof TimelineModule | null>(null);

  useEffect(() => {
    latest.current = { state, focus };
  });

  // A new run: a fresh scene, with whatever was known before the stream at rest.
  useEffect(() => {
    timeline.current?.kill();
    timeline.current = null;
    consumed.current = 0;
    const current = latest.current.state;
    store.set(
      current
        ? restScene(current, latest.current.focus, knownBefore(current), EMPTY_SCENE)
        : EMPTY_SCENE,
    );
  }, [runId, store]);

  // The animation code loads with the first result to show.
  const wantsTimeline = !reducedMotion && state != null && state.arrivals.length > 0;
  useEffect(() => {
    if (!wantsTimeline || loaded) return;
    let cancelled = false;
    void import("./timeline").then((module) => {
      if (!cancelled) setLoaded(module);
    });
    return () => {
      cancelled = true;
    };
  }, [wantsTimeline, loaded]);

  // Hand each new arrival to the timeline, or rest the scene without motion.
  useEffect(() => {
    if (!state) return;
    // Results known before the stream (GET /runs/{id} after a reload) are shown at once, also
    // when they arrive after the run's first render.
    const shown = store.get().revealed;
    const known = knownBefore(state);
    if (!timeline.current && [...known].some((s) => !shown.has(s))) {
      store.set(restScene(state, focus, new Set([...shown, ...known]), store.get()));
    }
    if (reducedMotion) {
      timeline.current?.finish();
      timeline.current?.kill();
      timeline.current = null;
      consumed.current = state.arrivals.length;
      store.set(restScene(state, focus, undefined, store.get()));
      return;
    }
    if (!loaded) return;
    if (!timeline.current) {
      timeline.current = loaded.createLineTimeline(
        store,
        () => latest.current.state ?? state,
        () => latest.current.focus,
      );
    }
    const arrivals = state.arrivals;
    for (let i = consumed.current; i < arrivals.length; i += 1) timeline.current.push(arrivals[i]!);
    consumed.current = arrivals.length;
  }, [state, focus, reducedMotion, loaded, store]);

  // A different unit or wafer chosen while the line is at rest.
  const focusKey = focus ? `${focus.kind}:${"index" in focus ? focus.index : focus.name}` : "";
  useEffect(() => {
    const current = latest.current.state;
    if (!current) return;
    if (timeline.current) timeline.current.refocus();
    else if (!reducedMotion)
      store.set(restScene(current, latest.current.focus, store.get().revealed, store.get()));
  }, [focusKey, reducedMotion, store]);

  useEffect(() => () => timeline.current?.kill(), []);

  return {
    store,
    /** Show every arrived result now. */
    finish: () => timeline.current?.finish(),
  };
}
