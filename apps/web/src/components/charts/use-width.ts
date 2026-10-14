"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * Width of an element in CSS pixels, following resizes. Starts at `initial` on the server and
 * measures as soon as the element is attached in the browser. The ref is a callback ref, so an
 * element that appears later (after data loads, or behind a toggle) is measured too. Put it on an
 * element whose width comes from its container (a block with min-width 0), never from what is
 * drawn inside it, or a wide chart can hold its own container open.
 */
export function useWidth<T extends HTMLElement>(initial = 640) {
  const [element, setElement] = useState<T | null>(null);
  const [width, setWidth] = useState(initial);
  const ref = useCallback((node: T | null) => setElement(node), []);
  useEffect(() => {
    if (!element) return;
    const measure = (value: number) => setWidth(Math.max(0, Math.round(value)));
    measure(element.getBoundingClientRect().width);
    const observer = new ResizeObserver(([entry]) => {
      if (entry) measure(entry.contentRect.width);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);
  return [ref, width] as const;
}
