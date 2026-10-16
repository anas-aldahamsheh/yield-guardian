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
    <div className="mt-8 grid grid-cols-[minmax(0,1fr)] gap-1 rounded-[28px] bg-surface p-1.5 shadow-[inset_0_0_0_1px_var(--hairline),var(--highlight)] sm:p-2 md:grid-cols-2">
      <section
        id="station-4"
        aria-labelledby="station-4-title"
        className={cn(
          "glow relative min-w-0 rounded-[22px] pt-4 pr-4 pb-6 pl-14 transition-[background-color,box-shadow] duration-(--dur-4) sm:pr-6 md:pt-12 md:pl-6",
          focused === 4 && "lit",
        )}
      >
        <Spur reached={linked.length > 0} />
        <h2
          id="station-4-title"
          className="text-[16px] leading-6 font-[630] tracking-[-0.01em] text-ink"
        >
          <span className="tnum text-ink-3">4</span> Investigation
        </h2>
        {linked.length ? (
          <ul className="mt-3 grid grid-cols-[minmax(0,1fr)] gap-2">
            {linked.map((a) => (
              <li key={a.alarm_id}>
                <LinkedInvestigation id={a.investigation_id} alarm={a} />
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1.5 max-w-[60ch] text-[14px] leading-[22px] text-ink-2">
            Starts when you choose Investigate on an alarm. The investigator gathers this run&apos;s
            evidence for and against each literature cause and writes a report in which every number
            is checked against the run.
          </p>
        )}
      </section>
      <section
        id="station-5"
        aria-labelledby="station-5-title"
        className={cn(
          "glow relative min-w-0 rounded-[22px] pt-4 pr-4 pb-6 pl-14 transition-[background-color,box-shadow] duration-(--dur-4) sm:pr-6 md:pt-12 md:pl-6",
          "md:before:pointer-events-none md:before:absolute md:before:top-12 md:before:bottom-6 md:before:left-0 md:before:w-px md:before:bg-hairline",
          focused === 5 && "lit before:opacity-0",
        )}
      >
        <Spur reached={false} />
        <h2
          id="station-5-title"
          className="text-[16px] leading-6 font-[630] tracking-[-0.01em] text-ink"
        >
          <span className="tnum text-ink-3">5</span> Decision
        </h2>
        <p className="mt-1.5 max-w-[60ch] text-[14px] leading-[22px] text-ink-2">
          An engineer reads the finished report and approves its actions, which opens a work order,
          or rejects it. That happens on the investigation&apos;s page; nothing here is decided by a
          model.
        </p>
      </section>
    </div>
  );
}

/**
 * The on-demand end of the line: a dashed track (nothing flows here until someone asks), lit with
 * the film once this run has started an investigation.
 */
function Spur({ reached }: { reached: boolean }) {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0">
      <span className="absolute top-0 bottom-0 left-[27px] w-0 border-l-2 border-dashed border-hairline-strong md:hidden" />
      <span className="absolute inset-x-0 top-[25px] hidden h-0 border-t-2 border-dashed border-hairline-strong md:block" />
      {reached ? (
        <>
          <span className="swap-in absolute top-0 bottom-0 left-[27px] w-[2px] bg-[linear-gradient(180deg,var(--film-6),var(--film-5))] md:hidden" />
          <span className="swap-in absolute inset-x-0 top-[25px] hidden h-[2px] bg-[linear-gradient(90deg,var(--film-6),var(--film-5))] md:block" />
        </>
      ) : null}
      <span
        className={cn(
          "absolute top-[23px] left-[21px] size-[14px] rounded-full md:top-[19px]",
          reached
            ? "bg-film-6 shadow-[0_0_0_4px_color-mix(in_oklab,var(--film-6)_22%,transparent)]"
            : "bg-surface shadow-[inset_0_0_0_2px_var(--hairline-strong)]",
        )}
      />
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
    <div className="grow-in rounded-[16px] bg-surface-2 px-4 py-3.5">
      <p className="text-[14.5px] leading-5 font-[600] text-ink">
        {alarm.title} <span className="tnum font-[440] text-ink-3">{alarm.alarm_id}</span>
      </p>
      <p
        className="mt-1 flex flex-wrap items-center gap-x-3 text-[13px] leading-5"
        aria-live="polite"
      >
        {status ? <StatusLabel status={status} /> : <span className="text-ink-3">Starting</span>}
        {inv ? <span className="tnum text-ink-3">{plural(inv.steps.length, "step")}</span> : null}
        {last ? <span className="min-w-0 truncate text-ink-3">{last.title}</span> : null}
      </p>
      <Link
        href={investigationHref(id)}
        className="press mt-2.5 inline-flex h-8 items-center rounded-full bg-ink px-3.5 text-[13px] font-[600] text-canvas no-underline hover:bg-ink/90"
      >
        {status === "awaiting_decision" ? "Read the report and decide" : "Open the investigation"}
      </Link>
    </div>
  );
}
