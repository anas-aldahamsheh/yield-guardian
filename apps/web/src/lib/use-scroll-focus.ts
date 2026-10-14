"use client";

import { useEffect, useRef } from "react";

/**
 * Makes a scroll container reachable from the keyboard only while it actually scrolls: a
 * table that overflows at 375 px becomes a named region with tabindex 0 (arrow keys then
 * scroll it); the same table at 1440 px adds no tab stop and no landmark. Watches size and
 * content changes. Without `label` only the tab stop is managed (the element names itself).
 */
export function useScrollFocus<T extends HTMLElement>(label?: string) {
  const ref = useRef<T>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => {
      const scrolls = el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1;
      if (scrolls) {
        el.tabIndex = 0;
        if (label) {
          el.setAttribute("role", "region");
          el.setAttribute("aria-label", label);
        }
      } else {
        el.removeAttribute("tabindex");
        if (label) {
          el.removeAttribute("role");
          el.removeAttribute("aria-label");
        }
      }
    };
    update();
    const resize = new ResizeObserver(update);
    resize.observe(el);
    for (const child of Array.from(el.children)) resize.observe(child);
    const mutation = new MutationObserver(() => {
      for (const child of Array.from(el.children)) resize.observe(child);
      update();
    });
    mutation.observe(el, { childList: true, subtree: true });
    return () => {
      resize.disconnect();
      mutation.disconnect();
    };
  }, [label]);
  return ref;
}
