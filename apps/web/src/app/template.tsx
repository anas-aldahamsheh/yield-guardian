"use client";

import type { ReactNode } from "react";

import { useEntrance } from "@/components/motion/entrance";

/**
 * Every navigation mounts a new template, so a page reached from another settles in once as it
 * arrives: one opacity and rise of the whole page (`.page-enter`). The page a document opens
 * with (a first visit, a reload, a link from elsewhere) is drawn at rest. Nothing fades in
 * section by section.
 */
export default function Template({ children }: { children: ReactNode }) {
  const entrance = useEntrance();
  return <div className={entrance ? "page-enter" : undefined}>{children}</div>;
}
