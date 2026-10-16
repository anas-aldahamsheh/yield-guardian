"use client";

import { ChevronDown } from "lucide-react";
import { type ReactNode, useState } from "react";

import { cn } from "@/lib/utils";

/**
 * A section that opens in place. Its content mounts the first time it opens and stays mounted,
 * so a long chart-heavy section costs nothing until someone asks for it.
 */
export function Disclosure({
  title,
  summary,
  children,
  className,
  id,
}: {
  title: string;
  summary?: string;
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  const [opened, setOpened] = useState(false);
  return (
    <details
      id={id}
      className={cn("group/disclosure panel glow", className)}
      onToggle={(e) => e.currentTarget.open && setOpened(true)}
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-5 rounded-[inherit] px-5 py-4.5 sm:px-6 sm:py-5 [&::-webkit-details-marker]:hidden">
        <span className="min-w-0">
          <span className="block text-[16px] leading-6 font-[630] tracking-[-0.01em] text-ink sm:text-[17px]">
            {title}
          </span>
          {summary ? (
            <span className="mt-0.5 block text-[13.5px] leading-5 text-ink-2">{summary}</span>
          ) : null}
        </span>
        <span
          aria-hidden="true"
          className="grid size-9 shrink-0 place-items-center rounded-full bg-surface-2 text-ink-2 transition-[background-color,color,rotate] duration-(--dur-4) ease-spring group-open/disclosure:rotate-180 group-open/disclosure:bg-ink! group-open/disclosure:text-canvas! group-hover/disclosure:bg-surface-3"
        >
          <ChevronDown className="size-4" strokeWidth={2} />
        </span>
      </summary>
      <div className="grow-in rounded-b-[inherit] border-t border-hairline bg-canvas pt-street">
        {opened ? children : null}
      </div>
    </details>
  );
}
