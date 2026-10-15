"use client";

import { useEffect, useState } from "react";

import { formatInt } from "@/lib/format";

/** "45 s", "2 min 05 s", "1 h 04 min": elapsed time as an engineer reads it. */
export function formatElapsed(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s} s`;
  const pad = (n: number) => String(n).padStart(2, "0");
  if (s < 3600) return `${Math.floor(s / 60)} min ${pad(s % 60)} s`;
  return `${formatInt(Math.floor(s / 3600))} h ${pad(Math.floor((s % 3600) / 60))} min`;
}

/**
 * The current time, once a second while `active`; null until the page has mounted, so the
 * server and the first client render agree (no time-dependent markup before hydration).
 */
export function useNow(active: boolean): number | null {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    if (!active) return;
    const tick = () => setNow(Date.now());
    const first = window.setTimeout(tick, 0);
    const id = window.setInterval(tick, 1000);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(id);
    };
  }, [active]);
  return active ? now : null;
}

/**
 * Real elapsed time from `from`: to `to` when the work has finished, otherwise to now, counting
 * while it runs. Nothing is estimated; a run with no end and no clock yet shows a dash.
 */
export function Elapsed({
  from,
  to,
  running,
  className,
}: {
  from: string;
  to?: string | null;
  running: boolean;
  className?: string;
}) {
  const now = useNow(running);
  const start = Date.parse(from);
  const end = running ? now : to ? Date.parse(to) : null;
  const text = end == null || Number.isNaN(start) ? "–" : formatElapsed(end - start);
  return (
    <span className={className} data-elapsed={running ? "running" : "done"}>
      <span className="tnum">{text}</span>
    </span>
  );
}
