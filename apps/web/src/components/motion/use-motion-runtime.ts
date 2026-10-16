"use client";

import { useSyncExternalStore } from "react";

import type * as RuntimeModule from "./runtime";

type Runtime = typeof RuntimeModule;

let runtime: Runtime | null = null;
let loading: Promise<Runtime> | null = null;
const listeners = new Set<() => void>();

/**
 * Fetches Motion's components once (MotionProvider calls it at the reader's first sign of
 * activity). Every mark that waits for them re-renders when they arrive.
 */
export function loadMotionRuntime(): Promise<Runtime> {
  loading ??= import("./runtime").then(
    (mod) => {
      runtime = mod;
      for (const listener of listeners) listener();
      return mod;
    },
    (error: unknown) => {
      loading = null;
      throw error;
    },
  );
  return loading;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Motion's components once they have loaded; null on the server and until then. */
export function useMotionRuntime(): Runtime | null {
  return useSyncExternalStore(
    subscribe,
    () => runtime,
    () => null,
  );
}
