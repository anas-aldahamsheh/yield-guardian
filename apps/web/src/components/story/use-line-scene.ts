"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { knownBefore, type RunState } from "@/lib/live/run-state";
import type { Focus } from "@/lib/live/url-state";

import { EMPTY_SCENE, createSceneStore, restScene, type Scene, type SceneStore } from "./scene";
import type * as TimelineModule from "./timeline";
import type { LineTimeline } from "./timeline";

/** A run's scene before anything plays: at rest with every result known before the stream. */
function sceneAtRest(state: RunState | null, focus: Focus): Scene {
  return state ? restScene(state, focus, knownBefore(state), EMPTY_SCENE) : EMPTY_SCENE;
}

/**
 * Drives the line's scene for a run. With motion, results that arrive on the stream are handed
 * to the run's GSAP timeline (loaded on the first one, so the page's first load carries no
 * animation code); without it, the scene is always at rest with every arrived result.
 *
 * Results known before the stream (a reload, a link, back and forward: the run's stored state)
 * are at rest from the first render, on the server too, so the page arrives showing them and
 * nothing replays; a run whose stored state comes later is put at rest before it is painted.
 */
export function useLineScene(state: RunState | null, focus: Focus, reducedMotion: boolean) {
  const [store] = useState<SceneStore>(() => createSceneStore(sceneAtRest(state, focus)));
  const timeline = useRef<LineTimeline | null>(null);
  const consumed = useRef(0);
  const latest = useRef({ state, focus });
  const runId = state?.runId ?? null;
  /** The run the scene shows. */
  const shows = useRef(runId);
  const [loaded, setLoaded] = useState<typeof TimelineModule | null>(null);

  useLayoutEffect(() => {
    latest.current = { state, focus };
  });

  // A new run: a fresh scene, with whatever was known before the stream at rest, before paint.
  useLayoutEffect(() => {
    if (shows.current === runId) return;
    shows.current = runId;
    timeline.current?.kill();
    timeline.current = null;
    consumed.current = 0;
    store.set(sceneAtRest(latest.current.state, latest.current.focus));
  }, [runId, store]);

  // Results known before the stream that came after the run's first render (GET /runs/{id}
  // read in the browser) are shown at once, before paint.
  useLayoutEffect(() => {
    if (!state || timeline.current) return;
    const shown = store.get().revealed;
    const known = knownBefore(state);
    if ([...known].some((s) => !shown.has(s))) {
      store.set(restScene(state, focus, new Set([...shown, ...known]), store.get()));
    }
  }, [state, focus, store]);

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
    if (reducedMotion) {
      timeline.current?.finish();
      timeline.current?.kill();
      timeline.current = null;
      consumed.current = state.arrivals.length;
      store.set(restScene(state, focus, undefined, store.get()));
      return;
    }
    if (!loaded || consumed.current >= state.arrivals.length) return;
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

  // A different unit or wafer chosen while the line is at rest (not the first render: the
  // scene starts on the unit and wafer in view).
  const focusKey = focus ? `${focus.kind}:${"index" in focus ? focus.index : focus.name}` : "";
  const focused = useRef(focusKey);
  useEffect(() => {
    if (focused.current === focusKey) return;
    focused.current = focusKey;
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
