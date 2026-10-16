import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * A word that qualifies the item beside it, on a small chip: "Recorded" on a replayed
 * investigation, "Example" on what belongs to the recorded example every visitor sees.
 */
export function Tag({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center rounded-full bg-surface-2 px-2 align-[1px] text-[12px] leading-4 font-[520] whitespace-nowrap text-ink-2 shadow-[inset_0_0_0_1px_var(--hairline)]",
        className,
      )}
    >
      {children}
    </span>
  );
}
