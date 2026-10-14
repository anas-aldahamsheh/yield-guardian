"use client";

import type { Evidence, NumberRef, VerificationIssue } from "@yield-guardian/contracts";
import { useEffect, useRef } from "react";

import { readPointer } from "@/lib/investigation/events";
import { formatDateTime } from "@/lib/format";
import { TOOL_NAME } from "@/lib/labels";
import { cn } from "@/lib/utils";

import type { EvidenceSelection } from "./report";

/**
 * Evidence as stored: the tool, its arguments, the source bundle and the exact data the report
 * may cite. A number clicked in the report opens here with its value highlighted.
 */
export function EvidencePanel({
  evidence,
  numbers,
  issues,
  selection,
  onSelect,
}: {
  evidence: Evidence[];
  numbers: NumberRef[];
  issues?: Map<string, VerificationIssue[]>;
  selection: EvidenceSelection | null;
  onSelect: (selection: EvidenceSelection) => void;
}) {
  const current = evidence.find((e) => e.evidence_id === selection?.evidenceId) ?? evidence[0];
  if (!current) {
    return <p className="text-[14px] leading-5 text-ink-3">No evidence yet. Each tool result is stored here as it arrives.</p>;
  }
  const number = selection?.number != null && selection.evidenceId === current.evidence_id ? numbers[selection.number] : undefined;
  const path = selection?.evidenceId === current.evidence_id ? selection.path : undefined;
  const value = path ? readPointer(current.data, path) : undefined;

  return (
    <div className="min-w-0">
      <div role="tablist" aria-label="Evidence" className="flex flex-wrap gap-1">
        {evidence.map((e) => (
          <button
            key={e.evidence_id}
            role="tab"
            type="button"
            aria-selected={e.evidence_id === current.evidence_id}
            onClick={() => onSelect({ evidenceId: e.evidence_id })}
            className={cn(
              "tnum h-7 min-w-9 cursor-pointer rounded-sm border px-2 text-[13px]",
              e.evidence_id === current.evidence_id
                ? "lit border-transparent text-ink"
                : "border-hairline-strong text-ink-2 hover:border-ink-3 hover:text-ink",
            )}
          >
            {e.evidence_id}
          </button>
        ))}
      </div>

      <div key={current.evidence_id} role="tabpanel" aria-label={`Evidence ${current.evidence_id}`} className="swap-in mt-4">
        <p className="text-[15px] leading-6 text-ink">{current.summary}</p>
        <dl className="mt-3 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-[13px] leading-5">
          <dt className="text-ink-3">Tool</dt>
          <dd className="text-ink-2">{TOOL_NAME[current.tool] ?? current.tool}</dd>
          <dt className="text-ink-3">Arguments</dt>
          <dd className="tnum break-words text-ink-2">
            {Object.entries(current.arguments).map(([k, v]) => `${k} = ${JSON.stringify(v)}`).join(", ") || "none"}
          </dd>
          <dt className="text-ink-3">Source</dt>
          <dd className="tnum text-ink-2">
            {current.source
              ? `${current.source.name} bundle ${current.source.version}, commit ${current.source.git_commit.slice(0, 7)}`
              : "Literature index"}
          </dd>
          <dt className="text-ink-3">Stored</dt>
          <dd className="tnum text-ink-2">{formatDateTime(current.created_at)}</dd>
        </dl>

        {number && path ? (
          <div className="lit mt-4 rounded-sm px-3 py-2.5 text-[13px] leading-5">
            <p className="text-ink">
              The report writes <span className="tnum font-medium">{number.as_written}</span>. The evidence holds{" "}
              <span className="tnum font-medium">{value === undefined ? "nothing" : formatValue(value)}</span> at{" "}
              <span className="tnum">{path}</span>.
            </p>
            {selection?.number != null
              ? issues?.get(`numbers[${selection.number}]`)?.map((issue, i) => (
                  <p key={i} className="mt-1 text-fail">
                    Flagged: <span className="text-ink-2">{issue.message}</span>
                  </p>
                ))
              : null}
          </div>
        ) : null}

        <div data-json-scroll className="mt-4 max-h-[420px] overflow-auto rounded-sm border border-hairline bg-die-2 p-3">
          <JsonNode value={current.data} path="" highlight={path} />
        </div>
      </div>
    </div>
  );
}

function formatValue(value: unknown): string {
  if (typeof value === "number") return String(value);
  if (value === null) return "null";
  if (typeof value === "string") return `“${value}”`;
  return JSON.stringify(value);
}

function JsonNode({ value, path, highlight, name }: { value: unknown; path: string; highlight?: string; name?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const hit = highlight != null && highlight === path && path !== "";
  useEffect(() => {
    // Scroll only the data box, never the page.
    const node = ref.current;
    const box = node?.closest<HTMLElement>("[data-json-scroll]");
    if (!hit || !node || !box) return;
    const top = node.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop;
    box.scrollTo({ top: Math.max(0, top - box.clientHeight / 3) });
  }, [hit]);

  const label = name != null ? <span className="text-ink-3">{name}: </span> : null;
  const isBranch = value != null && typeof value === "object";
  if (!isBranch) {
    return (
      <div ref={ref} className={cn("tnum text-[12px] leading-5 break-words", hit && "lit -mx-1 rounded-sm px-1")}>
        {label}
        <span className={cn(typeof value === "number" ? "text-ink" : value === null ? "text-ink-3" : "text-ink-2")}>
          {formatValue(value)}
        </span>
      </div>
    );
  }
  const entries: [string, unknown][] = Array.isArray(value)
    ? value.map((v, i) => [String(i), v])
    : Object.entries(value as Record<string, unknown>);
  return (
    <div ref={ref} className={cn("text-[12px] leading-5", hit && "lit -mx-1 rounded-sm px-1")}>
      {label}
      {name != null ? <span className="text-ink-3">{Array.isArray(value) ? `[${entries.length}]` : ""}</span> : null}
      <div className={cn(name != null && "ml-3 border-l border-hairline pl-2")}>
        {entries.map(([k, v]) => (
          <JsonNode key={k} name={k} value={v} path={`${path}/${k.replace(/~/g, "~0").replace(/\//g, "~1")}`} highlight={highlight} />
        ))}
      </div>
    </div>
  );
}
