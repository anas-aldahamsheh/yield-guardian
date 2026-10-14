"use client";

import type { PlantClock as Clock } from "@yield-guardian/contracts";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";

import { useApi } from "@/lib/api/context";
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
  const api = useApi();
  const state = useQuery({ ...q.lineState(api, 10), staleTime: 5 * 60_000 });
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
      <span
        aria-hidden="true"
        className={cn("size-1.5 rounded-full", live ? "bg-safelight" : "bg-mark-muted")}
      />
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
