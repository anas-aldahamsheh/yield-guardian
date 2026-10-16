"use client";

import { useEffect, useRef } from "react";

/** True when `el` is in the hidden part of a closed <details> (anywhere but its summary). */
function hiddenInClosedDetails(el: Element): boolean {
  const details = el.closest("details:not([open])");
  if (!details) return false;
  return !details.querySelector(":scope > summary")?.contains(el);
}

/**
 * Makes a scroll container reachable from the keyboard only while it actually scrolls: a
 * table that overflows at 375 px becomes a named region with tabindex 0 (arrow keys then
 * scroll it); the same table at 1440 px adds no tab stop and no landmark. Watches size and
 * content changes. Without `label` only the tab stop is managed (the element names itself).
 *
 * Inside a closed <details> nothing is measured: the browser lays nothing out there, and reading
 * a size would make it lay out the hidden content just to answer (the guide's closed entries
 * cost hundreds of milliseconds of a phone's load that way). Hidden content takes no tab stop
 * anyway; when the details opens, the ResizeObserver sees the container's size and measures it.
 */
export function useScrollFocus<T extends HTMLElement>(label?: string) {
  const ref = useRef<T>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => {
      if (hiddenInClosedDetails(el)) return;
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
