"use client";

import { useQuery } from "@tanstack/react-query";
import {
  decodeWaferCells,
  type WaferDetail,
  type WaferMap,
  type WaferSummary,
} from "@yield-guardian/contracts";
import Link from "next/link";
import { useMemo } from "react";

import { PageFrame, PageHeader, Panel, Reading } from "@/components/page";
import { EmptyState, ErrorState, Placeholder, QueryView } from "@/components/states";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { useApi } from "@/lib/api/context";
import { useStartInvestigation } from "@/lib/api/investigations";
import { q } from "@/lib/api/queries";
import { useSession } from "@/lib/api/session";
import { useParam } from "@/lib/use-param";
import { formatInt, formatNumber, formatPercent, formatPValue, formatReading } from "@/lib/format";
import { type PatternLabel, patternName } from "@/lib/labels";
import { lotHref } from "@/lib/routes";
import { cn } from "@/lib/utils";

import { DieMap } from "./die-map";
import { WaferAttribution } from "./wafer-attribution";

export const PATTERN_LABELS: PatternLabel[] = [
  "Center",
  "Donut",
  "Edge-Loc",
  "Edge-Ring",
  "Loc",
  "Near-full",
  "Random",
  "Scratch",
  "none",
];

export function WaferLab() {
  const [selected, setSelected] = useParam("wafer");
  const [label, setLabel] = useParam("label");
  const [unknown, setUnknown] = useParam("unknown");
  const api = useApi();
  const filter = useMemo(
    () => ({
      ...(label ? { label: label as PatternLabel } : {}),
      ...(unknown === "1" ? { unknown: true } : {}),
      limit: 100,
    }),
    [label, unknown],
  );
  const list = useQuery(q.wafers(api, filter));
  const current = selected ?? list.data?.items[0]?.wafer_id ?? null;

  return (
    <PageFrame>
      <PageHeader
        title="Wafer lab"
        description="Wafer maps from WM-811K: the pattern the classifier reads, whether the map looks like anything it was trained on, whether fail dies cluster, and the most similar wafers."
      />
      <div className="grid grid-cols-[minmax(0,1fr)] gap-street lg:grid-cols-[320px_minmax(0,1fr)]">
        <Panel
          title="Wafers"
          description={list.data ? `${formatInt(list.data.total)} match` : undefined}
          bodyClassName="px-0 sm:px-0 pb-0"
          className="lg:sticky lg:top-[calc(var(--bar-height)+8px)] lg:flex lg:max-h-[calc(100dvh-var(--bar-height)-16px)] lg:flex-col lg:overflow-hidden"
        >
          <div className="grid grid-cols-[minmax(0,1fr)] gap-3 px-4 pb-3 sm:px-5">
            <Select value={label ?? "all"} onValueChange={(v) => setLabel(v === "all" ? null : v)}>
              <SelectTrigger aria-label="Recorded pattern" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All recorded patterns</SelectItem>
                {PATTERN_LABELS.map((l) => (
                  <SelectItem key={l} value={l}>
                    {patternName(l)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="flex items-center gap-2">
              <Switch
                id="unknown-only"
                checked={unknown === "1"}
                onCheckedChange={(v) => setUnknown(v ? "1" : null)}
              />
              <Label htmlFor="unknown-only" className="text-[13px] text-ink-2">
                Only maps unlike the training patterns
              </Label>
            </div>
          </div>
          <div className="min-h-0 overflow-y-auto border-t border-hairline lg:flex-1">
            {list.isError ? (
              <ErrorState
                compact
                className="m-4"
                error={list.error}
                onRetry={() => void list.refetch()}
              />
            ) : !list.data ? (
              <Placeholder className="m-4 h-64" label="Loading wafers" />
            ) : list.data.items.length === 0 ? (
              <EmptyState className="m-4" title="No wafer matches">
                Choose another pattern, or show all maps.
              </EmptyState>
            ) : (
              <ul aria-label="Wafers">
                {list.data.items.map((w) => (
                  <li key={w.wafer_id}>
                    <button
                      type="button"
                      onClick={() => setSelected(w.wafer_id)}
                      aria-current={w.wafer_id === current ? "true" : undefined}
                      className={cn(
                        "flex w-full cursor-pointer items-baseline justify-between gap-3 border-b border-hairline px-4 py-2 text-left text-[14px] leading-5 hover:bg-surface-2 sm:px-5",
                        w.wafer_id === current && "lit",
                      )}
                    >
                      <span className="tnum truncate text-ink">{w.wafer_id}</span>
                      <span className="shrink-0 text-[12px] text-ink-3">
                        {patternName(w.label as PatternLabel | null)}
                        {w.predicted_label && w.predicted_label !== w.label
                          ? `, read as ${patternName(w.predicted_label as PatternLabel)}`
                          : ""}
                        {w.unknown ? ", unknown" : ""}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Panel>
        {current ? <WaferPanel waferId={current} onSelect={setSelected} /> : null}
      </div>
    </PageFrame>
  );
}

function grid(map: WaferMap) {
  return {
    kind: "results" as const,
    height: map.height,
    width: map.width,
    cells: decodeWaferCells(map),
  };
}

function counts(cells: Uint8Array) {
  let pass = 0;
  let fail = 0;
  for (const c of cells) {
    if (c === 1) pass += 1;
    else if (c === 2) fail += 1;
  }
  return { pass, fail };
}

function WaferPanel({ waferId, onSelect }: { waferId: string; onSelect: (id: string) => void }) {
  const api = useApi();
  const detail = useQuery(q.wafer(api, waferId));
  return (
    <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] content-start gap-street">
      <QueryView
        query={detail}
        loading={<Placeholder className="h-[560px]" label="Loading the wafer" />}
      >
        {(d) => <WaferDetailView detail={d} />}
      </QueryView>
      <SimilarWafers waferId={waferId} onSelect={onSelect} />
      {detail.data?.prediction ? (
        <PatternCauses label={detail.data.prediction.top_label as PatternLabel} />
      ) : null}
    </div>
  );
}

function WaferDetailView({ detail }: { detail: WaferDetail }) {
  const data = useMemo(() => grid(detail.map), [detail.map]);
  const n = counts(data.cells);
  const w = detail.wafer;
  const p = detail.prediction;
  const s = detail.spatial;
  const { canAct } = useSession();
  const start = useStartInvestigation();
  return (
    <Panel
      title={<span className="tnum">Wafer {w.wafer_id}</span>}
      description={
        <>
          Lot{" "}
          <Link
            href={lotHref(w.lot)}
            className="tnum text-ink-2 underline decoration-hairline-strong underline-offset-4"
          >
            {w.lot}
          </Link>
          , wafer {w.wafer_index}. Official split: {w.official_split ?? "unlabelled"}.
        </>
      }
      actions={
        canAct ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() => start.mutate({ kind: "wafer", ref: w.wafer_id })}
            disabled={start.isPending}
          >
            {start.isPending ? "Starting…" : "Investigate this wafer"}
          </Button>
        ) : null
      }
    >
      <div className="grid grid-cols-[minmax(0,1fr)] gap-x-8 gap-y-6 md:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <figure className="m-0">
          <DieMap
            data={data}
            label={`Wafer map ${w.wafer_id}: ${n.pass + n.fail} dies, ${n.fail} failed.`}
            className="mx-auto max-w-[440px]"
          />
          <figcaption className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[12px] leading-4 text-ink-2">
            <span className="flex items-center gap-1.5">
              <span aria-hidden="true" className="size-2.5 rounded-[1px] bg-hairline-strong" />{" "}
              Passed ({formatInt(n.pass)})
            </span>
            <span className="flex items-center gap-1.5">
              <span aria-hidden="true" className="size-2.5 rounded-[1px] bg-fail" /> Failed (
              {formatInt(n.fail)})
            </span>
          </figcaption>
          <WaferAttribution
            attribution={detail.attribution}
            className="mt-2 text-[12px] leading-4"
          />
        </figure>
        <div className="min-w-0">
          <dl className="grid grid-cols-2 gap-x-6 gap-y-4">
            <Reading label="Recorded pattern" value={patternName(w.label as PatternLabel | null)} />
            <Reading
              label="Classifier reads"
              value={p ? patternName(p.top_label as PatternLabel) : "Not available"}
              detail={p ? formatPercent(p.top_probability) : undefined}
            />
          </dl>
          {p ? (
            <>
              <h3 className="mt-6 text-[13px] leading-5 text-ink-3">
                Calibrated probability of each pattern
              </h3>
              <ul
                className="mt-1.5 grid grid-cols-[minmax(0,1fr)] gap-1"
                aria-label="Pattern probabilities"
              >
                {p.probabilities.map((c) => (
                  <li
                    key={c.label}
                    className="grid grid-cols-[6.5rem_minmax(0,1fr)_3.5rem] items-center gap-2 text-[13px] leading-5"
                  >
                    <span className={cn(c.label === p.top_label ? "text-ink" : "text-ink-2")}>
                      {patternName(c.label as PatternLabel)}
                    </span>
                    <span className="h-2 rounded-[6px] bg-hairline">
                      <span
                        className={cn(
                          "block h-2 rounded-[6px]",
                          c.label === p.top_label ? "bg-ink" : "bg-ink-3",
                        )}
                        style={{ width: `${Math.max(0.5, c.probability * 100)}%` }}
                      />
                    </span>
                    <span className="tnum text-right text-ink-2">
                      {formatPercent(c.probability, c.probability < 0.1 ? 1 : 0)}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-[12px] leading-4 text-ink-3">
                Temperature {formatNumber(p.temperature)}. Model {p.model.name} {p.model.version}.
              </p>

              <h3 className="mt-6 text-[14px] leading-5 font-semibold text-ink">
                Like the training patterns?
              </h3>
              <p className="mt-1 text-[14px] leading-5 text-ink-2">
                {p.unknown.is_unknown
                  ? "No: the unknown-pattern score (Mahalanobis) is above the threshold, so the map is reported as an unknown pattern."
                  : "Yes: the unknown-pattern score (Mahalanobis) is below the threshold."}{" "}
                <span className="tnum text-ink-3">
                  Score {formatReading(p.unknown.score, 3)} against{" "}
                  {formatReading(p.unknown.threshold, 3)}, a threshold set on the validation set
                  that keeps {formatPercent(p.unknown.in_distribution_recall, 0)} of known patterns.
                  {p.unknown.energy_score != null
                    ? ` Energy score ${formatReading(p.unknown.energy_score, 3)}, a cross-check that does not set the flag.`
                    : ""}
                </span>
              </p>
            </>
          ) : (
            <p className="mt-6 text-[14px] leading-5 text-ink-3">
              No prediction: the wafer model is not loaded.
            </p>
          )}
          {s ? (
            <>
              <h3 className="mt-6 text-[14px] leading-5 font-semibold text-ink">
                Do the fail dies cluster?
              </h3>
              <p className="mt-1 text-[14px] leading-5 text-ink-2">
                {s.clustered ? "Yes." : "No evidence of clustering."}{" "}
                <span className="tnum text-ink-3">
                  Join count {formatReading(s.statistic, 3)} where chance gives{" "}
                  {formatReading(s.expected, 3)}; permutation p {formatPValue(s.p_value)} (
                  {formatInt(s.permutations)} permutations).
                </span>
              </p>
            </>
          ) : null}
        </div>
      </div>
    </Panel>
  );
}

function SimilarWafers({ waferId, onSelect }: { waferId: string; onSelect: (id: string) => void }) {
  const api = useApi();
  const similar = useQuery(q.similarWafers(api, waferId, 6));
  return (
    <Panel
      title="Most similar wafers"
      description={
        similar.data
          ? `${similar.data.method}. Similarity is the cosine of the embeddings.`
          : "Nearest maps by learned embedding."
      }
    >
      <QueryView
        query={similar}
        loading={<Placeholder className="h-40" label="Loading similar wafers" />}
      >
        {(s) =>
          s.results.length === 0 ? (
            <p className="text-[14px] text-ink-3">No similar wafers were found.</p>
          ) : (
            <ul className="grid grid-cols-3 gap-3 sm:grid-cols-6">
              {s.results.map((r) => (
                <SimilarItem
                  key={r.wafer.wafer_id}
                  wafer={r.wafer}
                  map={r.map}
                  similarity={r.similarity}
                  onSelect={onSelect}
                />
              ))}
            </ul>
          )
        }
      </QueryView>
    </Panel>
  );
}

function SimilarItem({
  wafer,
  map,
  similarity,
  onSelect,
}: {
  wafer: WaferSummary;
  map: WaferMap;
  similarity: number;
  onSelect: (id: string) => void;
}) {
  const data = useMemo(() => grid(map), [map]);
  return (
    <li>
      <button
        type="button"
        onClick={() => onSelect(wafer.wafer_id)}
        className="group w-full cursor-pointer text-left"
      >
        <DieMap
          data={data}
          label={`Wafer ${wafer.wafer_id}`}
          className="rounded-sm bg-surface-2 p-1 group-hover:outline group-hover:outline-1 group-hover:outline-hairline-strong"
        />
        <span className="tnum mt-1 block truncate text-[12px] leading-4 text-ink">
          {wafer.wafer_id}
        </span>
        <span className="tnum block text-[12px] leading-4 text-ink-3">
          {formatNumber(similarity)}, {patternName(wafer.label as PatternLabel | null)}
        </span>
      </button>
    </li>
  );
}

function PatternCauses({ label }: { label: PatternLabel }) {
  const api = useApi();
  const causes = useQuery(q.patternCauses(api, label));
  if (label === "none") return null;
  return (
    <Panel
      title={`What the literature links to ${patternName(label)} patterns`}
      description={causes.data?.framing}
    >
      <QueryView
        query={causes}
        loading={<Placeholder className="h-32" label="Loading the literature" />}
      >
        {(c) => {
          const sources = new Map(c.sources.map((s) => [s.source_id, s]));
          const list = c.causes.filter((x) => x.label === label);
          return list.length === 0 ? (
            <p className="text-[14px] text-ink-3">
              The literature index has nothing on this pattern yet.
            </p>
          ) : (
            <ul className="grid grid-cols-[minmax(0,1fr)] gap-4">
              {list.map((cause, i) => (
                <li key={i}>
                  <p className="written max-w-[66ch] text-ink">{cause.hypothesis}</p>
                  <p className="mt-0.5 text-[12px] text-ink-3">Confidence: {cause.confidence}</p>
                  <ul className="mt-2 grid grid-cols-[minmax(0,1fr)] gap-2">
                    {cause.quotes.map((quote, k) => {
                      const s = sources.get(quote.source_id);
                      return (
                        <li
                          key={k}
                          className="border-l-2 border-hairline-strong pl-3 text-[14px] leading-5 text-ink-2"
                        >
                          “{quote.quote}”
                          <span className="mt-0.5 block text-[12px] text-ink-3">
                            {s
                              ? `${s.authors.slice(0, 2).join(", ")}${s.authors.length > 2 ? " et al." : ""}${s.year ? ` (${s.year})` : ""}, ${s.title}`
                              : quote.source_id}
                            , {quote.location}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                </li>
              ))}
            </ul>
          );
        }}
      </QueryView>
    </Panel>
  );
}
