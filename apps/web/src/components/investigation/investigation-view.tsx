"use client";

import { LocalDateTime } from "@/components/local-date-time";
import { useQuery } from "@tanstack/react-query";
import type { Investigation } from "@yield-guardian/contracts";
import { ChevronLeftIcon, CircleAlertIcon, CircleCheckIcon } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { PageFrame, PageHeader, Panel } from "@/components/page";
import { NAV_BACK, Shared } from "@/components/page-transition";
import { WorkOrderSection } from "@/components/work-orders/work-order-view";
import { ErrorState, Placeholder } from "@/components/states";
import { Button } from "@/components/ui/button";
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
  const evidenceRef = useRef<HTMLDivElement>(null);

  const select = useCallback((next: EvidenceSelection) => {
    setSelection(next);
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
            <span className="tnum" data-run-elapsed>
              {running ? "Running for " : "Took "}
              <Elapsed from={inv.created_at} to={finishedAt(inv)} running={running} />
            </span>
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

      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-5 xl:grid-cols-[minmax(0,1fr)_440px]">
        <Panel
          title="Report"
          description="Written by a language model from the evidence only. Numbers link to the value they came from."
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

        <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] content-start gap-5">
          <Panel
            live={running}
            title="Run"
            description={<RunDescription investigation={inv} />}
            actions={
              running ? (
                <span className="inline-flex h-6 items-center gap-1.5 rounded-full bg-signal-wash px-2.5 text-[12.5px] leading-4 font-[560] text-ink">
                  <span aria-hidden="true" className="live-dot size-1.5" />
                  {state === "reconnecting" ? "Reconnecting…" : "Running"}
                </span>
              ) : null
            }
          >
            <Steps steps={inv.steps} running={running} selection={selection} onSelect={select} />
            <StepAnnouncer investigation={inv} />
          </Panel>
          <div ref={evidenceRef} className="scroll-mt-[calc(var(--bar-height)+16px)]">
            <Panel
              title="Evidence"
              description="Tool results exactly as stored. The report may cite only these."
            >
              <EvidencePanel
                evidence={inv.evidence}
                numbers={inv.report?.numbers ?? []}
                issues={issues}
                selection={selection}
                onSelect={select}
              />
            </Panel>
          </div>
        </div>
      </div>

      <Trace investigation={inv} running={running} />

      {inv.work_order_id && !replay ? (
        <section
          id={WORK_ORDER_ANCHOR}
          aria-label={`Work order ${inv.work_order_id}`}
          className="mt-14 scroll-mt-[calc(var(--bar-height)+24px)] border-t border-hairline pt-10"
        >
          <WorkOrderSection id={inv.work_order_id} hypotheses={readHypotheses(inv.report) ?? []} />
        </section>
      ) : null}
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
    <>
      <span>
        {failed
          ? "Recorded run: it failed when it was generated and is not replayed"
          : "Recorded run: generated once, replayed without calling a model"}
      </span>
      {unitId != null ? (
        <span className="tnum">
          Data as of unit {unitId}
          {unit.data ? `, ${formatPlantTime(unit.data.timestamp)}` : ""}
        </span>
      ) : null}
    </>
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
  const models = investigation.models
    .map((m) => `${ROLE_NAMES[m.role] ?? m.role} ${m.model_id}`)
    .join(", ");
  return (
    <span className="tnum">
      {models}
      {u
        ? `. ${plural(u.requests, "model call")}, ${formatInt(u.tokens_in + u.tokens_out + u.tokens_reasoning)} tokens, ${formatNumber(u.points, 5)} points${
            u.requests_without_usage > 0
              ? `; ${formatInt(u.requests_without_usage)} ${u.requests_without_usage === 1 ? "call" : "calls"} did not report usage and ${u.requests_without_usage === 1 ? "is" : "are"} not in these sums`
              : ""
          }.`
        : "."}
    </span>
  );
}

/** One result of the checks as a readout: "3/4". The sentence beside it states it in words. */
function CheckFigure({ label, value, of }: { label: string; value: number; of: number }) {
  return (
    <span className="flex items-end gap-2.5">
      <span className="readout text-[34px] leading-[36px]">
        {formatInt(value)}
        <span className="text-ink-3">/{formatInt(of)}</span>
      </span>
      <span className="max-w-[10ch] pb-0.5 text-[12px] leading-4 text-ink-2">{label}</span>
    </span>
  );
}

function VerificationSummary({ investigation }: { investigation: Investigation }) {
  const v = investigation.verification!;
  const remaining = v.issues.length;
  const supported = v.claims.filter((c) => c.verdict === "supported").length;
  return (
    <div
      className={cn(
        "mb-9 overflow-hidden rounded-[16px]",
        remaining
          ? "bg-fail-wash shadow-[inset_0_0_0_1px_color-mix(in_oklab,var(--fail)_28%,transparent)]"
          : "bg-pass-wash shadow-[inset_0_0_0_1px_color-mix(in_oklab,var(--pass)_28%,transparent)]",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-x-8 gap-y-4 px-4 py-4 sm:px-5">
        <div className="flex max-w-[52ch] min-w-0 items-start gap-3">
          {remaining ? (
            <CircleAlertIcon
              aria-hidden="true"
              className="mt-0.5 size-5 shrink-0 text-fail"
              strokeWidth={1.9}
            />
          ) : (
            <CircleCheckIcon
              aria-hidden="true"
              className="mt-0.5 size-5 shrink-0 text-pass"
              strokeWidth={1.9}
            />
          )}
          <div className="min-w-0">
            <p className="text-[15.5px] leading-6 font-[620] text-ink">
              {remaining
                ? `${plural(remaining, "issue")} left after the checks, flagged where ${remaining === 1 ? "it applies" : "they apply"}`
                : "Every check passed"}
            </p>
            <p className="tnum mt-1 text-[13px] leading-5 text-ink-2">
              {formatInt(v.numbers_matched)} of {formatInt(v.numbers_checked)} numbers match their
              evidence. {plural(v.claims.length, "finding")} checked by{" "}
              {v.verifier_model ?? "no verifier model"}.{" "}
              {v.rounds === 0
                ? "No revision was needed."
                : `The writer revised the report ${v.rounds === 1 ? "once" : "twice"}.`}
            </p>
          </div>
        </div>
        <div aria-hidden="true" className="tnum flex gap-x-7 pl-8 text-ink">
          <CheckFigure
            label="numbers match evidence"
            value={v.numbers_matched}
            of={v.numbers_checked}
          />
          <CheckFigure label="findings supported" value={supported} of={v.claims.length} />
        </div>
      </div>
      {remaining ? (
        <ul className="grid grid-cols-[minmax(0,1fr)] border-t border-[color-mix(in_oklab,var(--fail)_22%,transparent)] text-[13px] leading-5">
          {v.issues.map((issue, i) => (
            <li
              key={i}
              className="border-b border-[color-mix(in_oklab,var(--fail)_14%,transparent)] py-2.5 pr-4 pl-12 text-ink last:border-b-0 sm:pr-5 sm:pl-[52px]"
            >
              <span className="font-[600]">{ISSUE_CODE[issue.code] ?? issue.code}</span>
              <span className="text-ink-2">
                {" "}
                at {issue.location}
                {issue.severity === "warning" ? ", warning" : ""}.{" "}
              </span>
              <span className="text-ink-2">{issue.message}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
