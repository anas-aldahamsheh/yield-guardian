"use client";

import { useEffect, useState } from "react";

/**
 * Calls `fn` once the page has loaded and the browser is idle, so work that is not needed for
 * the first paint never competes with it. Returns a cancel function.
 */
export function afterLoadIdle(fn: () => void, timeout = 2000): () => void {
  let cancel = () => {};
  const go = () => {
    if (typeof window.requestIdleCallback === "function") {
      const id = window.requestIdleCallback(fn, { timeout });
      cancel = () => window.cancelIdleCallback(id);
    } else {
      const id = window.setTimeout(fn, 200);
      cancel = () => window.clearTimeout(id);
    }
  };
  if (document.readyState === "complete") go();
  else window.addEventListener("load", go, { once: true });
  return () => {
    window.removeEventListener("load", go);
    cancel();
  };
}

/** True once the page has loaded and the browser is idle. */
export function useAfterLoad(timeout?: number): boolean {
  const [idle, setIdle] = useState(false);
  useEffect(() => afterLoadIdle(() => setIdle(true), timeout), [timeout]);
  return idle;
}
