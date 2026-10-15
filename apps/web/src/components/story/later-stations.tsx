"use client";

import { useQuery } from "@tanstack/react-query";
import type { RunAlarm } from "@yield-guardian/contracts";
import Link from "next/link";

import { StatusLabel } from "@/components/investigation/status-label";
import { useApi } from "@/lib/api/context";
import { q } from "@/lib/api/queries";
import { useInvestigationStream } from "@/lib/investigation/use-investigation-stream";
import { plural } from "@/lib/format";
import type { RunState } from "@/lib/live/run-state";
import { investigationHref } from "@/lib/routes";
import { cn } from "@/lib/utils";

/**
 * Stations 4 and 5 work on demand: an investigation starts from an alarm, and a decision is an
 * engineer's on its report. Under the line they list what this run has started, as it streams.
 */
export function LaterStations({
  state,
  focused,
}: {
  state: RunState | null;
  focused: 4 | 5 | null;
}) {
  const linked = state
    ? state.alarms.filter(
        (a): a is RunAlarm & { investigation_id: string } => a.investigation_id != null,
      )
    : [];
  return (
    <div className="mt-6 grid grid-cols-[minmax(0,1fr)] gap-4 md:grid-cols-2">
      <section
        id="station-4"
        aria-labelledby="station-4-title"
        className={cn("panel px-4 py-4 sm:px-5", focused === 4 && "lit")}
      >
        <h2 id="station-4-title" className="text-[15px] leading-6 font-semibold text-ink">
          <span className="tnum text-ink-3">4</span> Investigation
        </h2>
        {linked.length ? (
          <ul className="mt-2 grid grid-cols-[minmax(0,1fr)] gap-2">
            {linked.map((a) => (
              <li key={a.alarm_id}>
                <LinkedInvestigation id={a.investigation_id} alarm={a} />
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 max-w-[60ch] text-[14px] leading-5 text-ink-2">
            Starts when you choose Investigate on an alarm. The investigator gathers this run&apos;s
            evidence for and against each literature cause and writes a report in which every number
            is checked against the run.
          </p>
        )}
      </section>
      <section
        id="station-5"
        aria-labelledby="station-5-title"
        className={cn("panel px-4 py-4 sm:px-5", focused === 5 && "lit")}
      >
        <h2 id="station-5-title" className="text-[15px] leading-6 font-semibold text-ink">
          <span className="tnum text-ink-3">5</span> Decision
        </h2>
        <p className="mt-1 max-w-[60ch] text-[14px] leading-5 text-ink-2">
          An engineer reads the finished report and approves its actions, which opens a work order,
          or rejects it. That happens on the investigation&apos;s page; nothing here is decided by a
          model.
        </p>
      </section>
    </div>
  );
}

function LinkedInvestigation({ id, alarm }: { id: string; alarm: RunAlarm }) {
  const api = useApi();
  const query = useQuery(q.investigation(api, id));
  useInvestigationStream(query.data);
  const inv = query.data;
  // Until the investigation itself is read, the status stored with the run stands for it.
  const status = inv?.status ?? alarm.investigation_status ?? null;
  const last = inv?.steps.at(-1);
  return (
    <div className="border-t border-hairline pt-2">
      <p className="text-[14px] leading-5 text-ink">
        {alarm.title} <span className="tnum text-ink-3">{alarm.alarm_id}</span>
      </p>
      <p
        className="mt-0.5 flex flex-wrap items-center gap-x-3 text-[13px] leading-5"
        aria-live="polite"
      >
        {status ? <StatusLabel status={status} /> : <span className="text-ink-3">Starting</span>}
        {inv ? <span className="tnum text-ink-3">{plural(inv.steps.length, "step")}</span> : null}
        {last ? <span className="min-w-0 truncate text-ink-3">{last.title}</span> : null}
      </p>
      <Link
        href={investigationHref(id)}
        className="text-[13px] text-ink underline underline-offset-2 hover:text-safelight"
      >
        {status === "awaiting_decision" ? "Read the report and decide" : "Open the investigation"}
      </Link>
    </div>
  );
}
