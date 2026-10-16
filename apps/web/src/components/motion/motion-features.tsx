"use client";

import { LazyMotion } from "framer-motion";
import type { ReactNode } from "react";

import { afterLoadIdle } from "@/lib/idle";

const loadFeatures = () =>
  new Promise<void>((resolve) => afterLoadIdle(resolve))
    .then(() => import("./features"))
    .then((mod) => mod.default);

/**
 * Motion's feature set for a part of a page that renders `m` components itself (the
 * investigations list): LazyMotion, strict, so a heavy `motion.*` import fails loudly, with the
 * features fetched once the page has loaded and the browser is idle.
 */
export function MotionFeatures({ children }: { children: ReactNode }) {
  return (
    <LazyMotion features={loadFeatures} strict>
      {children}
    </LazyMotion>
  );
}
