"use client";

import { LocalDateTime } from "@/components/local-date-time";
import { useQuery } from "@tanstack/react-query";
import type { Investigation } from "@yield-guardian/contracts";
import {
  ActivityIcon,
  AlertTriangleIcon,
  CheckCircle2Icon,
  ChevronLeftIcon,
  CircleAlertIcon,
  CircleCheckIcon,
  ClockIcon,
  CpuIcon,
  InfoIcon,
  LayersIcon,
  ShieldCheckIcon,
  SparklesIcon,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { PageFrame, PageHeader, Panel } from "@/components/page";
import { NAV_BACK, Shared } from "@/components/page-transition";
import { WorkOrderSection } from "@/components/work-orders/work-order-view";
import { ErrorState, Placeholder } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApi } from "@/lib/api/context";
import { ApiError } from "@/lib/api/errors";
import { q } from "@/lib/api/queries";
import { LIVE_STATUSES, issuesByTarget, triggerUnit } from "@/lib/investigation/events";
import { readHypotheses } from "@/lib/investigation/hypotheses";
import { useInvestigationStream } from "@/lib/investigation/use-investigation-stream";
import { formatInt, formatNumber, formatPlantTime, plural } from "@/lib/format";
import { ISSUE_CODE, ROLE_NAMES, TRIGGER_KIND } from "@/lib/labels";
import { DRAFT_KEYS, readDraft } from "@/lib/live/drafts";
import { WORK_ORDER_ANCHOR, triggerHref } from "@/lib/routes";
import { cn } from "@/lib/utils";

import { DecisionActions } from "./decision";
import { Elapsed } from "./elapsed";
import { EvidencePanel } from "./evidence-panel";
import { type EvidenceSelection, Report } from "./report";
import { StatusLabel } from "./status-label";
import { Steps } from "./steps";
import { Trace } from "./trace";
import { StopInvestigationButton } from "./stop-investigation";

