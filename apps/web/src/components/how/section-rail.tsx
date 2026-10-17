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

  // Groups: a top-level section and the sections under it. Only the group being read is open.
  const groups: { head: RailItem; children: RailItem[] }[] = [];
  for (const s of items) {
    if (s.level === 0 || groups.length === 0) groups.push({ head: s, children: [] });
    else groups[groups.length - 1]!.children.push(s);
  }
  const openGroup =
    groups.find((g) => g.head.id === current || g.children.some((c) => c.id === current)) ??
    groups[0];
  const tint = "bg-[color-mix(in_oklab,var(--signal)_12%,transparent)]";

  return (
    <nav
      aria-label="On this page"
      className="sticky top-[calc(var(--bar-height)+32px)] max-h-[calc(100dvh-var(--bar-height)-64px)] [scrollbar-width:none] overflow-y-auto rounded-[22px] bg-surface p-3 shadow-[inset_0_0_0_1px_var(--hairline),var(--highlight)]"
    >
      <p className="px-2.5 pt-1 pb-2.5 text-[12px] leading-4 font-[560] text-ink-3">On this page</p>
      <ol className="grid gap-1">
        {groups.map((g, gi) => {
          const open = g === openGroup;
          const headActive = g.head.id === current;
          return (
            <li key={g.head.id}>
              <a
                href={`#${g.head.id}`}
                onClick={(e) => go(e, g.head.id)}
                aria-current={headActive ? "location" : undefined}
                aria-expanded={g.children.length ? open : undefined}
                className={cn(
                  "flex items-center gap-2.5 rounded-[12px] px-2.5 py-2 text-[13.5px] leading-5 font-[620] no-underline transition-colors duration-(--dur-2)",
                  open ? "text-ink" : "text-ink-2 hover:bg-surface-2 hover:text-ink",
                  headActive && tint,
                )}
              >
                <span
                  aria-hidden="true"
                  className={cn(
                    "tnum grid size-5 shrink-0 place-items-center rounded-full text-[11px] leading-none font-[640] transition-colors duration-(--dur-2)",
                    open
                      ? "bg-[var(--signal)] text-white"
                      : "text-ink-3 shadow-[inset_0_0_0_1.5px_var(--hairline-strong)]",
                  )}
                >
                  {gi + 1}
                </span>
                {g.head.label}
              </a>
              {g.children.length ? (
                <div
                  className={cn(
                    "grid transition-[grid-template-rows,opacity] duration-(--dur-3) ease-out motion-reduce:transition-none",
                    open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
                  )}
                >
                  <ol className="ms-[19px] min-h-0 overflow-hidden border-s border-hairline">
                    {g.children.map((c) => {
                      const active = c.id === current;
                      return (
                        <li key={c.id} className="py-px">
                          <a
                            href={`#${c.id}`}
                            onClick={(e) => go(e, c.id)}
                            tabIndex={open ? undefined : -1}
                            aria-current={active ? "location" : undefined}
                            className={cn(
                              "-ms-px block rounded-e-[10px] border-s-2 py-1.5 ps-3.5 pe-2 text-[13px] leading-5 no-underline transition-[color,background-color,border-color] duration-(--dur-2)",
                              active
                                ? cn("border-[var(--signal)] font-[580] text-[var(--signal)]", tint)
                                : "border-transparent font-[460] text-ink-2 hover:text-ink",
                            )}
                          >
                            {c.label}
                          </a>
                        </li>
                      );
                    })}
                  </ol>
                </div>
              ) : null}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
