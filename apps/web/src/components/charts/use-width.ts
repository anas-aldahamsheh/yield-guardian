"use client";

import { useLayoutEffect, useRef, useState } from "react";

/**
 * Width of an element in CSS pixels, following resizes. Starts at `initial` on the server and
 * measures before the first paint in the browser. Put the ref on an element whose width comes
 * from its container (a block with min-width 0), never from what is drawn inside it, or a wide
 * chart can hold its own container open.
 */
export function useWidth<T extends HTMLElement>(initial = 640) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(initial);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(Math.max(0, Math.round(entry.contentRect.width)));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}