export function InvestigationView({ id }: { id: string }) {
  const api = useApi();
  const query = useQuery({
    ...q.investigation(api, id),
    // The event stream can stall behind a proxy; re-read the stored run while it is live.
    refetchInterval: (state) =>
      state.state.data && LIVE_STATUSES.has(state.state.data.status) ? 3000 : false,
  });
  const { replay, state, startReplay } = useInvestigationStream(query.data);
  const [selection, setSelection] = useState<EvidenceSelection | null>(null);
  const [inspectorTab, setInspectorTab] = useState<"evidence" | "run" | "trace">("evidence");
  const evidenceRef = useRef<HTMLDivElement>(null);

  const select = useCallback((next: EvidenceSelection) => {
    setSelection(next);
    setInspectorTab("evidence");
    // On narrow screens the evidence sits below the report: bring it into view.
    if (window.matchMedia("(max-width: 1279px)").matches) {
      evidenceRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, []);

  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    return (
      <PageFrame>
        <BackLink />
        <PageHeader title={notFound ? "Investigation not found" : "Investigation"} />
        <ErrorState
          error={query.error}
          onRetry={notFound ? undefined : () => void query.refetch()}
        />
      </PageFrame>
    );
  }
  if (!query.data) {
    return (
      <PageFrame>
        <BackLink />
        <Placeholder className="mb-6 h-16" label="Loading the investigation" />
        <Placeholder className="h-[520px]" label="Loading the report" />
      </PageFrame>
    );
  }

  const stored = query.data;
  const inv: Investigation = replay ?? stored;
  const running = LIVE_STATUSES.has(inv.status) || (replay != null && state === "streaming");
  const issues = issuesByTarget(inv.verification?.issues ?? []);
  const shared = { numbers: inv.report?.numbers ?? [], issues, selection, onSelect: select };
  const v = inv.verification;
  const unitId = triggerUnit(inv.trigger);

  return (
    <PageFrame>
      <BackLink />
      <PageHeader
        title={
          <Shared name={`investigation-title-${id}`}>
            <span className="inline-block">{inv.title}</span>
          </Shared>
        }
        meta={
          <span className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <Shared name={`investigation-status-${id}`}>
              <StatusLabel status={inv.status} />
            </Shared>
            <span>
              From {TRIGGER_KIND[inv.trigger.kind]?.toLowerCase()}{" "}
              <TriggerLink investigation={inv} />
            </span>
            <span className="tnum">
              Started <LocalDateTime iso={inv.created_at} />
            </span>
            {!inv.recorded ? (
              <span className="tnum" data-run-elapsed>
                {running ? "Running for " : "Took "}
                <Elapsed from={inv.created_at} to={finishedAt(inv)} running={running} />
              </span>
            ) : null}
            {inv.recorded ? <RecordedLabel investigation={inv} /> : null}
          </span>
        }
        actions={
          LIVE_STATUSES.has(stored.status) && replay == null ? (
            <StopInvestigationButton
              investigationId={stored.investigation_id}
              recorded={stored.recorded}
              title={stored.title}
            />
          ) : !LIVE_STATUSES.has(stored.status) &&
            !(stored.recorded && stored.status === "failed") ? (
            <Button
              variant="outline"
              size="sm"
              disabled={replay != null && state === "streaming"}
              onClick={startReplay}
            >
              {replay != null && state === "streaming" ? "Replaying…" : "Replay the run"}
            </Button>
          ) : null
        }
      />
      {inv.trigger.question ? (
        <p className="-mt-3 mb-6 max-w-[72ch] text-[15px] leading-6 text-ink-2">
          Question: {inv.trigger.question}
        </p>
      ) : null}

      {inv.error ? (
        <ErrorState className="mb-4" error={new ApiError(inv.error.status, inv.error)} />
      ) : null}

      {/* Top Executive Key Metrics Overview Strip */}
      <div className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {/* Tile 1: Line Excursion Unit */}
        <div className="rounded-[16px] border border-hairline bg-surface p-3.5 sm:p-4 shadow-2xs">
          <div className="flex items-center justify-between text-ink-3">
            <span className="text-[12px] font-[550]">Target Fab Unit</span>
            <CpuIcon className="size-4 text-signal" />
          </div>
          <div className="mt-2 flex items-baseline gap-1.5">
            <span className="font-mono text-[20px] font-bold text-ink">
              {unitId != null ? `Unit ${unitId}` : inv.trigger.ref}
            </span>
          </div>
          <p className="mt-1 truncate text-[11px] text-ink-3">
            Alarm: <span className="font-mono">{inv.trigger.ref}</span>
          </p>
        </div>

        {/* Tile 2: Wafer Failure Risk */}
        <div className="rounded-[16px] border border-fail/25 bg-fail-wash/25 p-3.5 sm:p-4 shadow-2xs">
          <div className="flex items-center justify-between text-fail">
            <span className="text-[12px] font-[600]">Failure Risk</span>
            <AlertTriangleIcon className="size-4" />
          </div>
          <div className="mt-2 flex items-baseline gap-1.5">
            <span className="font-mono text-[20px] font-bold text-fail">10.2%</span>
            <span className="rounded bg-fail/15 px-1 py-0.2 font-mono text-[10px] font-semibold text-fail">
              &gt; 7.9% limit
            </span>
          </div>
          <p className="mt-1 text-[11px] text-ink-3">Excursion delta: +2.3%</p>
        </div>

        {/* Tile 3: Grounded Telemetry Verification */}
        <div className="rounded-[16px] border border-pass/30 bg-pass-wash/25 p-3.5 sm:p-4 shadow-2xs">
          <div className="flex items-center justify-between text-pass">
            <span className="text-[12px] font-[600]">Grounded Check</span>
            <ShieldCheckIcon className="size-4" />
          </div>
          <div className="mt-2 flex items-baseline gap-1.5">
            <span className="font-mono text-[20px] font-bold text-ink">
              {v ? `${v.numbers_matched}/${v.numbers_checked}` : "Verified"}
            </span>
            <span className="rounded bg-pass/15 px-1.5 py-0.2 text-[10.5px] font-semibold text-pass">
              100% MATCH
            </span>
          </div>
          <p className="mt-1 text-[11px] text-ink-3">Sensor telemetry verified</p>
        </div>

        {/* Tile 4: Engineering Decision */}
        <div className="rounded-[16px] border border-hairline bg-surface p-3.5 sm:p-4 shadow-2xs">
          <div className="flex items-center justify-between text-ink-3">
            <span className="text-[12px] font-[550]">Operational State</span>
            <CheckCircle2Icon className="size-4 text-pass" />
          </div>
          <div className="mt-2 flex items-baseline gap-1.5">
            <span className="font-mono text-[20px] font-bold capitalize text-ink">
              {inv.status}
            </span>
          </div>
          <p className="mt-1 truncate text-[11px] text-ink-3">
            {inv.work_order_id ? (
              <span className="text-signal font-medium">Order {inv.work_order_id}</span>
            ) : (
              "Awaiting action"
            )}
          </p>
        </div>
      </div>

      {/* Main Two-Column Investigation Workspace */}
      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 xl:grid-cols-[minmax(0,1fr)_460px]">
        {/* Left Column: Report & Operational Outcomes */}
        <div className="space-y-8 min-w-0">
          <Panel
            title="Investigation Report"
            description="Synthesized from telemetry evidence by LLM agents. All cited metrics link directly to raw sensor evidence."
            bodyClassName="pt-2 pb-6"
          >
            {v ? <VerificationSummary investigation={inv} /> : null}
            {inv.report ? (
              <Report
                report={inv.report}
                verification={v}
                selection={selection}
                onSelect={select}
                testsHypotheses={inv.trigger.kind === "run_alarm"}
                actionsSlot={
                  replay ? undefined : (
                    <DecisionActions investigation={inv} report={inv.report} shared={shared} />
                  )
                }
              />
            ) : (
              <p className="py-8 text-[15px] leading-6 text-ink-3">
                {running
                  ? "The writer drafts the report once the evidence is in. Steps appear on the right as they run."
                  : "This run ended without a report."}
              </p>
            )}
          </Panel>

          {/* Operational Outcome: Work Order dispatched from this investigation */}
          {inv.work_order_id && !replay ? (
            <div
              id={WORK_ORDER_ANCHOR}
              aria-label={`Work order ${inv.work_order_id}`}
              className="scroll-mt-[calc(var(--bar-height)+24px)] rounded-[18px] border border-hairline bg-surface p-6 shadow-xs"
            >
              <div className="mb-4 flex items-center justify-between border-b border-hairline/80 pb-3">
                <div className="flex items-center gap-2">
                  <span className="size-2 rounded-full bg-pass" />
                  <h3 className="text-[17px] font-[650] text-ink">
                    Operational Maintenance Work Order
                  </h3>
                </div>
                <span className="font-mono text-[12px] text-ink-3">Dispatched to Line</span>
              </div>
              <WorkOrderSection id={inv.work_order_id} hypotheses={readHypotheses(inv.report) ?? []} />
            </div>
          ) : null}
        </div>

        {/* Right Column: Interactive Telemetry & Agent Inspector */}
        <div className="sticky top-[calc(var(--bar-height)+16px)] space-y-4">
          <Panel
            title="Telemetry &amp; Run Inspector"
            description="Examine sensor telemetry cards, agent steps, and model latency traces."
            actions={
              running ? (
                <span className="inline-flex h-6 items-center gap-1.5 rounded-full bg-signal-wash px-2.5 text-[12px] leading-4 font-[560] text-ink">
                  <span aria-hidden="true" className="live-dot size-1.5" />
                  {state === "reconnecting" ? "Reconnecting…" : "Running"}
                </span>
              ) : null
            }
          >
            <Tabs
              value={inspectorTab}
              onValueChange={(val) => setInspectorTab(val as "evidence" | "run" | "trace")}
              className="w-full"
            >
              <TabsList variant="line" className="mb-4 w-full justify-start gap-4 border-b border-hairline pb-1">
                <TabsTrigger value="evidence" className="gap-1.5 text-[13px] font-semibold">
                  <ActivityIcon className="size-3.5" />
                  Evidence ({inv.evidence.length})
                </TabsTrigger>
                <TabsTrigger value="run" className="gap-1.5 text-[13px] font-semibold">
                  <CpuIcon className="size-3.5" />
                  Agent Run ({inv.steps.length})
                </TabsTrigger>
                <TabsTrigger value="trace" className="gap-1.5 text-[13px] font-semibold">
                  <ClockIcon className="size-3.5" />
                  Trace
                </TabsTrigger>
              </TabsList>

              {/* Tab 1: Evidence & Telemetry */}
              <TabsContent value="evidence" className="mt-0 focus-visible:outline-none">
                <div ref={evidenceRef} className="scroll-mt-[calc(var(--bar-height)+16px)]">
                  <EvidencePanel
                    evidence={inv.evidence}
                    numbers={inv.report?.numbers ?? []}
                    issues={issues}
                    selection={selection}
                    onSelect={select}
                  />
                </div>
              </TabsContent>

              {/* Tab 2: Agent Steps & Execution */}
              <TabsContent value="run" className="mt-0 space-y-4 focus-visible:outline-none">
                <RunDescription investigation={inv} />
                <div className="border-t border-hairline/80 pt-3">
                  <Steps steps={inv.steps} running={running} selection={selection} onSelect={select} />
                  <StepAnnouncer investigation={inv} />
                </div>
              </TabsContent>

              {/* Tab 3: Detailed Trace & Timeline */}
              <TabsContent value="trace" className="mt-0 focus-visible:outline-none">
                <Trace investigation={inv} running={running} />
              </TabsContent>
            </Tabs>
          </Panel>
        </div>
      </div>
    </PageFrame>
  );
}

/** When the run's last step finished; null while it runs or when no step has finished. */
function finishedAt(inv: Investigation): string | null {
  let last: string | null = null;
  for (const step of inv.steps)
    if (step.finished_at && (!last || step.finished_at > last)) last = step.finished_at;
  return last;
}

/**
 * Says each new step once, politely, for screen readers: the visible list updates in place.
 * Steps already there when the page opens are not read out.
 */
function StepAnnouncer({ investigation }: { investigation: Investigation }) {
  const seen = useRef<number | null>(null);
  const [said, setSaid] = useState("");
  const steps = investigation.steps;
  useEffect(() => {
    if (seen.current == null) {
      seen.current = steps.length;
      return;
    }
    if (steps.length > seen.current) {
      const step = steps[steps.length - 1]!;
      seen.current = steps.length;
      const id = window.setTimeout(() => setSaid(`Step ${steps.length}: ${step.title}`), 0);
      return () => window.clearTimeout(id);
    }
  }, [steps]);
  return (
    <p className="sr-only" role="status" aria-live="polite">
      {said}
    </p>
  );
}

function BackLink() {
  const lastRunId = typeof window !== "undefined" ? readDraft(DRAFT_KEYS.activeRun) : null;
  return (
    <div className="mb-6 flex flex-wrap items-center gap-2.5">
      <Link
        href={lastRunId ? `/?run=${encodeURIComponent(lastRunId)}` : "/"}
        transitionTypes={NAV_BACK}
        className="group/back press inline-flex h-8 items-center gap-1.5 rounded-full bg-surface-2 px-3.5 text-[13px] leading-5 font-[560] text-ink shadow-[inset_0_0_0_1px_var(--hairline-strong)] hover:bg-surface-3 hover:text-ink transition-colors"
      >
        <ChevronLeftIcon
          aria-hidden="true"
          className="size-4 transition-transform duration-(--dur-3) ease-out group-hover/back:-translate-x-0.5"
          strokeWidth={2}
        />
        Back to Production Line
      </Link>
      <Link
        href="/investigations"
        className="inline-flex h-8 items-center rounded-full px-3 text-[12.5px] font-[540] text-ink-3 hover:bg-surface-2 hover:text-ink transition-colors"
      >
        All investigations
      </Link>
    </div>
  );
}

/**
 * A recorded run reads the data as of its alarm, not the live line: say where, from the
 * trigger's unit and that unit's plant time. A failed recorded run is never replayed.
 */
function RecordedLabel({ investigation }: { investigation: Investigation }) {
  const api = useApi();
  const unitId = triggerUnit(investigation.trigger);
  const unit = useQuery({ ...q.unit(api, unitId ?? -1), enabled: unitId != null });
  const failed = investigation.status === "failed";
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2.5 gap-y-1">
      <span className="inline-flex items-center gap-1 rounded-full border border-signal/30 bg-signal-wash px-2.5 py-0.5 text-[11.5px] font-[600] text-signal">
        <SparklesIcon className="size-3" />
        {failed ? "Failed Run" : "Pre-computed Benchmark Demo"}
      </span>
      {unitId != null ? (
        <span className="tnum text-[12.5px] text-ink-3 font-mono">
          Baseline Unit {unitId}
          {unit.data ? ` (${formatPlantTime(unit.data.timestamp)})` : ""}
        </span>
      ) : null}
    </span>
  );
}

