"use client";

import { useEffect, type RefObject } from "react";

/**
 * The floating Ask button takes the bottom of the screen: 16 px from the edge, 48 px tall, and
 * a margin (the footer keeps the same 96 px free at the end of every page).
 */
export const ASK_CLEARANCE = 96;

/**
 * Writes `--viewport-room` on the element: the height from its top to the Ask button's band at
 * the bottom of the screen. A panel beside the line (out of the page's flow, so its height moves
 * nothing else) caps its height with it, so no line of it sits under the button wherever the page
 * is scrolled. Measured at most once a frame: on scroll while the element is on screen, and when
 * the window or the page's content changes size.
 */
export function useViewportRoom(ref: RefObject<HTMLElement | null>, clearance = ASK_CLEARANCE) {
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined" || typeof ResizeObserver === "undefined")
      return;
    let frame = 0;
    let last = Number.NaN;
    const measure = () => {
      frame = 0;
      const room = Math.round(window.innerHeight - el.getBoundingClientRect().top - clearance);
      if (room !== last) {
        last = room;
        el.style.setProperty("--viewport-room", `${room}px`);
      }
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(measure);
    };
    let listening = false;
    const listen = (on: boolean) => {
      if (on === listening) return;
      listening = on;
      if (on) window.addEventListener("scroll", schedule, { passive: true });
      else window.removeEventListener("scroll", schedule);
    };
    const seen = new IntersectionObserver(([entry]) => {
      listen(Boolean(entry?.isIntersecting));
      schedule();
    });
    seen.observe(el);
    // Content above it (the run's heading, a banner) moves it without a scroll.
    const moved = new ResizeObserver(schedule);
    moved.observe(document.body);
    window.addEventListener("resize", schedule);
    schedule();
    return () => {
      seen.disconnect();
      moved.disconnect();
      listen(false);
      window.removeEventListener("resize", schedule);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [ref, clearance]);
}
