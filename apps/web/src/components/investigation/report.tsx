"use client";

import type { NumberRef, Report as ReportData, Verification, VerificationIssue } from "@yield-guardian/contracts";
import { Fragment } from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { issuesByTarget, segmentNumbers } from "@/lib/investigation/events";
import { CLAIM_VERDICT, ISSUE_CODE, STRENGTH } from "@/lib/labels";
import { cn } from "@/lib/utils";

/** What the reader has selected: an evidence record, and optionally one value inside it. */
export interface EvidenceSelection {
  evidenceId: string;
  path?: string;
  number?: number;
}

export interface Shared {
  numbers: NumberRef[];
  issues: Map<string, VerificationIssue[]>;
  selection: EvidenceSelection | null;
  onSelect: (selection: EvidenceSelection) => void;
}

/** A report a language model wrote: serif, every number and claim linked to its evidence. */
export function Report({
  report,
  verification,
  selection,
  onSelect,
  actionsSlot,
}: {
  report: ReportData;
  verification: Verification | null;
  selection: EvidenceSelection | null;
  onSelect: (selection: EvidenceSelection) => void;
  /** Replaces the plain action list, for choosing actions to approve. */
  actionsSlot?: React.ReactNode;
}) {
  const shared: Shared = {
    numbers: report.numbers,
    issues: issuesByTarget(verification?.issues ?? []),
    selection,
    onSelect,
  };
  const verdicts = new Map(verification?.claims.map((c) => [c.finding_index, c]) ?? []);

  return (
    <article className="min-w-0" aria-labelledby="report-summary">
      <h2 id="report-summary" className="sr-only">
        Report
      </h2>
      <p className="written max-w-[68ch] text-ink">
        <WrittenText text={report.summary} {...shared} />
      </p>
      <Flags issues={shared.issues.get("summary")} />

      <h3 className="mt-8 text-[15px] leading-6 font-semibold text-ink">Findings</h3>
      <ol className="mt-2 grid gap-5">
        {report.findings.map((finding, i) => {
          const verdict = verdicts.get(i);
          return (
            <li key={i} className="grid grid-cols-[1.75rem_minmax(0,1fr)] gap-x-2">
              <span className="tnum pt-[5px] text-[13px] leading-5 text-ink-3">{i + 1}.</span>
              <div className="min-w-0">
                <p className="written max-w-[66ch] text-ink">
                  <WrittenText text={finding.claim} {...shared} />
                </p>
                <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[13px] leading-5">
                  <EvidenceChips ids={finding.evidence_ids} {...shared} />
                  <span className="text-ink-3">{STRENGTH[finding.strength] ?? finding.strength}</span>
                  {verdict ? (
                    <span
                      className={cn(
                        verdict.verdict === "supported"
                          ? "text-ink-2"
                          : verdict.verdict === "unsupported"
                            ? "text-fail"
                            : "text-ink",
                      )}
                    >
                      Verifier: {CLAIM_VERDICT[verdict.verdict]?.toLowerCase()}
                      {verdict.note ? <span className="text-ink-3">. {verdict.note}</span> : null}
                    </span>
                  ) : null}
                </div>
                <Flags issues={shared.issues.get(`findings[${i}]`)} />
              </div>
            </li>
          );
        })}
      </ol>

      <h3 className="mt-8 text-[15px] leading-6 font-semibold text-ink">Proposed actions</h3>
      {actionsSlot ?? (
        <ol className="mt-2 grid gap-4">
          {report.actions.map((action, i) => (
            <li key={i} className="grid grid-cols-[1.75rem_minmax(0,1fr)] gap-x-2">
              <span className="tnum pt-[5px] text-[13px] leading-5 text-ink-3">{i + 1}.</span>
              <ActionBody action={action} index={i} {...shared} />
            </li>
          ))}
        </ol>
      )}

      {report.limitations.length ? (
        <>
          <h3 className="mt-8 text-[15px] leading-6 font-semibold text-ink">Limitations</h3>
          <ul className="mt-2 grid max-w-[68ch] list-disc gap-1.5 pl-5 text-[15px] leading-6 text-ink-2 marker:text-ink-3">
            {report.limitations.map((l, i) => (
              <li key={i}>{l}</li>
            ))}
          </ul>
        </>
      ) : null}
    </article>
  );
}

