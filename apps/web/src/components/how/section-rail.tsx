"use client";

import { type MouseEvent, useCallback, useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

export interface RailItem {
  id: string;
  label: string;
  /** 0 for a top-level section, 1 for one inside it. */
  level: 0 | 1;
}

const TINT = "bg-[color-mix(in_oklab,var(--signal)_12%,transparent)]";

/**
 * Tracks the section being read, and scrolls to a section on request. While a requested scroll
 * runs, the tracking is held, so the map jumps straight to the target instead of walking through
 * every section on the way.
 */
function useSectionSpy(items: readonly RailItem[]) {
  const [current, setCurrent] = useState<string | null>(null);
  const lock = useRef<string | null>(null);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    let frame = 0;
    const read = () => {
      frame = 0;
      if (lock.current) return;
      const line = window.innerHeight * 0.3;
      const atBottom =
        window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4;
      let found: string | null = null;
      if (atBottom) found = items[items.length - 1]?.id ?? null;
      else
        for (const s of items) {
          const el = document.getElementById(s.id);
          if (el && el.getBoundingClientRect().top <= line) found = s.id;
        }
      setCurrent(found ?? items[0]?.id ?? null);
    };
    const onScroll = () => {
      if (lock.current) {
        // Release the hold once the scroll has settled.
        window.clearTimeout(timer.current);
        timer.current = window.setTimeout(() => {
          lock.current = null;
        }, 160);
        return;
      }
      if (!frame) frame = requestAnimationFrame(read);
    };
    read();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (frame) cancelAnimationFrame(frame);
      window.clearTimeout(timer.current);
    };
  }, [items]);

  const go = useCallback((id: string) => {
    const el = document.getElementById(id);
    if (!el) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    lock.current = id;
    setCurrent(id);
    window.clearTimeout(timer.current);
    // If the page is already there and no scroll happens, release the hold anyway.
    timer.current = window.setTimeout(() => {
      lock.current = null;
    }, 1200);
    el.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    window.history.replaceState(null, "", `#${id}`);
    const heading = el.querySelector("h2, h3") ?? el;
    if (!reduce && "animate" in heading)
      heading.animate(
        [{ backgroundColor: "color-mix(in oklab, var(--signal) 18%, transparent)" }, { backgroundColor: "transparent" }],
        { duration: 1400, easing: "ease-out", delay: 350 },
      );
  }, []);

  return { current, go };
}

function groupsOf(items: readonly RailItem[]) {
  const groups: { head: RailItem; children: RailItem[] }[] = [];
  for (const s of items) {
    if (s.level === 0 || groups.length === 0) groups.push({ head: s, children: [] });
    else groups[groups.length - 1]!.children.push(s);
  }
  return groups;
}

/**
 * The section map of How it works: a sticky card on wide screens, one numbered group per
 * top-level section. Only the group being read is open; a click scrolls straight to a section.
 */
export function SectionRail({ items }: { items: readonly RailItem[] }) {
  const { current, go } = useSectionSpy(items);
  const navRef = useRef<HTMLElement>(null);
  const groups = groupsOf(items);
  const openGroup =
    groups.find((g) => g.head.id === current || g.children.some((c) => c.id === current)) ??
    groups[0];

  // Keep the marked link in view inside the map.
  useEffect(() => {
    if (!current) return;
    const link = navRef.current?.querySelector<HTMLElement>(`[data-id="${current}"]`);
    link?.scrollIntoView({ block: "nearest" });
  }, [current]);

  const click = (e: MouseEvent<HTMLAnchorElement>, id: string) => {
    e.preventDefault();
    go(id);
  };

  return (
    <nav
      ref={navRef}
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
                data-id={g.head.id}
                onClick={(e) => click(e, g.head.id)}
                aria-current={headActive ? "location" : undefined}
                aria-expanded={g.children.length ? open : undefined}
                className={cn(
                  "flex items-center gap-2.5 rounded-[12px] px-2.5 py-2 text-[13.5px] leading-5 font-[620] no-underline transition-colors duration-(--dur-2)",
                  open ? "text-ink" : "text-ink-2 hover:bg-surface-2 hover:text-ink",
                  headActive && TINT,
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
                            data-id={c.id}
                            onClick={(e) => click(e, c.id)}
                            tabIndex={open ? undefined : -1}
                            aria-current={active ? "location" : undefined}
                            className={cn(
                              "-ms-px block rounded-e-[10px] border-s-2 py-1.5 ps-3.5 pe-2 text-[13px] leading-5 no-underline transition-[color,background-color,border-color] duration-(--dur-2)",
                              active
                                ? cn("border-[var(--signal)] font-[580] text-[var(--signal)]", TINT)
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
      <button
        type="button"
        onClick={() => {
          const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
          window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
        }}
        className="mt-2 w-full rounded-[12px] border-t border-hairline px-2.5 pt-2.5 pb-1.5 text-start text-[12.5px] leading-5 font-[520] text-ink-3 transition-colors hover:text-ink"
      >
        Back to top
      </button>
    </nav>
  );
}

/** The section map on narrow screens: a sticky "On this page" menu under the site bar. */
export function SectionMenu({ items }: { items: readonly RailItem[] }) {
  const { current, go } = useSectionSpy(items);
  const [open, setOpen] = useState(false);
  const label = items.find((s) => s.id === current)?.label ?? "On this page";

  return (
    <div className="sticky top-[calc(var(--bar-height)+8px)] z-20 mb-8 lg:hidden">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-3 rounded-[16px] bg-surface/95 px-4 py-3 text-start shadow-[inset_0_0_0_1px_var(--hairline),0_10px_30px_-24px_rgb(0_0_0/0.4)] backdrop-blur-xl"
      >
        <span className="min-w-0">
          <span className="block text-[11.5px] leading-4 text-ink-3">On this page</span>
          <span className="block truncate text-[14px] leading-5 font-[600] text-ink">{label}</span>
        </span>
        <span
          aria-hidden="true"
          className={cn("text-ink-3 transition-transform duration-(--dur-2)", open && "rotate-180")}
        >
          ▾
        </span>
      </button>
      {open ? (
        <ol className="mt-2 max-h-[60dvh] overflow-y-auto rounded-[16px] bg-surface p-2 shadow-[inset_0_0_0_1px_var(--hairline),0_20px_40px_-24px_rgb(0_0_0/0.5)]">
          {items.map((s) => (
            <li key={s.id}>
              <a
                href={`#${s.id}`}
                onClick={(e) => {
                  e.preventDefault();
                  setOpen(false);
                  go(s.id);
                }}
                aria-current={s.id === current ? "location" : undefined}
                className={cn(
                  "block rounded-[10px] py-2 pe-3 text-[14px] leading-5 no-underline",
                  s.level === 0 ? "ps-3 font-[620] text-ink" : "ps-7 font-[460] text-ink-2",
                  s.id === current && cn("text-[var(--signal)]", TINT),
                )}
              >
                {s.label}
              </a>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}
