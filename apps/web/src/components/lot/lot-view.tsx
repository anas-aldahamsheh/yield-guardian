"use client";

import { useQueries, useQuery } from "@tanstack/react-query";
import { decodeWaferCells, type LotDetail, type PatternTest } from "@yield-guardian/contracts";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useState, useSyncExternalStore } from "react";

import { PageFrame, PageHeader, Panel } from "@/components/page";
import { ErrorState, Placeholder } from "@/components/states";
import { Button } from "@/components/ui/button";
import { DieMap, FrequencyLegend } from "@/components/wafer/die-map";
import { usePrefersReducedMotion, webglAvailable } from "@/components/wafer/hero-wafer";
import { useApi } from "@/lib/api/context";
import { ApiError } from "@/lib/api/errors";
import { useStartInvestigation } from "@/lib/api/investigations";
import { q } from "@/lib/api/queries";
import { useSession } from "@/lib/api/session";
import { formatInt, formatPercent, formatPValue } from "@/lib/format";
import { type PatternLabel, patternName } from "@/lib/labels";
import { cn } from "@/lib/utils";

import type { StackWafer } from "./lot-stack-scene";

const LotStackScene = dynamic(() => import("./lot-stack-scene"), { ssr: false, loading: () => null });
const noop = () => () => {};

export function LotView({ lot }: { lot: string }) {
  const api = useApi();
  const query = useQuery(q.lot(api, lot));
  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    return (
      <PageFrame>
        <PageHeader title={`Lot ${lot}`} />
        <ErrorState error={query.error} onRetry={notFound ? undefined : () => void query.refetch()} />
      </PageFrame>
    );
  }
  if (!query.data) {
    return (
      <PageFrame>
        <Placeholder className="h-[560px]" label="Loading the lot" />
      </PageFrame>
    );
  }
  return <LotContent detail={query.data} />;
}

function LotContent({ detail }: { detail: LotDetail }) {
  const api = useApi();
  const wafers = useQueries({ queries: detail.wafers.map((w) => q.wafer(api, w.wafer_id)) });
  const [selected, setSelected] = useState<number | null>(null);
  const reducedMotion = usePrefersReducedMotion();
  const canRender3d = useSyncExternalStore(noop, webglAvailable, () => false);
  const { canAct } = useSession();
  const start = useStartInvestigation();

  // Rebuild the stack only when a map arrives, not on every render of the queries array.
  const mapsKey = wafers.map((w) => w.dataUpdatedAt).join(",");
  const [stackState, setStackState] = useState<{ key: string; stack: StackWafer[] } | null>(null);
  let stack = stackState?.stack ?? [];
  if (!stackState || stackState.key !== mapsKey) {
    stack = detail.wafers.map((w, i) => {
      const map = wafers[i]?.data?.map;
      return { slot: w.wafer_index, grid: map ? { height: map.height, width: map.width, cells: decodeWaferCells(map) } : null };
    });
    setStackState({ key: mapsKey, stack });
  }
  const loaded = stack.filter((w) => w.grid).length;
  const missing = wafers.filter((w) => w.isError).length;
  const current = selected != null ? detail.wafers.find((w) => w.wafer_index === selected) : undefined;
  const currentGrid = selected != null ? stack.find((w) => w.slot === selected)?.grid : null;
  const flagged = detail.tests.filter((t) => t.flagged);

  return (
    <PageFrame>
      <Link href="/lots" className="mb-3 inline-block text-[13px] text-ink-2 underline decoration-hairline-strong underline-offset-4 hover:text-ink">
        All lots
      </Link>
      <PageHeader
        title={<span className="tnum">Lot {detail.lot}</span>}
        description={
          flagged.length
            ? `${formatInt(detail.wafers.length)} wafers. More ${flagged.map((t) => patternName(t.label as PatternLabel)).join(" and ")} wafers than the training period would lead you to expect.`
            : `${formatInt(detail.wafers.length)} wafers. No pattern occurs more often than expected.`
        }
        actions={
          canAct ? (
            <Button variant="outline" onClick={() => start.mutate({ kind: "lot", ref: detail.lot })} disabled={start.isPending}>
              {start.isPending ? "Starting…" : "Investigate this lot"}
            </Button>
          ) : null
        }
      />

      <div className="grid gap-street xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <Panel
          title="The lot as a stack"
          description="Slot 1 at the bottom. Failed dies are red on every wafer, so a pattern repeated through the lot lines up. Choose a slot to take that wafer out."
        >
          <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_9.5rem]">
            <div className="relative aspect-[4/3] min-w-0 overflow-hidden rounded-sm bg-room" data-theme="dark">
              {canRender3d ? (
                <LotStackScene wafers={stack} selected={selected} onSelect={setSelected} reducedMotion={reducedMotion} />
              ) : (
                <p className="p-6 text-[14px] text-ink-2">This browser cannot draw 3D. Use the slot list to read each wafer.</p>
              )}
              <p className="tnum absolute bottom-2 left-3 text-[12px] text-ink-3">
                {loaded} of {detail.wafers.length} maps loaded
                {missing ? `, ${missing} unavailable` : ""}
              </p>
            </div>
            <ol aria-label="Slots" className="grid max-h-[420px] grid-cols-5 gap-1 overflow-y-auto md:grid-cols-1">
              {[...detail.wafers].reverse().map((w) => (
                <li key={w.wafer_id}>
                  <button
                    type="button"
                    aria-pressed={selected === w.wafer_index}
                    onClick={() => setSelected((s) => (s === w.wafer_index ? null : w.wafer_index))}
                    className={cn(
                      "tnum flex w-full cursor-pointer items-baseline justify-between gap-2 rounded-sm px-2 py-1 text-left text-[12px] leading-4 hover:bg-die-2",
                      selected === w.wafer_index && "lit",
                    )}
                  >
                    <span className="text-ink">{w.wafer_index}</span>
                    <span className="hidden truncate text-ink-3 md:inline">{patternName(w.label as PatternLabel | null)}</span>
                  </button>
                </li>
              ))}
            </ol>
          </div>
        </Panel>

        <div className="grid min-w-0 content-start gap-street">
          <Panel
            title={current ? <span className="tnum">Slot {current.wafer_index}: {current.wafer_id}</span> : "Failure frequency across the lot"}
            description={
              current
                ? `Recorded ${patternName(current.label as PatternLabel | null)}, classifier reads ${patternName(current.predicted_label as PatternLabel | null)}.`
                : detail.stacked
                  ? `Share of the ${detail.stacked.wafers} wafers whose die at each position failed.`
                  : undefined
            }
            actions={
              current ? (
                <Link href={`/wafers?wafer=${encodeURIComponent(current.wafer_id)}`} className="text-[13px] text-ink underline decoration-hairline-strong underline-offset-4">
                  Open in the wafer lab
                </Link>
              ) : null
            }
          >
            {current ? (
              currentGrid ? (
                <DieMap data={{ kind: "results", ...currentGrid }} label={`Wafer ${current.wafer_id}`} className="mx-auto max-w-[360px]" />
              ) : (
                <p className="py-8 text-[14px] text-ink-3">This wafer&rsquo;s map is not available.</p>
              )
            ) : detail.stacked ? (
              <StackedMap stacked={detail.stacked} />
            ) : (
              <p className="py-8 text-[14px] text-ink-3">The wafers in this lot have maps of different sizes, so they cannot be stacked.</p>
            )}
          </Panel>
          <Panel title="Patterns against the expected rate" description={`${detail.method}.`} bodyClassName="px-0 sm:px-0">
            <PatternTests tests={detail.tests} />
          </Panel>
        </div>
      </div>
    </PageFrame>
  );
}

