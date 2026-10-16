"use client";

import { useQuery } from "@tanstack/react-query";
import type { Investigation, InvestigationStep, ModelCallTrace } from "@yield-guardian/contracts";

import { LocalDateTime } from "@/components/local-date-time";
import { Panel } from "@/components/page";
import { useApi } from "@/lib/api/context";
import { q } from "@/lib/api/queries";
import { formatDuration, formatInt } from "@/lib/format";
import { ROLE_NAMES, STEP_NODE, TOOL_NAME } from "@/lib/labels";
import { cn } from "@/lib/utils";

import { Elapsed } from "./elapsed";

const PROVIDER: Record<string, string> = {
  token_factory: "Token Factory",
  tokenharbor: "TokenHarbor",
  openrouter: "OpenRouter",
  anthropic: "Anthropic",
};

type Row =
  | { kind: "call"; at: number; end: number; call: ModelCallTrace; fallback: boolean }
  | { kind: "step"; at: number; end: number | null; step: InvestigationStep };

/** What went wrong with a call, in plain words (null when it worked). */
export function callProblem(call: ModelCallTrace): string | null {
  if (call.status === "ok") return null;
  const detail = call.error ? `: ${call.error}` : "";
  switch (call.status) {
    case "empty":
      return (call.tokens_out ?? 0) > 0 || (call.tokens_reasoning ?? 0) > 0
        ? "Empty answer: the model used its whole output budget thinking"
        : "Empty answer: the model returned no text";
    case "invalid_output":
      return `The answer did not match the expected format${detail}`;
    case "refused_profile":
      return `Not sent: the request breaks a rule of this model's profile${detail}`;
    default:
      return `Failed${call.http_status ? ` (HTTP ${call.http_status})` : ""}${detail}`;
  }
}

function buildRows(steps: InvestigationStep[], calls: ModelCallTrace[]): Row[] {
  const rows: Row[] = calls.map((call, i) => {
    const at = Date.parse(call.at);
    const prev = calls[i - 1];
    const fallback =
      prev != null &&
      prev.status !== "ok" &&
      prev.role === call.role &&
      prev.model_id !== call.model_id;
    return { kind: "call", at, end: at + call.latency_ms, call, fallback };
  });
  for (const step of steps) {
    if (step.tool == null && step.status !== "running") continue;
    rows.push({
      kind: "step",
      at: Date.parse(step.started_at),
      end: step.finished_at ? Date.parse(step.finished_at) : null,
      step,
    });
  }
  return rows.sort((a, b) => a.at - b.at);
}

/**
 * The run traced call by call: every model call (what was sent, what came back, whether it
 * worked) interleaved with the tool steps, in time order.
 */
export function Trace({
  investigation,
  running,
}: {
  investigation: Investigation;
  running: boolean;
}) {
  const api = useApi();
  const calls = useQuery({
    ...q.investigationCalls(api, investigation.investigation_id),
    refetchInterval: running ? 3000 : false,
  });
  const rows = buildRows(investigation.steps, calls.data ?? []);
  const failures = rows.filter((r) =>
    r.kind === "call" ? r.call.status !== "ok" : r.step.status === "failed",
  ).length;
  const fallbacks = rows.filter((r) => r.kind === "call" && r.fallback).length;
  const ends = rows.map((r) => r.end).filter((e): e is number => e != null);
  const total = rows.length && ends.length ? Math.max(...ends) - rows[0]!.at : null;

  return (
    <Panel
      className="mt-5"
      title="Trace"
      live={running}
      description={
        <span className="tnum">
          {formatInt(rows.length)} steps · {formatInt(failures)} failed · {formatInt(fallbacks)}{" "}
          {fallbacks === 1 ? "fallback" : "fallbacks"} · {formatDuration(total)} in all
        </span>
      }
    >
      {calls.isError ? (
        <p className="text-[14px] leading-5 text-fail">The model calls could not be loaded.</p>
      ) : !rows.length ? (
        <p className="text-[14px] leading-5 text-ink-3">
          {calls.isPending ? "Loading the trace." : "No model or tool calls were recorded."}
        </p>
      ) : (
        <ol className="grid grid-cols-[minmax(0,1fr)] divide-y divide-hairline text-[13.5px] leading-5">
          {rows.map((row, i) =>
            row.kind === "call" ? (
              <CallRow key={`c${i}`} call={row.call} fallback={row.fallback} />
            ) : (
              <StepRow key={`s${row.step.index}`} step={row.step} />
            ),
          )}
        </ol>
      )}
    </Panel>
  );
}

