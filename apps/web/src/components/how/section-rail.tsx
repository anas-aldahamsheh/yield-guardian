"use client";

import { type MouseEvent, useEffect, useState } from "react";

import { cn } from "@/lib/utils";

export interface RailItem {
  id: string;
  label: string;
  /** 0 for a top-level section, 1 for one inside it. */
  level: 0 | 1;
}

/**
 * The section map of How it works: a sticky vertical rail on wide screens, one node per section
 * joined by a thin line. A click scrolls to the section; the section being read is marked.
 */
export function SectionRail({ items }: { items: readonly RailItem[] }) {
  const [current, setCurrent] = useState<string | null>(null);

  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const visible = new Set<string>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) visible.add(e.target.id);
          else visible.delete(e.target.id);
        }
        // The deepest section, in page order, crossing the reading band.
        const last = [...items].reverse().find((s) => visible.has(s.id));
        if (last) setCurrent(last.id);
      },
      { rootMargin: "-25% 0px -65% 0px", threshold: 0 },
    );
    for (const s of items) {
      const el = document.getElementById(s.id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [items]);

  const go = (e: MouseEvent<HTMLAnchorElement>, id: string) => {
    const el = document.getElementById(id);
    if (!el) return;
    e.preventDefault();
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    window.history.replaceState(null, "", `#${id}`);
    setCurrent(id);
  };

  return (
    <nav
      aria-label="On this page"
      className="sticky top-[calc(var(--bar-height)+32px)] max-h-[calc(100dvh-var(--bar-height)-64px)] [scrollbar-width:none] overflow-y-auto"
    >
      <span aria-hidden="true" className="absolute top-3 bottom-3 left-[5px] w-px bg-hairline" />
      <ol className="relative grid gap-0.5">
        {items.map((s) => {
          const active = s.id === current;
          return (
            <li key={s.id} className="relative">
              <a
                href={`#${s.id}`}
                onClick={(e) => go(e, s.id)}
                aria-current={active ? "location" : undefined}
                className={cn(
                  "group flex items-center gap-3 py-1 no-underline transition-colors duration-(--dur-1)",
                  s.level === 0
                    ? "text-[13px] leading-5 font-[600]"
                    : "text-[12.5px] leading-5 font-[480]",
                  active ? "text-ink" : "text-ink-3 hover:text-ink",
                )}
              >
                <span
                  aria-hidden="true"
                  className="relative z-[1] grid size-[11px] shrink-0 place-items-center rounded-full bg-canvas"
                >
                  <span
                    className={cn(
                      "rounded-full transition-[background-color,box-shadow,width,height] duration-(--dur-2)",
                      s.level === 0 ? "size-[9px]" : "size-[7px]",
                      active
                        ? "bg-[var(--signal)] shadow-[0_0_0_3px_var(--signal-wash)]"
                        : "bg-canvas shadow-[inset_0_0_0_1.5px_var(--hairline-strong)] group-hover:shadow-[inset_0_0_0_1.5px_var(--ink-3)]",
                    )}
                  />
                </span>
                <span className={cn("min-w-0 truncate", s.level === 1 && "ps-1")}>{s.label}</span>
              </a>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
