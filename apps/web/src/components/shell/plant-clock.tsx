"use client";

import type { PlantClock as Clock } from "@yield-guardian/contracts";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";

import { useApi } from "@/lib/api/context";
import { useAfterLoad } from "@/lib/idle";
import { q } from "@/lib/api/queries";
import { formatInt } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Replay position from the API's clock, advanced locally: position = floor((now - epoch) /
 * seconds_per_unit) mod units_total. The offset corrects for a skewed browser clock.
 */
export function clockPosition(clock: Clock, offsetMs: number, nowMs = Date.now()) {
  const elapsedUnits = Math.floor(
    (nowMs + offsetMs - Date.parse(clock.epoch)) / (clock.seconds_per_unit * 1000),
  );
  const total = Math.max(1, clock.units_total);
  return {
    position: ((elapsedUnits % total) + total) % total,
    cycle: Math.floor(elapsedUnits / total),
  };
}

/**
 * The line state the clock reads. The API's smallest window is still a 39 KB snapshot, so the
 * top bar asks for it once the page is idle rather than during the first load.
 */
function useClockState() {
  const api = useApi();
  const idle = useAfterLoad();
  return useQuery({ ...q.lineState(api, 10), staleTime: 5 * 60_000, enabled: idle });
}

export function usePlantClock(clock: Clock | undefined, fetchedAt: number) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!clock) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [clock]);
  if (!clock) return null;
  const offset = Date.parse(clock.now) - fetchedAt;
  return { ...clockPosition(clock, offset, now), total: clock.units_total };
}

export function PlantClockLink({ className }: { className?: string }) {
  const state = useClockState();
  const live = usePlantClock(state.data?.clock, state.dataUpdatedAt);

  return (
    <Link
      href="/line"
      className={cn(
        "flex items-center gap-2 rounded-sm px-1 text-[13px] leading-5 text-ink-2 no-underline hover:text-ink",
        className,
      )}
      aria-label={
        live
          ? `Line replay at unit ${live.position} of ${live.total}. Open the line.`
          : "Open the line"
      }
    >
      <span aria-hidden="true" className={cn("size-1.5 rounded-full", live ? "live-dot" : "bg-mark-muted")} />
      {live ? (
        <span className="tnum">
          Unit {formatInt(live.position)}
          <span className="text-ink-3"> of {formatInt(live.total)}</span>
        </span>
      ) : (
        <span>{state.isError ? "Line offline" : "Line"}</span>
      )}
    </Link>
  );
}

/**
 * Where the replay is in its cycle, as a hairline of safelight along the bottom of the top bar.
 * It repeats the position the clock link states in words, so it is hidden from assistive tech.
 */
export function ReplayTrack({ className }: { className?: string }) {
  const state = useClockState();
  const live = usePlantClock(state.data?.clock, state.dataUpdatedAt);
  if (!live) return null;
  const share = live.total > 1 ? live.position / (live.total - 1) : 0;
  return (
    <span aria-hidden="true" className={cn("pointer-events-none absolute inset-x-0 bottom-[-1px] h-px", className)}>
      <span
        className="block h-full origin-left bg-safelight transition-transform duration-[var(--dur-arrive)] ease-[var(--ease-arrive)]"
        style={{ transform: `scaleX(${share})` }}
      />
    </span>
  );
}
