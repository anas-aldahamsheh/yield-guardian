"use client";

import { useSyncExternalStore } from "react";

import { formatDateTime, formatDateTimeUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

const subscribe = () => () => {};

/**
 * A product event time in the viewer's time zone. The server does not know that zone, so the
 * server render and hydration show UTC (labelled), and the local time follows straight after:
 * the HTML always matches what hydration renders, with no hydration error.
 */
export function LocalDateTime({
  iso,
  timeOnly = false,
  className,
}: {
  iso: string | null | undefined;
  /** Only the hours and minutes, for a list within one day. */
  timeOnly?: boolean;
  className?: string;
}) {
  const local = useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
  const text = local ? formatDateTime(iso) : formatDateTimeUtc(iso);
  return (
    <time dateTime={iso ?? undefined} className={cn(className)}>
      {timeOnly && iso ? text.slice(11) : text}
    </time>
  );
}
