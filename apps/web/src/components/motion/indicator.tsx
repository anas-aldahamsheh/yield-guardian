"use client";

import type { Transition } from "framer-motion";
import type { ReactNode } from "react";

import { SPRING } from "./springs";
import { useMotionRuntime } from "./use-motion-runtime";

/**
 * The mark on the current item of a group: the pill under a tab, a nav link or a segment, the
 * light on an open input. On the first paint it is a plain span. Once Motion has loaded (at the
 * reader's first sign of activity, see MotionProvider) it is a shared-layout span: when the
 * current item changes, the mark slides there from the old one. With `fade` it also fades in and
 * out (inside AnimatePresence), as the hover pill does. `layoutId` names the mark within its
 * LayoutGroup.
 */
export function Indicator({
  layoutId,
  className,
  transition = SPRING.layout,
  fade = false,
  children,
}: {
  layoutId: string;
  className?: string;
  transition?: Transition;
  fade?: boolean;
  children?: ReactNode;
}) {
  const runtime = useMotionRuntime();
  if (!runtime) {
    return (
      <span aria-hidden="true" className={className}>
        {children}
      </span>
    );
  }
  const { LazyMotion, domMax, m } = runtime;
  return (
    <LazyMotion features={domMax} strict>
      <m.span
        aria-hidden="true"
        layoutId={layoutId}
        transition={transition}
        className={className}
        {...(fade
          ? { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 } }
          : {})}
      >
        {children}
      </m.span>
    </LazyMotion>
  );
}
