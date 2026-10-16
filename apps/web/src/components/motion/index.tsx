"use client";

/**
 * Motion hooks shared by the whole interface (docs/DESIGN.md, "Motion"). Springs live in
 * `./springs`, the Motion provider in `./motion-provider`; keyframes and spring curves for CSS in
 * globals.css. Every hook respects prefers-reduced-motion.
 *
 * - Page arrival: `app/template.tsx` settles each page in once (`.page-enter`).
 * - Lists: `.flash-new` / `.flash-alarm` on a row that just arrived (once, keyed by its id).
 * - Numbers: `<Ticker>` runs a reading from its old value to its new one when a result arrives.
 * - Charts: `useFirstSeen` starts a chart's drawing the first time it is on screen.
 * - Swapped content: `.swap-in`, keyed so it replays when the content changes.
 */

import { useEffect, useRef, useState, useSyncExternalStore, type RefObject } from "react";

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

/** Expo-out: fast at first, settling exactly on the value. */
const easeOutExpo = (t: number) => (t >= 1 ? 1 : 1 - 2 ** (-10 * t));

/**
 * A number that runs from its previous value to `value` over `duration` ms. With `from`, the
 * first render starts there (a count that arrives starts at 0). Jumps straight to the value under
 * reduced motion, and when the change is not a finite number.
 */
export function useTicker(
  value: number,
  { duration = 900, from }: { duration?: number; from?: number } = {},
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
      const v = start + (value - start) * easeOutExpo(t);
      shownRef.current = v;
      setShown(v);
      if (t < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [value, duration, reduced]);

  return shown;
}

/** A reading that runs to its new value. `format` turns the number into text. */
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
 * an element that carries a one-shot CSS animation (`.flash-new`, `.swap-in`, a sweep of light).
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

/**
 * False until the element has been on screen once, then true for good: a chart draws its real
 * series the first time it is seen. True at once under reduced motion and where
 * IntersectionObserver is missing.
 */
export function useFirstSeen(ref: RefObject<Element | null>, margin = "0px 0px -10% 0px"): boolean {
  const reduced = usePrefersReducedMotion();
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    if (seen) return;
    const el = ref.current;
    if (reduced || !el || typeof IntersectionObserver === "undefined") {
      setSeen(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setSeen(true);
          observer.disconnect();
        }
      },
      { rootMargin: margin },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref, reduced, seen, margin]);
  return seen;
}
