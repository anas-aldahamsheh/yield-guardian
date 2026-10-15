"use client";

import type { ReactNode } from "react";

import { useScrollFocus } from "@/lib/use-scroll-focus";
import { cn } from "@/lib/utils";

/**
 * A container that scrolls sideways when its content (usually a table) is wider than the
 * screen. While it scrolls it is a named region in the tab order, so it works without a mouse.
 */
export function ScrollRegion({
  label,
  className,
  children,
}: {
  label: string;
  className?: string;
  children: ReactNode;
}) {
  const ref = useScrollFocus<HTMLDivElement>(label);
  return (
    <div ref={ref} className={cn("overflow-x-auto", className)}>
      {children}
    </div>
  );
}
