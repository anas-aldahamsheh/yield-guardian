"use client";

import { LocalDateTime } from "@/components/local-date-time";
import { useQuery } from "@tanstack/react-query";
import type { Investigation } from "@yield-guardian/contracts";
import Link from "next/link";
import { useCallback, useRef, useState } from "react";

import { PageFrame, PageHeader, Panel } from "@/components/page";
import { ErrorState, Placeholder } from "@/components/states";
import { Button } from "@/components/ui/button";
import { useApi } from "@/lib/api/context";
import { ApiError } from "@/lib/api/errors";
import { q } from "@/lib/api/queries";
import { LIVE_STATUSES, issuesByTarget, triggerUnit } from "@/lib/investigation/events";
import { useInvestigationStream } from "@/lib/investigation/use-investigation-stream";
import { formatInt, formatNumber, formatPlantTime, plural } from "@/lib/format";
import { ISSUE_CODE, ROLE_NAMES, TRIGGER_KIND } from "@/lib/labels";
import { cn } from "@/lib/utils";

import { DecisionActions } from "./decision";
import { EvidencePanel } from "./evidence-panel";
import { type EvidenceSelection, Report } from "./report";
import { StatusLabel } from "./status-label";
import { Steps } from "./steps";

export function InvestigationView({ id }: { id: string }) {
  const api = useApi();
  const query = useQuery(q.investigation(api, id));
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
        <ErrorState error={query.error} onRetry={notFound ? undefined : () => void query.refetch()} />
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
        title={inv.title}
        meta={
          <span className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <StatusLabel status={inv.status} />
            <span>
              From {TRIGGER_KIND[inv.trigger.kind]?.toLowerCase()} <TriggerLink investigation={inv} />
            </span>
            <span className="tnum">Started <LocalDateTime iso={inv.created_at} /></span>
            {inv.recorded ? <RecordedLabel investigation={inv} /> : null}
          </span>
        }
        actions={
          !LIVE_STATUSES.has(stored.status) && !(stored.recorded && stored.status === "failed") ? (
            <Button variant="outline" size="sm" disabled={replay != null && state === "streaming"} onClick={startReplay}>
              {replay != null && state === "streaming" ? "Replaying…" : "Replay the run"}
            </Button>
          ) : null
        }
      />
      {inv.trigger.question ? (
        <p className="-mt-3 mb-6 max-w-[72ch] text-[15px] leading-6 text-ink-2">Question: {inv.trigger.question}</p>
      ) : null}

      {inv.error ? <ErrorState className="mb-4" error={new ApiError(inv.error.status, inv.error)} /> : null}

      <div className="grid grid-cols-[minmax(0,1fr)] gap-street xl:grid-cols-[minmax(0,1fr)_440px]">
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
              actionsSlot={replay ? undefined : <DecisionActions investigation={inv} report={inv.report} shared={shared} />}
            />
          ) : (
            <p className="py-8 text-[15px] leading-6 text-ink-3">
              {running
                ? "The writer drafts the report once the evidence is in. Steps appear on the right as they run."
                : "This run ended without a report."}
            </p>
          )}
        </Panel>

        <div className="grid grid-cols-[minmax(0,1fr)] min-w-0 content-start gap-street">
          <Panel
            live={running}
            title="Run"
            description={<RunDescription investigation={inv} />}
            actions={running ? <span className="text-[13px] text-ink-2">{state === "reconnecting" ? "Reconnecting…" : "Running"}</span> : null}
          >
            <Steps steps={inv.steps} running={running} selection={selection} onSelect={select} />
          </Panel>
          <div ref={evidenceRef} className="scroll-mt-[calc(var(--bar-height)+16px)]">
            <Panel title="Evidence" description="Tool results exactly as stored. The report may cite only these.">
              <EvidencePanel evidence={inv.evidence} numbers={inv.report?.numbers ?? []} issues={issues} selection={selection} onSelect={select} />
            </Panel>
          </div>
        </div>
      </div>
    </PageFrame>
  );
}

function BackLink() {
  return (
    <Link href="/investigations" className="mb-3 inline-block text-[13px] text-ink-2 underline decoration-hairline-strong underline-offset-4 hover:text-ink">
      All investigations
    </Link>
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
      <span>{failed ? "Recorded run: it failed when it was generated and is not replayed" : "Recorded run: generated once, replayed without calling a model"}</span>
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
  const { kind, ref } = investigation.trigger;
  const unit = kind === "alarm" ? ref.match(/^AL-(\d+)-/)?.[1] : kind === "unit" ? ref : null;
  const href = unit ? `/units/${unit}` : kind === "wafer" ? `/wafers/${ref}` : kind === "lot" ? `/lots/${ref}` : null;
  return href ? (
    <Link href={href} className="tnum text-ink underline decoration-hairline-strong underline-offset-4 hover:decoration-ink">
      {ref}
    </Link>
  ) : (
    <span className="tnum text-ink">{ref}</span>
  );
}

function RunDescription({ investigation }: { investigation: Investigation }) {
  const u = investigation.usage;
  const models = investigation.models.map((m) => `${ROLE_NAMES[m.role] ?? m.role} ${m.model_id}`).join(", ");
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

/** One result of the checks as a readout: "3/4". The sentence below states it in words. */
function CheckFigure({ label, value, of }: { label: string; value: number; of: number }) {
  return (
    <span className="flex items-baseline gap-2">
      <span className="readout text-[28px] leading-8">
        {formatInt(value)}
        <span className="text-ink-3">/{formatInt(of)}</span>
      </span>
      <span className="max-w-[11ch] text-[12px] leading-4 text-ink-2">{label}</span>
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
        "mb-7 rounded-sm border-l-2 px-4 py-3.5",
        remaining ? "border-fail bg-fail-wash" : "border-pass bg-pass-wash",
      )}
    >
      <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
        <p className="text-[15px] leading-6 font-medium text-ink">
          {remaining
            ? `${plural(remaining, "issue")} left after the checks, flagged where ${remaining === 1 ? "it applies" : "they apply"}`
            : "Every check passed"}
        </p>
        <div aria-hidden="true" className="tnum flex gap-x-6 text-ink">
          <CheckFigure label="numbers match evidence" value={v.numbers_matched} of={v.numbers_checked} />
          <CheckFigure label="findings supported" value={supported} of={v.claims.length} />
        </div>
      </div>
      <p className="tnum mt-1.5 text-[13px] leading-5 text-ink-2">
        {formatInt(v.numbers_matched)} of {formatInt(v.numbers_checked)} numbers match their evidence.{" "}
        {plural(v.claims.length, "finding")} checked by {v.verifier_model ?? "no verifier model"}.{" "}
        {v.rounds === 0 ? "No revision was needed." : `The writer revised the report ${v.rounds === 1 ? "once" : "twice"}.`}
      </p>
      {remaining ? (
        <ul className="mt-2 grid grid-cols-[minmax(0,1fr)] gap-1 text-[13px] leading-5">
          {v.issues.map((issue, i) => (
            <li key={i} className="text-ink">
              <span className="font-medium">{ISSUE_CODE[issue.code] ?? issue.code}</span>
              <span className="text-ink-2"> at {issue.location}{issue.severity === "warning" ? ", warning" : ""}. </span>
              <span className="text-ink-2">{issue.message}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
