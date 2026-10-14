"use client";

import type { InvestigationStep } from "@yield-guardian/contracts";

import { formatDuration, formatInt, formatNumber, formatReported } from "@/lib/format";
import { ROLE_NAMES, STEP_NODE, TOOL_NAME } from "@/lib/labels";
import { cn } from "@/lib/utils";

import { type EvidenceSelection, EvidenceChips } from "./report";

const duration = (step: InvestigationStep) =>
  step.finished_at ? Date.parse(step.finished_at) - Date.parse(step.started_at) : null;

/**
 * The run as a sequence: each step written by code, the tool it called, the evidence it stored
 * and every model call with its tokens, cost and time.
 */
export function Steps({
  steps,
  running,
  selection,
  onSelect,
}: {
  steps: InvestigationStep[];
  running: boolean;
  selection: EvidenceSelection | null;
  onSelect: (selection: EvidenceSelection) => void;
}) {
  if (!steps.length) {
    return <p className="text-[14px] leading-5 text-ink-3">{running ? "Waiting for the first step." : "No steps were recorded."}</p>;
  }
  return (
    <ol className="relative grid">
      {steps.map((step, i) => {
        const last = i === steps.length - 1;
        const ms = duration(step);
        return (
          <li key={step.index} className="relative grid grid-cols-[20px_minmax(0,1fr)] gap-x-3 pb-4">
            {!last ? <span aria-hidden="true" className="absolute top-5 bottom-0 left-[9.5px] w-px bg-hairline-strong" /> : null}
            <StepMark status={step.status} />
            <div className="min-w-0">
              <p className="text-[14px] leading-5 text-ink">
                <span className="sr-only">{statusWord(step.status)}: </span>
                {step.title}
              </p>
              <p className="tnum mt-0.5 text-[12px] leading-4 text-ink-3">
                {STEP_NODE[step.node] ?? step.node}
                {step.tool ? `, ${TOOL_NAME[step.tool] ?? step.tool}` : ""}
                {ms != null ? `, ${formatDuration(ms)}` : step.status === "running" ? ", running" : ""}
              </p>
              {step.evidence_ids.length ? (
                <div className="mt-1.5 text-[12px]">
                  <EvidenceChips ids={step.evidence_ids} selection={selection} onSelect={onSelect} />
                </div>
              ) : null}
              {step.llm.map((call, k) => (
                <p key={k} className="tnum mt-1.5 text-[12px] leading-4 text-ink-3">
                  {ROLE_NAMES[call.role] ?? call.role}: <span className="text-ink-2">{call.model_id}</span>,{" "}
                  {call.tokens_in == null && call.tokens_out == null ? (
                    "tokens not reported"
                  ) : (
                    <>
                      {formatReported(call.tokens_in)} in, {formatReported(call.tokens_out)} out
                    </>
                  )}
                  {call.tokens_reasoning ? `, ${formatInt(call.tokens_reasoning)} reasoning` : ""},{" "}
                  {call.points == null ? "points not reported" : `${formatNumber(call.points, 5)} points`},{" "}
                  {formatDuration(call.latency_ms)}
                  {call.cached ? ", from cache" : ""}
                </p>
              ))}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function statusWord(status: InvestigationStep["status"]) {
  return { running: "Running", completed: "Done", failed: "Failed", skipped: "Skipped" }[status];
}

function StepMark({ status }: { status: InvestigationStep["status"] }) {
  return (
    <span aria-hidden="true" className="relative z-[1] mt-0.5 flex size-5 items-center justify-center rounded-full bg-die">
      <svg viewBox="0 0 20 20" className="size-5">
        {status === "running" ? (
          <>
            <circle cx="10" cy="10" r="8.5" fill="none" stroke="var(--safelight)" strokeWidth="1.5" />
            <circle cx="10" cy="10" r="4" fill="var(--safelight)" className={cn("origin-center animate-pulse")} />
          </>
        ) : status === "completed" ? (
          <>
            <circle cx="10" cy="10" r="8.5" fill="var(--ink)" />
            <path d="M6 10.3l2.6 2.6L14.2 7.4" fill="none" stroke="var(--die)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </>
        ) : status === "failed" ? (
          <>
            <circle cx="10" cy="10" r="8.5" fill="var(--fail)" />
            <path d="M7 7l6 6M13 7l-6 6" stroke="var(--die)" strokeWidth="1.8" strokeLinecap="round" />
          </>
        ) : (
          <>
            <circle cx="10" cy="10" r="8.5" fill="none" stroke="var(--edge)" strokeWidth="1.5" />
            <path d="M6.5 10h7" stroke="var(--ink-3)" strokeWidth="1.5" strokeLinecap="round" />
          </>
        )}
      </svg>
    </span>
  );
}
