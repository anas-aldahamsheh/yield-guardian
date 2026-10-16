"use client";

import { LayoutGroup } from "framer-motion";
import { useEffect, useState } from "react";

import { Indicator } from "@/components/motion/indicator";
import { cn } from "@/lib/utils";

/**
 * The experts' contents, held under the site bar while the experts' sections are on screen. The
 * section being read is marked, and the mark slides to the next section as the page scrolls.
 */
export function ExpertsNav({ sections }: { sections: readonly { id: string; label: string }[] }) {
  const [current, setCurrent] = useState<string | null>(null);

  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const visible = new Map<string, number>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries)
          visible.set(e.target.id, e.isIntersecting ? e.intersectionRatio : 0);
        // The first section, in page order, that is on screen in the reading band.
        const first = sections.find((s) => (visible.get(s.id) ?? 0) > 0);
        setCurrent(first?.id ?? null);
      },
      { rootMargin: "-30% 0px -55% 0px", threshold: [0, 0.01] },
    );
    for (const s of sections) {
      const el = document.getElementById(s.id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [sections]);

  return (
    <nav
      aria-label="For experts"
      className="sticky top-[calc(var(--bar-height)+8px)] z-20 -mx-1 mt-6 [scrollbar-width:none] overflow-x-auto rounded-full bg-canvas/94 p-1 shadow-[inset_0_0_0_1px_var(--hairline),0_10px_30px_-24px_rgb(0_0_0/0.4)] backdrop-blur-xl sm:mx-0 sm:w-fit"
    >
      <LayoutGroup id="experts-nav">
        <ul className="flex w-max items-center gap-0.5">
          {sections.map((s) => {
            const active = s.id === current;
            return (
              <li key={s.id} className="relative">
                {active ? (
                  <Indicator
                    layoutId="experts-current"
                    className="absolute inset-0 rounded-full bg-surface shadow-[inset_0_0_0_1px_var(--hairline),0_1px_2px_rgb(0_0_0/0.06)] dark:bg-surface-3"
                  />
                ) : null}
                <a
                  href={`#${s.id}`}
                  aria-current={active ? "location" : undefined}
                  className={cn(
                    "relative flex h-9 items-center rounded-full px-4 text-[13.5px] leading-5 font-[540] whitespace-nowrap no-underline transition-colors duration-(--dur-1)",
                    active ? "text-ink" : "text-ink-2 hover:text-ink",
                  )}
                >
                  {s.label}
                </a>
              </li>
            );
          })}
        </ul>
      </LayoutGroup>
    </nav>
  );
}
