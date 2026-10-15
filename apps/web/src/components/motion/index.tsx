"use client";

/**
 * The console's motion, in one place. Motion here is CSS keyframes (globals.css) plus a few
 * small hooks, so it costs almost nothing in the bundle and every piece respects
 * prefers-reduced-motion. docs/DESIGN.md explains when to use which.
 *
 * - Page arrival: `PageFrame` carries `.page-enter`; nothing else fades in on load.
 * - Lists: `.flash-new` / `.flash-alarm` on a row that just arrived (once, keyed by its id).
 * - Numbers: `<Ticker>` eases a reading from its old value to its new one.
 * - Charts: `.arrival` (safelight ring on the newest point), `.alarm-pulse` (fail rings).
 * - Swapped content: `.swap-in`, keyed so it replays when the content changes.
 * - Home only: `.rise-line` and `.stage-in` for the one orchestrated page-load sequence.
 */

import { useEffect, useRef, useState, useSyncExternalStore } from "react";

function subscribeReducedMotion(callback: () => void) {
  const query = window.matchMedia("(prefers-reduced-motion: reduce)");
  query.addEventListener("change", callback);
  return () => query.removeEventListener("change", callback);
}

/** True when the reader asked for reduced motion. False on the server. */
export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeReducedMotion,
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => false,
  );
}

const easeOutCubic = (t: number) => 1 - (1 - t) ** 3;

/**
 * A number that eases from its previous value to `value` over `duration` ms. With `from`, the
 * first render starts there (the home page's counters start at 0). Jumps straight to the value
 * under reduced motion, and when the change is not a finite number.
 */
export function useTicker(
  value: number,
  { duration = 600, from }: { duration?: number; from?: number } = {},
) {
  const reduced = usePrefersReducedMotion();
  const [shown, setShown] = useState(from ?? value);
  const shownRef = useRef(shown);

  useEffect(() => {
    const start = shownRef.current;
    if (reduced || !Number.isFinite(start) || !Number.isFinite(value) || start === value) {
      shownRef.current = value;
      setShown(value);
      return;
    }
    let frame = 0;
    const t0 = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - t0) / duration);
      const v = start + (value - start) * easeOutCubic(t);
      shownRef.current = v;
      setShown(v);
      if (t < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [value, duration, reduced]);

  return shown;
}

/** A reading that ticks to its new value. `format` turns the number into text. */
export function Ticker({
  value,
  format,
  duration,
  from,
  className,
}: {
  value: number;
  format: (value: number) => string;
  duration?: number;
  from?: number;
  className?: string;
}) {
  const shown = useTicker(value, { duration, from });
  return <span className={className}>{format(shown)}</span>;
}

/**
 * Returns a key that changes each time `signal` changes after the first render, for remounting
 * an element that carries a one-shot CSS animation (`.flash-new`, `.arrival`, `.swap-in`).
 * Returns null until the first change, so nothing animates on page load.
 */
export function useChangeKey(signal: unknown): number | null {
  const [state, setState] = useState<{ signal: unknown; count: number | null }>({
    signal,
    count: null,
  });
  if (!Object.is(state.signal, signal)) {
    setState({ signal, count: (state.count ?? 0) + 1 });
  }
  return state.count;
}

/**
 * Ids that are new since the previous render of a list (an alarm, a unit), so their rows can be
 * lit once. Ids present on the first render never count as new.
 */
export function useNewIds(ids: readonly string[]): ReadonlySet<string> {
  const seen = useRef<Set<string> | null>(null);
  const [fresh, setFresh] = useState<ReadonlySet<string>>(() => new Set());
  const joined = ids.join("\u0000");
  useEffect(() => {
    if (seen.current == null) {
      seen.current = new Set(ids);
      return;
    }
    const next = new Set(ids.filter((id) => !seen.current!.has(id)));
    for (const id of ids) seen.current.add(id);
    // A handful of new ids is arrivals; many at once is a reload or a new window, not news.
    if (next.size > 0 && next.size <= 3) setFresh(next);
    // `joined` stands for `ids`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [joined]);
  return fresh;
}