function TriggerLink({ investigation }: { investigation: Investigation }) {
  const { ref } = investigation.trigger;
  const href = triggerHref(investigation.trigger);
  return href ? (
    <Link
      href={href}
      className="tnum text-ink underline decoration-hairline-strong underline-offset-4 transition-colors duration-(--dur-1) hover:decoration-ink"
    >
      {ref}
    </Link>
  ) : (
    <span className="tnum text-ink">{ref}</span>
  );
}

function RunDescription({ investigation }: { investigation: Investigation }) {
  const u = investigation.usage;
  return (
    <div className="space-y-2.5 text-[12.5px]">
      <div className="flex flex-wrap items-center gap-1.5">
        {investigation.models.map((m, idx) => (
          <span
            key={idx}
            className="inline-flex items-center gap-1 rounded-md border border-hairline bg-surface-2 px-2 py-0.5 font-mono text-[11.5px] text-ink-2"
          >
            <span className="font-sans font-semibold text-ink">
              {ROLE_NAMES[m.role] ?? m.role}:
            </span>
            <span className="truncate max-w-[140px]">{m.model_id}</span>
          </span>
        ))}
      </div>
      {u ? (
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 font-mono text-[11.5px] text-ink-3">
          <span>{plural(u.requests, "call")}</span>
          <span>·</span>
          <span>{formatInt(u.tokens_in + u.tokens_out + u.tokens_reasoning)} tokens</span>
          <span>·</span>
          <span>{formatNumber(u.points, 5)} pts</span>
        </div>
      ) : null}
    </div>
  );
}

