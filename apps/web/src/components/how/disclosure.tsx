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
      className={cn("group panel", className)}
      onToggle={(e) => e.currentTarget.open && setOpened(true)}
    >
      <summary className="flex cursor-pointer list-none items-start justify-between gap-4 px-4 py-3.5 sm:px-5 [&::-webkit-details-marker]:hidden">
        <span className="min-w-0">
          <span className="block text-[15px] leading-6 font-semibold text-ink">{title}</span>
          {summary ? (
            <span className="block text-[13px] leading-5 text-ink-3">{summary}</span>
          ) : null}
        </span>
        <ChevronDown
          aria-hidden="true"
          className="mt-1 size-4 shrink-0 text-ink-3 transition-transform group-open:rotate-180"
        />
      </summary>
      <div className="border-t border-hairline bg-room p-0 pt-street">
        {opened ? children : null}
      </div>
    </details>
  );
}
