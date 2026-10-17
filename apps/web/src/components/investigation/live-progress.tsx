"use client";

import type { InvestigationStep } from "@yield-guardian/contracts";

import { formatDuration } from "@/lib/format";
import { STEP_NODE, TOOL_NAME } from "@/lib/labels";

import { Elapsed } from "./elapsed";

/**
 * What the investigator is doing right now, shown in place of the report while it runs: the
 * current step with a live mark, the steps just finished and the time so far.
 */
export function LiveProgress({ steps, startedAt }: { steps: InvestigationStep[]; startedAt: string }) {
  const current = [...steps].reverse().find((s) => s.status === "running");
  const done = steps.filter((s) => s.status !== "running").slice(-3);

  return (
    <div className="py-6" role="status" aria-live="polite">
      <div className="flex items-center gap-3">
        <span aria-hidden="true" className="relative flex size-3">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-[var(--signal)] opacity-60 motion-reduce:animate-none" />
          <span className="relative inline-flex size-3 rounded-full bg-[var(--signal)]" />
        </span>
        <p className="text-[16px] leading-6 font-[600] text-ink">
          {current ? current.title : steps.length ? "Moving to the next step" : "Starting the investigation"}
          <span className="inline-block w-6 animate-pulse">…</span>
        </p>
      </div>
      <p className="tnum mt-1 ms-6 text-[13px] leading-5 text-ink-3">
        {current
          ? `${STEP_NODE[current.node] ?? current.node}${current.tool ? `, ${TOOL_NAME[current.tool] ?? current.tool}` : ""}, `
          : ""}
        running for <Elapsed from={startedAt} running />
        {steps.length ? `, ${steps.filter((s) => s.status === "completed").length} steps done` : ""}
      </p>

      {done.length ? (
        <ol className="mt-5 ms-6 grid gap-2 border-s border-hairline ps-4">
          {done.map((s) => {
            const ms = s.finished_at ? Date.parse(s.finished_at) - Date.parse(s.started_at) : null;
            return (
              <li key={s.index} className="flex items-baseline gap-2 text-[14px] leading-5 text-ink-2">
                <span aria-hidden="true" className={s.status === "failed" ? "text-fail" : "text-pass"}>
                  {s.status === "failed" ? "✕" : s.status === "skipped" ? "–" : "✓"}
                </span>
                <span className="min-w-0 flex-1 truncate">{s.title}</span>
                {ms != null ? (
                  <span className="tnum shrink-0 text-[12px] text-ink-3">{formatDuration(ms)}</span>
                ) : null}
              </li>
            );
          })}
        </ol>
      ) : null}
    </div>
  );
}