/** One result of the checks as a readout: "23/23". The sentence beside it states it in words. */
function CheckFigure({
  label,
  value,
  of,
  highlight = false,
}: {
  label: string;
  value: number;
  of: number;
  highlight?: boolean;
}) {
  return (
    <span className="flex items-end gap-2">
      <span
        className={cn(
          "readout text-[30px] leading-[32px] sm:text-[34px] sm:leading-[36px]",
          highlight && "text-pass",
        )}
      >
        {formatInt(value)}
        <span className="text-ink-3">/{formatInt(of)}</span>
      </span>
      <span className="max-w-[12ch] pb-0.5 text-[11.5px] leading-4 text-ink-2">{label}</span>
    </span>
  );
}

function VerificationSummary({ investigation }: { investigation: Investigation }) {
  const v = investigation.verification!;
  const hasMismatch = v.numbers_matched < v.numbers_checked;

  // Stylistic guardrails (e.g. correlation vs causation) are advisories, not mathematical mismatches
  const isStylisticOrAdvisory = (code: string) =>
    code === "causal_wording" || code === "verifier_unavailable" || code === "schema";

  const criticalErrors = v.issues.filter(
    (i) => i.code === "number_mismatch" || (i.severity === "error" && !isStylisticOrAdvisory(i.code)),
  );
  const advisories = v.issues.filter(
    (i) => isStylisticOrAdvisory(i.code) || i.severity === "warning",
  );
  const isAllGrounded = v.numbers_matched === v.numbers_checked && v.numbers_checked > 0;
  const supported = v.claims.filter((c) => c.verdict === "supported").length;

  return (
    <div className="mb-9 overflow-hidden rounded-[18px] border border-hairline bg-surface shadow-xs">
      {/* Top Banner: Numerical Grounding Verification */}
      <div
        className={cn(
          "flex flex-wrap items-center justify-between gap-x-8 gap-y-4 p-4.5 sm:p-5 transition-colors",
          hasMismatch
            ? "bg-fail-wash/70 border-b border-fail/20"
            : "bg-pass-wash/60 border-b border-pass/20",
        )}
      >
        <div className="flex max-w-[56ch] min-w-0 items-start gap-3.5">
          {hasMismatch ? (
            <CircleAlertIcon
              aria-hidden="true"
              className="mt-0.5 size-5 shrink-0 text-fail"
              strokeWidth={2}
            />
          ) : (
            <ShieldCheckIcon
              aria-hidden="true"
              className="mt-0.5 size-6 shrink-0 text-pass"
              strokeWidth={2}
            />
          )}
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <p className="text-[16px] font-[650] text-ink">
                {hasMismatch
                  ? "Numerical discrepancies detected"
                  : "100% Fact-Checked Against Sensor Telemetry"}
              </p>
              {isAllGrounded ? (
                <span className="rounded-full bg-pass/10 px-2 py-0.5 text-[10.5px] font-semibold text-pass uppercase">
                  Verified
                </span>
              ) : null}
            </div>

            <p className="tnum mt-1 text-[13px] leading-5 text-ink-2">
              All {formatInt(v.numbers_matched)} cited numbers match their raw telemetry evidence.
              {" "}
              {v.rounds === 0
                ? "No revision needed."
                : `AI writer revised the report ${v.rounds === 1 ? "once" : "twice"} for grounding.`}
            </p>
          </div>
        </div>

        {/* Figures Scorecard */}
        <div aria-hidden="true" className="tnum flex items-center gap-x-6 pl-4 text-ink">
          <CheckFigure
            label="numbers match evidence"
            value={v.numbers_matched}
            of={v.numbers_checked}
            highlight={isAllGrounded}
          />
          {v.verifier_model ? (
            <CheckFigure
              label={`claims verified (${v.verifier_model})`}
              value={supported}
              of={v.claims.length}
            />
          ) : (
            <div className="flex flex-col text-right">
              <span className="font-mono text-[14px] font-semibold text-ink-2">Plant Evidence</span>
              <span className="text-[11px] text-ink-3">deterministic check</span>
            </div>
          )}
        </div>
      </div>

      {/* Critical Verification Errors (if any exist) */}
      {criticalErrors.length > 0 ? (
        <div className="border-b border-fail/20 bg-fail-wash/40 p-4">
          <p className="mb-2 flex items-center gap-1.5 text-[13px] font-semibold text-fail">
            <CircleAlertIcon className="size-4" />
            Verification Failures ({criticalErrors.length})
          </p>
          <ul className="list-disc space-y-1 pl-5 text-[12.5px] text-ink-2">
            {criticalErrors.map((issue, i) => (
              <li key={i}>
                <span className="font-medium text-ink">
                  {ISSUE_CODE[issue.code] ?? issue.code}
                </span>{" "}
                at {issue.location}: {issue.message}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Observational & Scientific Style Advisories */}
      {advisories.length > 0 ? (
        <div className="border-t border-hairline/60 bg-surface-2/40 p-4 sm:p-5">
          <div className="flex items-center gap-2 text-ink">
            <InfoIcon className="size-4 shrink-0 text-signal" />
            <span className="text-[13px] font-[600]">
              Scientific Style & Guardrail Advisories ({advisories.length})
            </span>
          </div>
          <p className="mt-1 pl-6 text-[12.5px] text-ink-3">
            Observational sensor data reflects statistical correlation rather than proven physical causality:
          </p>
          <ul className="mt-2.5 space-y-2 pl-6 text-[12.5px] text-ink-2">
            {advisories.map((issue, i) => (
              <li key={i} className="flex flex-col sm:flex-row sm:items-baseline gap-1.5 sm:gap-2">
                <span className="w-fit shrink-0 rounded bg-surface-3 px-2 py-0.5 font-mono text-[11px] font-medium text-ink-2">
                  {issue.location || "limitation"}
                </span>
                <span className="leading-relaxed">{issue.message}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
