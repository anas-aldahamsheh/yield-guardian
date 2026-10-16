"use client";

import { useQuery } from "@tanstack/react-query";
import type { KnowledgeSource } from "@yield-guardian/contracts";

import { ScrollRegion } from "@/components/scroll-region";
import { useApi } from "@/lib/api/context";
import { q } from "@/lib/api/queries";
import type { Assessment, Hypothesis, HypothesisEvidence } from "@/lib/investigation/hypotheses";

import { EvidenceChips, Flags, type Shared, WrittenText } from "./report";

const ASSESSMENT: Record<Assessment, { label: string; className: string }> = {
  supported: { label: "Supported", className: "text-ink font-[560]" },
  not_supported: { label: "Not supported", className: "text-ink-2" },
  inconclusive: { label: "Inconclusive", className: "text-ink-2" },
};

/**
 * The report's hypothesis table (PLAN_V2 §7): each candidate cause, the literature that names
 * it, the run's evidence for and against it, and the investigator's assessment. Hypotheses stay
 * hypotheses until an engineer confirms a cause on the work order.
 */
export function HypothesisTable({ rows, ...shared }: { rows: Hypothesis[] } & Shared) {
  const api = useApi();
  const causes = useQuery({
    ...q.patternCauses(api),
    enabled: rows.some((r) => r.source_ids.length > 0),
  });
  const sources = new Map((causes.data?.sources ?? []).map((s) => [s.source_id, s]));

  return (
    <section
      aria-labelledby="hypotheses-title"
      className="mt-9 border-t border-hairline pt-5"
      data-hypotheses
    >
      <h3 id="hypotheses-title" className="text-[15px] leading-6 font-[620] text-ink">
        Hypotheses
      </h3>
      <p className="mt-0.5 mb-3 max-w-[72ch] text-[13px] leading-5 text-ink-3">
        Candidate causes tested against this run&rsquo;s evidence. &ldquo;Supported&rdquo; means the
        evidence here agrees with it, not that it is the cause: an engineer confirms a cause on the
        work order.
      </p>
      {rows.length === 0 ? (
        <p className="text-[14px] leading-5 text-ink-3">
          The investigator tested no candidate cause for this trigger.
        </p>
      ) : (
        <ScrollRegion label="Hypotheses table" className="-mx-4 sm:-mx-5">
          <table className="w-full min-w-[880px] border-collapse text-left align-top text-[14px] leading-5">
            <caption className="sr-only">
              Hypotheses, with the evidence for and against each
            </caption>
            <thead>
              <tr className="border-y border-hairline text-[12.5px] leading-4 text-ink-3">
                <th scope="col" className="w-[24%] px-5 py-3 font-[520] sm:px-6">
                  Hypothesis
                </th>
                <th scope="col" className="w-[16%] px-3 py-3 font-[520]">
                  Sources
                </th>
                <th scope="col" className="w-[24%] px-3 py-3 font-[520]">
                  Evidence for
                </th>
                <th scope="col" className="w-[24%] px-3 py-3 font-[520]">
                  Evidence against
                </th>
                <th scope="col" className="px-5 py-3 font-[520] sm:px-6">
                  Assessment
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr
                  key={i}
                  className="border-b border-hairline align-top last:border-b-0"
                  data-assessment={row.assessment}
                >
                  <th scope="row" className="px-5 py-3 font-[420] sm:px-6">
                    <span className="written block text-[16px] leading-6 text-ink">
                      <WrittenText text={row.hypothesis} {...shared} />
                    </span>
                    <Flags issues={shared.issues.get(`hypotheses[${i}]`)} />
                  </th>
                  <td className="px-3 py-3 text-[13px] text-ink-2">
                    <SourceList ids={row.source_ids} sources={sources} />
                  </td>
                  <td className="px-3 py-3">
                    <EvidenceList entries={row.evidence_for} empty="None found" shared={shared} />
                  </td>
                  <td className="px-3 py-3">
                    <EvidenceList
                      entries={row.evidence_against}
                      empty="None found"
                      shared={shared}
                    />
                  </td>
                  <td className="px-5 py-3 whitespace-nowrap sm:px-6">
                    <span className={ASSESSMENT[row.assessment].className}>
                      {ASSESSMENT[row.assessment].label}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollRegion>
      )}
    </section>
  );
}

function EvidenceList({
  entries,
  empty,
  shared,
}: {
  entries: HypothesisEvidence[];
  empty: string;
  shared: Shared;
}) {
  if (!entries.length) return <span className="text-[13px] text-ink-3">{empty}</span>;
  return (
    <ul className="grid grid-cols-[minmax(0,1fr)] gap-2">
      {entries.map((e, i) => (
        <li key={i} className="min-w-0">
          <span className="written block text-[15px] leading-6 text-ink">
            <WrittenText text={e.observation} {...shared} />
          </span>
          <span className="mt-1 block text-[12px]">
            <EvidenceChips
              ids={[e.evidence_id]}
              selection={shared.selection}
              onSelect={shared.onSelect}
            />
          </span>
        </li>
      ))}
    </ul>
  );
}

function SourceList({ ids, sources }: { ids: string[]; sources: Map<string, KnowledgeSource> }) {
  if (!ids.length) return <span className="text-ink-3">None cited</span>;
  return (
    <ul className="grid grid-cols-[minmax(0,1fr)] gap-1.5">
      {ids.map((id) => {
        const s = sources.get(id);
        const href = s?.url ?? (s?.doi ? `https://doi.org/${s.doi}` : null);
        const label = s ? `${s.title}${s.year ? ` (${s.year})` : ""}` : id;
        return (
          <li key={id} className="min-w-0 break-words">
            {href ? (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-ink underline decoration-hairline-strong underline-offset-4 hover:decoration-ink"
              >
                {label}
              </a>
            ) : (
              <span className="text-ink">{label}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}
