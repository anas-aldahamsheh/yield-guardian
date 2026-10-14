"use client";

import type { SensorGroup, SensorGroups as Groups } from "@yield-guardian/contracts";
import { Fragment, useState } from "react";

import { formatNumber, formatPercent, formatPValue } from "@/lib/format";
import { UNIVARIATE_DIRECTION } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { ScrollRegion } from "@/components/scroll-region";

/** How the groups were made, written from the API's method fields. */
export function groupingMethodText(m: Groups["method"]): string {
  return (
    `Sensors whose Spearman correlation is at least ${formatNumber(m.threshold, 2)} are grouped (${m.linkage} linkage). ` +
    `A group is stable when it ranks in the top set in at least ${formatPercent(m.stability_threshold, 0)} of ${m.stability_refits} bootstrap refits, ` +
    `and significant when its importance survives ${m.permutations} label permutations at a Benjamini-Hochberg q of ${formatNumber(m.fdr_q, 2)}.`
  );
}

/**
 * Correlated sensors reported together, most important first. A row opens to the per-sensor
 * Mann-Whitney tests; tests that were not run read "not tested".
 */
export function SensorGroupsTable({
  data,
  selectedSensor,
  onSelectSensor,
}: {
  data: Groups;
  selectedSensor: string | null;
  onSelectSensor: (sensor: string) => void;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const max = Math.max(0.0001, ...data.groups.map((g) => g.importance));
  return (
    <ScrollRegion label="Sensor groups by importance">
      <table className="w-full min-w-[640px] border-collapse text-left text-[13px] leading-5">
        <caption className="sr-only">Sensor groups by importance</caption>
        <thead>
          <tr className="border-y border-hairline text-[12px] text-ink-3">
            <th scope="col" className="px-4 py-2 font-normal sm:px-5">Group</th>
            <th scope="col" className="px-2 py-2 font-normal">Sensors</th>
            <th scope="col" className="w-[22%] px-2 py-2 font-normal">Importance (mean |SHAP|, log-odds)</th>
            <th scope="col" className="px-2 py-2 text-right font-normal">Stability</th>
            <th scope="col" className="px-2 py-2 text-right font-normal">q</th>
            <th scope="col" className="px-4 py-2 font-normal sm:px-5">Reading</th>
          </tr>
        </thead>
        <tbody>
          {data.groups.map((g) => {
            const expanded = open === g.group_id;
            const containsSelected = selectedSensor != null && g.sensors.includes(selectedSensor);
            return (
              <Fragment key={g.group_id}>
                <tr className={cn("border-b border-hairline", containsSelected && "bg-die-2")}>
                  <th scope="row" className="px-4 py-2 align-top font-normal sm:px-5">
                    <button
                      type="button"
                      aria-expanded={expanded}
                      aria-controls={`group-${g.group_id}`}
                      onClick={() => setOpen(expanded ? null : g.group_id)}
                      className="tnum flex cursor-pointer items-center gap-1.5 text-ink"
                    >
                      <svg width="8" height="8" aria-hidden="true" className={cn("transition-transform", expanded && "rotate-90")}>
                        <path d="M2,1 L6,4 L2,7" fill="none" stroke="currentColor" strokeWidth="1.3" />
                      </svg>
                      {g.group_id}
                    </button>
                  </th>
                  <td className="px-2 py-2 align-top">
                    <SensorLinks group={g} selected={selectedSensor} onSelect={onSelectSensor} />
                  </td>
                  <td className="px-2 py-2 align-top">
                    <span className="flex items-center gap-2">
                      <span className="h-2.5 rounded-[2px] bg-ink-2" style={{ width: `${(g.importance / max) * 100}%`, minWidth: 2 }} aria-hidden="true" />
                      <span className="tnum shrink-0 text-ink-2">{formatNumber(g.importance, 3)}</span>
                    </span>
                  </td>
                  <td className="tnum px-2 py-2 text-right align-top text-ink-2">{formatPercent(g.stability, 0)}</td>
                  <td className="tnum px-2 py-2 text-right align-top text-ink">{formatPValue(g.q_value)}</td>
                  <td className="px-4 py-2 align-top text-ink-2 sm:px-5">
                    {g.significant && g.stable ? (
                      <span className="text-ink">Significant and stable</span>
                    ) : g.significant ? (
                      "Significant, not stable"
                    ) : g.stable ? (
                      "Stable, not significant"
                    ) : (
                      <span className="text-ink-3">Neither</span>
                    )}
                  </td>
                </tr>
                {expanded ? (
                  <tr id={`group-${g.group_id}`} className="border-b border-hairline bg-die-2">
                    <td colSpan={6} className="px-4 py-3 sm:px-5">
                      <UnivariateTable group={g} />
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </ScrollRegion>
  );
}

function SensorLinks({ group, selected, onSelect }: { group: SensorGroup; selected: string | null; onSelect: (s: string) => void }) {
  const [all, setAll] = useState(false);
  const limit = 6;
  const shown = all ? group.sensors : group.sensors.slice(0, limit);
  return (
    <span className="tnum flex flex-wrap gap-x-2">
      {shown.map((s) => (
        <button
          key={s}
          type="button"
          onClick={() => onSelect(s)}
          aria-pressed={selected === s}
          className={cn(
            // 24 px tall: a touch target that meets WCAG 2.2 target size.
            "min-h-6 cursor-pointer underline decoration-hairline-strong underline-offset-4 hover:text-ink",
            s === group.representative ? "font-medium text-ink" : "text-ink-2",
            selected === s && "lit rounded-[2px] px-0.5",
          )}
          title={s === group.representative ? "Representative sensor" : undefined}
        >
          {s}
        </button>
      ))}
      {group.sensors.length > limit && !all ? (
        <button type="button" onClick={() => setAll(true)} className="min-h-6 cursor-pointer text-ink-3 hover:text-ink">
          +{group.sensors.length - limit} more
        </button>
      ) : null}
    </span>
  );
}

function UnivariateTable({ group }: { group: SensorGroup }) {
  return (
    <>
      <p className="mb-2 text-[12px] leading-4 text-ink-3">
        Mann-Whitney test of each sensor between failed and passed units, Benjamini-Hochberg across sensors. The representative is {group.representative}.
      </p>
      <table className="w-full max-w-[560px] border-collapse text-left text-[13px] leading-5">
        <caption className="sr-only">Per-sensor tests in group {group.group_id}</caption>
        <thead>
          <tr className="text-[12px] text-ink-3">
            <th scope="col" className="py-1 pr-3 font-normal">Sensor</th>
            <th scope="col" className="py-1 pr-3 font-normal">Direction</th>
            <th scope="col" className="py-1 pr-3 text-right font-normal">p</th>
            <th scope="col" className="py-1 text-right font-normal">q</th>
          </tr>
        </thead>
        <tbody>
          {group.univariate.map((u) => (
            <tr key={u.sensor} className="border-t border-hairline">
              <th scope="row" className="tnum py-1 pr-3 font-normal text-ink">{u.sensor}</th>
              <td className={cn("py-1 pr-3", u.direction === "not_tested" ? "text-ink-3" : "text-ink-2")}>{UNIVARIATE_DIRECTION[u.direction] ?? u.direction}</td>
              <td className="tnum py-1 pr-3 text-right text-ink-2">{u.mann_whitney_p == null ? <span className="text-ink-3">not tested</span> : formatPValue(u.mann_whitney_p)}</td>
              <td className="tnum py-1 text-right text-ink">{u.q_value == null ? <span className="text-ink-3">not tested</span> : formatPValue(u.q_value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