function StackedMap({ stacked }: { stacked: NonNullable<LotDetail["stacked"]> }) {
  const max = Math.max(0.05, ...stacked.frequencies.map((v) => v ?? 0));
  return (
    <>
      <DieMap
        data={{ kind: "frequency", height: stacked.height, width: stacked.width, values: stacked.frequencies }}
        max={max}
        label={`Failure frequency map over ${stacked.wafers} wafers; the highest share at one die is ${formatPercent(max, 0)}.`}
        className="mx-auto max-w-[360px]"
      />
      <FrequencyLegend max={max} className="mx-auto mt-3 max-w-[360px]" />
    </>
  );
}

function PatternTests({ tests }: { tests: PatternTest[] }) {
  return (
    <table className="w-full border-collapse text-left text-[13px] leading-5">
      <caption className="sr-only">Binomial tests per pattern</caption>
      <thead>
        <tr className="border-y border-hairline text-[12px] text-ink-3">
          <th scope="col" className="px-4 py-2 font-normal sm:px-5">Pattern</th>
          <th scope="col" className="px-2 py-2 text-right font-normal">Wafers</th>
          <th scope="col" className="px-2 py-2 text-right font-normal">Expected</th>
          <th scope="col" className="px-2 py-2 text-right font-normal">p</th>
          <th scope="col" className="px-4 py-2 text-right font-normal sm:px-5">q</th>
        </tr>
      </thead>
      <tbody>
        {tests.map((t) => (
          <tr key={t.label} className="border-b border-hairline last:border-b-0">
            <th scope="row" className="px-4 py-2 font-normal sm:px-5">
              <span className={cn(t.flagged ? "font-medium text-ink" : "text-ink-2")}>{patternName(t.label as PatternLabel)}</span>
              {t.flagged ? <span className="ml-2 text-[12px] text-fail">More than expected</span> : null}
            </th>
            <td className="tnum px-2 py-2 text-right text-ink">
              {t.count} of {t.wafers}
            </td>
            <td className="tnum px-2 py-2 text-right text-ink-2">{formatPercent(t.expected_rate)}</td>
            <td className="tnum px-2 py-2 text-right text-ink-2">{formatPValue(t.p_value)}</td>
            <td className="tnum px-4 py-2 text-right text-ink sm:px-5">{formatPValue(t.q_value)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
