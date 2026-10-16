"use client";

import { useEffect } from "react";

/** How far a `.magnetic` control leans toward the pointer: a share of the distance, capped. */
const PULL = 0.22;
const MAX_PULL = 7;

/**
 * The pointer's effect on the page, from one passive listener and at most one update per frame,
 * mouse and pen only; nothing re-renders:
 * - every `.glow` surface under the pointer (a card, an instrument screen) gets the pointer's place
 *   as --mx and --my, so its light follows it (globals.css);
 * - a `.magnetic` control (the primary action) leans a few pixels toward the pointer as --tx and
 *   --ty, and springs back when the pointer leaves. Not under reduced motion.
 */
export function PointerLight() {
  useEffect(() => {
    if (!window.matchMedia("(hover: hover)").matches) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0;
    let last: PointerEvent | null = null;
    let pulled: HTMLElement | null = null;

    const release = () => {
      pulled?.style.setProperty("--tx", "0px");
      pulled?.style.setProperty("--ty", "0px");
      pulled = null;
    };
    const apply = () => {
      frame = 0;
      const event = last;
      if (!event || !(event.target instanceof Element)) return;
      let el = event.target.closest<HTMLElement>(".glow");
      while (el) {
        const rect = el.getBoundingClientRect();
        el.style.setProperty("--mx", `${Math.round(event.clientX - rect.left)}px`);
        el.style.setProperty("--my", `${Math.round(event.clientY - rect.top)}px`);
        el = el.parentElement?.closest<HTMLElement>(".glow") ?? null;
      }
      const magnet = reduced.matches ? null : event.target.closest<HTMLElement>(".magnetic");
      if (magnet !== pulled) release();
      if (magnet && !(magnet as HTMLButtonElement).disabled) {
        pulled = magnet;
        const rect = magnet.getBoundingClientRect();
        const clamp = (v: number) => Math.max(-MAX_PULL, Math.min(MAX_PULL, v * PULL));
        const dx = clamp(event.clientX - (rect.left + rect.width / 2));
        const dy = clamp(event.clientY - (rect.top + rect.height / 2));
        magnet.style.setProperty("--tx", `${dx.toFixed(1)}px`);
        magnet.style.setProperty("--ty", `${dy.toFixed(1)}px`);
      }
    };
    const onMove = (event: PointerEvent) => {
      if (event.pointerType === "touch") return;
      last = event;
      if (!frame) frame = requestAnimationFrame(apply);
    };
    const onLeave = () => release();
    document.addEventListener("pointermove", onMove, { passive: true });
    document.documentElement.addEventListener("pointerleave", onLeave);
    return () => {
      document.removeEventListener("pointermove", onMove);
      document.documentElement.removeEventListener("pointerleave", onLeave);
      if (frame) cancelAnimationFrame(frame);
      release();
    };
  }, []);
  return null;
}
