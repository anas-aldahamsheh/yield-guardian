"use client";

import { MotionConfig } from "framer-motion";
import { useEffect, type ReactNode } from "react";

import { SPRING } from "./springs";
import { loadMotionRuntime } from "./use-motion-runtime";

/** What a reader does before anything on the page can move: point, touch, type, scroll. */
const FIRST_SIGNS = ["pointermove", "pointerdown", "touchstart", "keydown", "focusin", "scroll"];

/**
 * Motion for the whole app: the interface's layout spring as the default transition, and the
 * reader's reduced-motion setting respected everywhere. Nothing moves on the first paint, so
 * Motion's renderer and feature set (`Indicator`, `MotionFeatures`) are not part of any first
 * load: the sliding marks fetch them at the reader's first sign of activity, before a mark has
 * anywhere to slide to.
 */
export function MotionProvider({ children, nonce }: { children: ReactNode; nonce?: string }) {
  useEffect(() => {
    const start = () => {
      for (const type of FIRST_SIGNS) window.removeEventListener(type, start, true);
      void loadMotionRuntime().catch(() => undefined);
    };
    for (const type of FIRST_SIGNS)
      window.addEventListener(type, start, { capture: true, passive: true });
    return () => {
      for (const type of FIRST_SIGNS) window.removeEventListener(type, start, true);
    };
  }, []);
  return (
    <MotionConfig reducedMotion="user" transition={SPRING.layout} nonce={nonce}>
      {children}
    </MotionConfig>
  );
}
