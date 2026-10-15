"use client";

import type { Alarm } from "@yield-guardian/contracts";
import Link from "next/link";
import { useState } from "react";

import { useNewIds } from "@/components/motion";
import { Panel } from "@/components/page";
import { EmptyState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { useStartInvestigation } from "@/lib/api/investigations";
import { useSession, useStartGuestSession } from "@/lib/api/session";
import { formatInt, formatPlantTime, formatProbability, formatReading } from "@/lib/format";
import { ALARM_KIND } from "@/lib/labels";
import { investigationHref, unitHref } from "@/lib/routes";
import { cn } from "@/lib/utils";

const SHOWN = 6;

function reading(alarm: Alarm, value: number | null) {
  if (value == null) return "–";
  return alarm.kind === "risk" ? formatProbability(value) : formatReading(value, 3);
}

/** Open alarms, newest first. Each can become an investigation. */
export function OpenAlarms({ alarms, className }: { alarms: Alarm[]; className?: string }) {
  const [all, setAll] = useState(false);
  const { canAct } = useSession();
  const guest = useStartGuestSession();
  const start = useStartInvestigation();
  const shown = all ? alarms : alarms.slice(0, SHOWN);
  const fresh = useNewIds(alarms.map((a) => a.alarm_id));

  return (
    <Panel
      title="Open alarms"
      description={`${formatInt(alarms.length)} open, newest first. Messages are written by the alarm rules.`}
      className={className}
      bodyClassName="px-0 sm:px-0 pb-2"
    >
      {alarms.length === 0 ? (
        <EmptyState title="No open alarms" className="mx-4 sm:mx-5">
          Alarms appear here when a unit crosses a risk threshold or a control limit.
        </EmptyState>
      ) : (
        <>
          {!canAct ? (
            <div className="mx-4 mb-2 flex flex-wrap items-center justify-between gap-2 rounded-sm bg-die-2 px-3 py-2 sm:mx-5">
              <p className="text-[13px] leading-5 text-ink-2">Investigating an alarm needs an engineer session.</p>
              <Button size="sm" variant="outline" onClick={() => guest.mutate()} disabled={guest.isPending}>
                {guest.isPending ? "Signing in…" : "Try as engineer"}
              </Button>
            </div>
          ) : null}
          <ol className="divide-y divide-hairline border-t border-hairline">
            {shown.map((alarm) => (
              <li
                key={alarm.alarm_id}
                className={cn("px-4 py-3 sm:px-5", fresh.has(alarm.alarm_id) && (alarm.severity === "alarm" ? "flash-alarm" : "flash-new"))}
              >
                <div className="flex items-baseline justify-between gap-3">
                  <p className="flex min-w-0 items-baseline gap-2 text-[14px] leading-5">
                    <span
                      aria-hidden="true"
                      className={cn(
                        "size-2 shrink-0 translate-y-[-1px] rounded-full",
                        alarm.severity === "alarm" ? "bg-fail" : "bg-concern",
                      )}
                    />
                    <span className="font-medium text-ink">{ALARM_KIND[alarm.kind] ?? alarm.kind}</span>
                    <span className="text-ink-3">{alarm.severity === "alarm" ? "Alarm" : "Warning"}</span>
                  </p>
                  <Link
                    href={unitHref(alarm.unit_id)}
                    className="tnum shrink-0 text-[13px] text-ink-2 underline decoration-hairline-strong underline-offset-4 hover:text-ink"
                  >
                    Unit {formatInt(alarm.unit_id)}
                  </Link>
                </div>
                <p className="mt-1 text-[14px] leading-5 text-ink-2">{alarm.message}</p>
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                  <p className="tnum text-[12px] leading-4 text-ink-3">
                    {reading(alarm, alarm.value)} against {reading(alarm, alarm.limit)}, {formatPlantTime(alarm.timestamp)}
                  </p>
                  {alarm.investigation_id ? (
                    <Link
                      href={investigationHref(alarm.investigation_id)}
                      className="text-[13px] text-ink underline decoration-hairline-strong underline-offset-4 hover:decoration-ink"
                    >
                      Open investigation
                    </Link>
                  ) : canAct ? (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={start.isPending}
                      onClick={() => start.mutate({ kind: "alarm", ref: alarm.alarm_id })}
                    >
                      {start.isPending && start.variables?.ref === alarm.alarm_id ? "Starting…" : "Investigate"}
                    </Button>
                  ) : null}
                </div>
              </li>
            ))}
          </ol>
          {alarms.length > SHOWN ? (
            <div className="border-t border-hairline px-4 pt-2 sm:px-5">
              <Button variant="ghost" size="sm" onClick={() => setAll((v) => !v)} className="-ml-2">
                {all ? "Show fewer" : `Show all ${formatInt(alarms.length)}`}
              </Button>
            </div>
          ) : null}
        </>
      )}
    </Panel>
  );
}
