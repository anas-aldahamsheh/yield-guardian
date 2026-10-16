"use client";

import { LayoutGroup } from "framer-motion";
import Link from "next/link";
import { useState } from "react";

import { Indicator } from "@/components/motion/indicator";
import { cn } from "@/lib/utils";

/**
 * A page's views as address-backed tabs: links in a segmented control, the current one on a pill
 * that slides to the view chosen. The pill moves as soon as a view is chosen; `aria-current`
 * follows the address.
 */
export function ViewTabs({
  label,
  items,
  current,
  className,
}: {
  label: string;
  items: readonly { id: string; label: string; href: string }[];
  current: string;
  className?: string;
}) {
  const [chosen, setChosen] = useState<string | null>(null);
  const [seen, setSeen] = useState(current);
  if (seen !== current) {
    setSeen(current);
    setChosen(null);
  }
  const shown = chosen ?? current;

  return (
    <nav
      aria-label={label}
      className={cn(
        "w-fit max-w-full [scrollbar-width:none] overflow-x-auto rounded-full bg-surface-2 p-1 shadow-[inset_0_0_0_1px_var(--hairline)]",
        className,
      )}
    >
      <LayoutGroup id={`view-tabs-${label}`}>
        <ul className="flex w-max items-center gap-0.5">
          {items.map((t) => {
            const active = t.id === current;
            return (
              <li key={t.id} className="relative">
                {t.id === shown ? (
                  <Indicator
                    layoutId="view-tab"
                    className="absolute inset-0 rounded-full bg-surface shadow-[inset_0_0_0_1px_var(--hairline),0_1px_2px_rgb(0_0_0/0.08),0_6px_16px_-8px_rgb(0_0_0/0.25)] dark:bg-surface-3"
                  />
                ) : null}
                <Link
                  href={t.href}
                  scroll={false}
                  aria-current={active ? "page" : undefined}
                  onClick={() => setChosen(t.id)}
                  className={cn(
                    "press relative flex h-10 items-center rounded-full px-5 text-[14.5px] leading-5 font-[580] whitespace-nowrap no-underline",
                    t.id === shown ? "text-ink" : "text-ink-2 hover:text-ink",
                  )}
                >
                  {t.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </LayoutGroup>
    </nav>
  );
}