function Mark({ ok, label }: { ok: boolean | null; label: string }) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 font-[560]",
        ok === true ? "text-pass" : ok === false ? "text-fail" : "text-ink-2",
      )}
    >
      <span aria-hidden="true">{ok === true ? "✓" : ok === false ? "✗" : "…"}</span>
      {label}
    </span>
  );
}

function Line({ children }: { children: React.ReactNode }) {
  return (
    <span className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-0.5">{children}</span>
  );
}

function CallRow({ call, fallback }: { call: ModelCallTrace; fallback: boolean }) {
  const problem = callProblem(call);
  return (
    <li className="py-2">
      <details>
        <summary className="cursor-pointer list-none [&::-webkit-details-marker]:hidden">
          <Line>
            <span className="tnum text-ink-3">
              <LocalDateTime iso={call.at} timeOnly />
            </span>
            <span className="font-[560] text-ink">{ROLE_NAMES[call.role] ?? call.role}</span>
            <span className="min-w-0 break-all text-ink-2">
              {call.model_id} · {PROVIDER[call.provider] ?? call.provider}
              {call.cache_hit ? " · cached" : ""}
              {fallback ? " · fallback" : ""}
            </span>
            <Mark ok={problem == null} label={problem == null ? "Worked" : "Failed"} />
            <span className="tnum text-ink-3">
              {formatDuration(call.latency_ms)}
              {call.tokens_in != null ? ` · ${formatInt(call.tokens_in)} tokens in` : ""}
              {call.tokens_out != null ? ` · ${formatInt(call.tokens_out)} tokens out` : ""}
            </span>
          </Line>
          {problem ? <p className="mt-0.5 text-fail">{problem}</p> : null}
        </summary>
        <div className="mt-2 grid gap-2">
          <TextBlock label="Sent" text={call.sent} />
          <TextBlock label="Returned" text={call.returned} />
        </div>
      </details>
    </li>
  );
}

function TextBlock({ label, text }: { label: string; text: string | null }) {
  return (
    <div className="min-w-0">
      <p className="text-[12.5px] font-[560] text-ink-2">{label}</p>
      <pre className="mt-1 max-h-64 overflow-auto rounded-[8px] bg-surface-2 p-2 font-mono text-[12px] leading-[18px] break-words whitespace-pre-wrap text-ink">
        {text ?? "Nothing recorded."}
      </pre>
    </div>
  );
}

function StepRow({ step }: { step: InvestigationStep }) {
  const tool = step.tool ? (TOOL_NAME[step.tool] ?? step.tool) : null;
  const status =
    step.status === "running" ? (
      <Mark ok={null} label="In progress" />
    ) : step.status === "completed" ? (
      <Mark ok label={`${formatInt(step.evidence_ids.length)} returned`} />
    ) : step.status === "skipped" ? (
      <Mark ok={false} label="Refused" />
    ) : (
      <Mark ok={false} label="Failed" />
    );
  return (
    <li className="py-2">
      <Line>
        <span className="tnum text-ink-3">
          <LocalDateTime iso={step.started_at} timeOnly />
        </span>
        <span className="font-[560] text-ink">{tool ? `Tool: ${tool}` : STEP_NODE[step.node]}</span>
        <span className="min-w-0 text-ink-2">{step.title}</span>
        {status}
        <span className="tnum text-ink-3">
          <Elapsed
            from={step.started_at}
            to={step.finished_at}
            running={step.status === "running"}
          />
        </span>
      </Line>
    </li>
  );
}