export function ActionBody({
  action,
  index,
  ...shared
}: { action: ReportData["actions"][number]; index: number } & Shared) {
  return (
    <div className="min-w-0">
      <p className="written max-w-[66ch] text-ink">
        <WrittenText text={action.action} {...shared} />
      </p>
      <p className="mt-1 max-w-[66ch] text-[15px] leading-6 text-ink-2">
        <WrittenText text={action.rationale} {...shared} />
      </p>
      <div className="mt-1.5 text-[13px] leading-5">
        <EvidenceChips ids={action.evidence_ids} {...shared} />
      </div>
      <Flags issues={shared.issues.get(`actions[${index}]`)} />
    </div>
  );
}

/** Written text with its listed numbers as links to the evidence value they came from. */
function WrittenText({ text, numbers, issues, selection, onSelect }: { text: string } & Shared) {
  return (
    <>
      {segmentNumbers(text, numbers).map((segment, i) => {
        if (segment.number == null) return <Fragment key={i}>{segment.text}</Fragment>;
        const ref = numbers[segment.number]!;
        const flagged = issues.get(`numbers[${segment.number}]`);
        const active = selection?.number === segment.number;
        const button = (
          <button
            type="button"
            onClick={() => onSelect({ evidenceId: ref.evidence_id, path: ref.path, number: segment.number })}
            className={cn(
              "tnum cursor-pointer rounded-[2px] px-0.5 underline decoration-1 underline-offset-[5px]",
              flagged
                ? "bg-fail-wash decoration-fail decoration-wavy"
                : "decoration-hairline-strong decoration-dotted hover:decoration-ink",
              active && "lit",
            )}
            aria-label={`${segment.text}, from evidence ${ref.evidence_id}${flagged ? ", flagged by the checks" : ""}. Show the value.`}
          >
            {segment.text}
          </button>
        );
        return flagged ? (
          <Tooltip key={i}>
            <TooltipTrigger asChild>{button}</TooltipTrigger>
            <TooltipContent className="max-w-[320px] font-sans">{flagged.map((f) => f.message).join(" ")}</TooltipContent>
          </Tooltip>
        ) : (
          <Fragment key={i}>{button}</Fragment>
        );
      })}
    </>
  );
}

export function EvidenceChips({ ids, selection, onSelect }: { ids: string[] } & Pick<Shared, "selection" | "onSelect">) {
  return (
    <span className="inline-flex flex-wrap gap-1">
      {ids.map((id) => (
        <button
          key={id}
          type="button"
          onClick={() => onSelect({ evidenceId: id })}
          aria-label={`Show evidence ${id}`}
          aria-pressed={selection?.evidenceId === id && selection.path == null}
          className={cn(
            "tnum inline-flex h-6 min-w-8 cursor-pointer items-center justify-center rounded-sm border border-hairline-strong px-1.5 text-[12px] text-ink-2 hover:border-ink-3 hover:text-ink",
            selection?.evidenceId === id && "lit border-transparent text-ink",
          )}
        >
          {id}
        </button>
      ))}
    </span>
  );
}

/** Issues the checks left on this part of the report, shown where they apply. */
function Flags({ issues }: { issues: VerificationIssue[] | undefined }) {
  if (!issues?.length) return null;
  return (
    <ul className="mt-2 grid gap-1">
      {issues.map((issue, i) => (
        <li key={i} className="flex max-w-[66ch] gap-2 rounded-sm border-l-2 border-fail bg-fail-wash px-3 py-1.5 text-[13px] leading-5 text-ink">
          <span className="font-medium">{ISSUE_CODE[issue.code] ?? issue.code}.</span>
          <span className="text-ink-2">{issue.message}</span>
        </li>
      ))}
    </ul>
  );
}
