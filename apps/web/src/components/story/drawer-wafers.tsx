"use client";

import {
  decodeWaferCells,
  type FinalTestResult,
  type PatternCauses,
  type WaferMap,
} from "@yield-guardian/contracts";
import { useMemo } from "react";

import { DieMap, FrequencyLegend } from "@/components/wafer/die-map";
import { ScrollRegion } from "@/components/scroll-region";
import {
  ciLabel,
  formatInt,
  formatInterval,
  formatNumber,
  formatPercent,
  formatProbability,
  formatPValue,
  formatReading,
  plural,
} from "@/lib/format";
import { patternName } from "@/lib/labels";
import { defaultWafer } from "@/lib/live/rest";
import {
  stageResult,
  type LotItemView,
  type RunState,
  type WaferItem,
  type WaferPatternView,
  type WaferSimilarView,
} from "@/lib/live/run-state";
import { countsAsUnknown, energyUnknown, formatApart, testedLots } from "@/lib/live/stations";
import { cn } from "@/lib/utils";

import { DrawerSection, Method, NotYet } from "./drawer-parts";

type WaferStage = "wafer_pattern" | "wafer_similar" | "lot" | "final_test";

/** A map to draw; null until the full run has it (a reload draws it once read). */
function results(map: WaferMap | null) {
  if (!map) return null;
  return {
    kind: "results" as const,
    height: map.height,
    width: map.width,
    cells: decodeWaferCells(map),
  };
}

/**
 * The verdict on one wafer in plain words: the model's prediction, and next to it, never in its
 * place, the cautions that apply: the map is unlike the ones the model learned from (check it by
 * eye), and, once the lot test has covered its lot, the test counts it as unknown because its
 * energy score is above the test's threshold.
 */
export function waferVerdict(w: WaferItem, pattern: WaferPatternView, tested: boolean): string {
  const accept = pattern.accept_threshold;
  const name = w.top_label === "none" ? "No defect pattern" : patternName(w.top_label);
  const verdict = w.auto_accepted
    ? `${name} at ${formatProbability(w.top_probability)}, classified automatically (the 99%-precision threshold is ${formatProbability(accept)}).`
    : `${name} at ${formatProbability(w.top_probability)}, for review: below the ${formatProbability(accept)} needed to classify it automatically.`;
  const cautions = [
    w.is_unknown ? unknownCaution(w) : null,
    tested ? lotTestCaution(w, pattern) : null,
  ];
  return [verdict, ...cautions.filter(Boolean)].join(" ");
}

export function unknownCaution(w: WaferItem): string {
  return `The map looks unlike the maps the model learned from (unknown score ${formatReading(w.unknown_score)}, unknown from ${formatReading(w.unknown_threshold)}), so check it by eye.`;
}

/** Null unless the lot test counts the wafer as unknown rather than its predicted pattern. */
export function lotTestCaution(w: WaferItem, pattern: WaferPatternView): string | null {
  if (!countsAsUnknown(w, pattern)) return null;
  const [score, limit] = formatApart(w.energy_score, pattern.energy_threshold);
  return `The lot test counts it as unknown, not as ${patternName(w.top_label)}: its energy score ${score} is above the test's threshold ${limit}.`;
}

/**
 * Station 3 in detail: every wafer of the run (pick one), its map and what the model read in
 * it, the most similar real wafers, literature causes of the patterns found, and the lot test
 * with its stacked map.
 */
export function WafersDrawer({
  state,
  shown,
  wafer,
  onWafer,
}: {
  state: RunState;
  shown: (stage: WaferStage) => boolean;
  wafer: number | null;
  onWafer: (index: number) => void;
}) {
  const pattern = shown("wafer_pattern") ? stageResult(state, "wafer_pattern") : null;
  const similar = shown("wafer_similar") ? stageResult(state, "wafer_similar") : null;
  const lots = shown("lot") ? stageResult(state, "lot") : null;
  const final = shown("final_test") ? stageResult(state, "final_test") : null;
  if (!pattern) return <NotYet stage={state.stages.wafer_pattern} what="The wafer maps" />;
  // Without a wafer chosen, the drawer opens on the first wafer with a pattern (known or not).
  const index = wafer != null && wafer < pattern.wafers.length ? wafer : defaultWafer(pattern);
  const chosen = index != null ? pattern.wafers[index]! : null;
  const tested = testedLots(lots);

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-8">
      <DrawerSection
        title="Every wafer of the run"
        description="Choose a wafer to see what the model read in its map."
      >
        <WaferChooser pattern={pattern} tested={tested} selected={index} onSelect={onWafer} />
      </DrawerSection>
      {chosen ? (
        <WaferDetail
          wafer={chosen}
          pattern={pattern}
          tested={tested.has(chosen.lot)}
          similar={similar}
          final={final}
          stageSimilar={state.stages.wafer_similar}
        />
      ) : (
        <p className="text-[14px] text-ink-2">Choose a wafer above.</p>
      )}
      {similar ? <Causes causes={similar.causes} focus={chosen?.top_label ?? null} /> : null}
      {lots ? (
        lots.lots.map((l) => (
          <LotPanel key={l.lot} lot={l} method={lots.method} energy={energyUnknown(pattern, l)} />
        ))
      ) : (
        <NotYet stage={state.stages.lot} what="The lot test" />
      )}
    </div>
  );
}

function WaferChooser({
  pattern,
  tested,
  selected,
  onSelect,
}: {
  pattern: WaferPatternView;
  /** Lots the lot test covered: their wafers show how the test counted them. */
  tested: ReadonlySet<string>;
  selected: number | null;
  onSelect: (i: number) => void;
}) {
  const maps = useMemo(() => pattern.wafers.map((w) => results(w.map)), [pattern]);
  return (
    <ul className="grid grid-cols-[repeat(auto-fill,minmax(72px,1fr))] gap-2" aria-label="Wafers">
      {pattern.wafers.map((w, i) => {
        const label = w.top_label === "none" ? "no pattern" : patternName(w.top_label);
        const uncounted = tested.has(w.lot) && countsAsUnknown(w, pattern);
        return (
          <li key={w.index}>
            <button
              type="button"
              aria-pressed={selected === i}
              onClick={() => onSelect(i)}
              className={cn(
                "flex w-full flex-col items-center gap-1 rounded-[4px] p-1.5 hover:bg-die-2",
                selected === i && "lit",
              )}
            >
              <span
                className={cn(
                  "block w-full rounded-full",
                  w.is_unknown && "outline-1 outline-offset-1 outline-ink-3 outline-dashed",
                )}
              >
                <DieMap
                  data={maps[i] ?? null}
                  label={`Wafer ${w.wafer} of ${w.lot}`}
                  className="rounded-full"
                />
              </span>
              <span className="tnum text-[12px] leading-4 text-ink">{`Wafer ${w.wafer}`}</span>
              <span
                className={cn(
                  "text-[11px] leading-4",
                  w.top_label === "none" ? "text-ink-3" : uncounted ? "text-ink-2" : "text-fail",
                )}
              >
                {label}
              </span>
              {uncounted ? (
                <span className="text-[11px] leading-4 text-ink-3">lot test: unknown</span>
              ) : null}
              {w.is_unknown ? (
                <span className="text-[11px] leading-4 text-ink-3">check by eye</span>
              ) : null}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function WaferDetail({
  wafer,
  pattern,
  tested,
  similar,
  final,
  stageSimilar,
}: {
  wafer: WaferItem;
  pattern: WaferPatternView;
  /** Whether the lot test covered the wafer's lot (and its result is shown). */
  tested: boolean;
  similar: WaferSimilarView | null;
  final: FinalTestResult | null;
  stageSimilar: RunState["stages"]["wafer_similar"];
}) {
  const data = useMemo(() => results(wafer.map), [wafer]);
  // Counted on the map. The page's first paint carries the map of the wafer it shows; another
  // one chosen before the full run is read is counted once it is.
  const counted = useMemo(() => {
    if (!data) return null;
    const fails = data.cells.reduce((n, v) => n + (v === 2 ? 1 : 0), 0);
    const dies = data.cells.reduce((n, v) => n + (v !== 0 ? 1 : 0), 0);
    return `${formatInt(fails)} of ${formatInt(dies)} dies failed`;
  }, [data]);
  const probs = [...(wafer.probabilities ?? [])].sort((a, b) => b.probability - a.probability);
  const recorded = final?.wafers.find((w) => w.index === wafer.index);
  const neighbours = similar?.wafers.find((w) => w.index === wafer.index)?.similar ?? [];
  const drawn = wafer.source_wafer == null;
  const unknownPos = Math.min(1, wafer.unknown_score / (wafer.unknown_threshold * 2));
  const energy = formatApart(wafer.energy_score, pattern.energy_threshold);

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-8 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
      <div className="min-w-0">
        <DieMap
          data={data}
          label={`Wafer ${wafer.wafer} of ${wafer.lot}${counted ? `: ${counted}` : ""}`}
          className="max-w-[340px] rounded-full"
        />
        <p className="tnum mt-2 text-[13px] leading-5 text-ink-2">
          {`${drawn ? "Your drawing" : wafer.source_wafer}: wafer ${wafer.wafer} of ${wafer.lot}${counted ? `, ${counted}` : ""}.`}
        </p>
      </div>
      <DrawerSection
        title={wafer.top_label === "none" ? "No defect pattern" : patternName(wafer.top_label)}
        description={waferVerdict(wafer, pattern, tested)}
      >
        {recorded ? (
          <p className="mb-3 text-[14px] leading-5 text-ink">
            {`Recorded in WM-811K as ${patternName(recorded.recorded_label)}: the model ${recorded.agrees ? "agrees" : `read ${patternName(recorded.predicted_label)}`}.`}
          </p>
        ) : null}
        <h4 className="text-[14px] leading-5 font-semibold text-ink">Pattern probabilities</h4>
        <ul className="mt-1.5 grid grid-cols-[minmax(0,1fr)] gap-0.5">
          {probs.map((p) => (
            <li
              key={p.label}
              className="tnum grid grid-cols-[88px_minmax(0,1fr)_56px] items-center gap-2 text-[12px] leading-5"
            >
              <span className="text-ink">{patternName(p.label)}</span>
              <span className="relative h-2.5 rounded-[1px] bg-hairline" aria-hidden="true">
                <span
                  className={cn(
                    "absolute inset-y-0 left-0 rounded-[1px]",
                    p.label === wafer.top_label ? "bg-ink" : "bg-ink-3",
                  )}
                  style={{ width: `${p.probability * 100}%` }}
                />
              </span>
              <span className="text-right text-ink-2">{formatProbability(p.probability)}</span>
            </li>
          ))}
        </ul>

        <h4 className="mt-5 text-[14px] leading-5 font-semibold text-ink">Unknown score</h4>
        <div className="relative mt-2 h-5" aria-hidden="true">
          <div className="absolute inset-x-0 top-2 h-1 rounded-full bg-hairline" />
          <div className="absolute top-2 right-0 left-1/2 h-1 rounded-r-full bg-ink-3/50" />
          <div className="absolute top-0 left-1/2 h-5 w-px bg-ink-2" />
          <div
            className="absolute top-0.5 size-4 -translate-x-1/2 rounded-full border-2 border-ink bg-die"
            style={{ left: `${unknownPos * 100}%` }}
          />
        </div>
        <p className="tnum text-[12px] leading-4 text-ink-3">
          {`${formatReading(wafer.unknown_score)} against ${formatReading(wafer.unknown_threshold)}, the score above which a map counts as unknown (the scale ends at twice it). Energy score ${energy[0]}, a cross-check; the lot test counts a map as unknown above ${energy[1]}.`}
        </p>

        <h4 className="mt-5 text-[14px] leading-5 font-semibold text-ink">
          Do the failing dies cluster?
        </h4>
        <p className="text-[14px] leading-5 text-ink-2">
          {wafer.spatial
            ? `${wafer.spatial.clustered ? "Yes" : "Not beyond chance"}: ${formatInt(wafer.spatial.statistic)} neighbouring pairs of failing dies against ${formatNumber(wafer.spatial.expected, 1)} expected at random (p ${formatPValue(wafer.spatial.p_value)}, ${formatInt(wafer.spatial.permutations)} permutations).`
            : "Not tested: the map has too few failing dies for a join-count test."}
        </p>
      </DrawerSection>

      <div className="min-w-0 lg:col-span-2">
        {similar ? (
          <DrawerSection
            title="The most similar real wafers"
            description={`Nearest of the ${formatInt(similar.searched)} WM-811K demo wafers by the model's embedding.${
              similar.precision_at_10
                ? ` On held-out wafers, ${formatPercent(similar.precision_at_10.value, 0)} of the ten nearest share the pattern${formatInterval(similar.precision_at_10, "percent") ? ` (${ciLabel(similar.precision_at_10)} ${formatInterval(similar.precision_at_10, "percent")})` : ""}.`
                : ""
            }`}
          >
            <ul className="grid grid-cols-[repeat(auto-fill,minmax(96px,1fr))] gap-3">
              {neighbours.map((s) => (
                <li key={s.wafer_id} className="min-w-0">
                  <DieMap
                    data={results(s.map)}
                    label={`${s.wafer_id}, ${patternName(s.recorded_label)}`}
                    className="rounded-full"
                  />
                  <p className="tnum mt-1 truncate text-[12px] leading-4 text-ink">{s.wafer_id}</p>
                  <p className="tnum text-[11px] leading-4 text-ink-3">{`${formatNumber(s.similarity, 3)} similar`}</p>
                  <p className="text-[11px] leading-4 text-ink-2">
                    {s.recorded_label
                      ? `recorded ${patternName(s.recorded_label)}`
                      : `read as ${patternName(s.predicted_label)}`}
                  </p>
                </li>
              ))}
            </ul>
            <Method>{similar.method}</Method>
          </DrawerSection>
        ) : (
          <NotYet stage={stageSimilar} what="The similar wafers" />
        )}
      </div>
      <div className="lg:col-span-2">
        <Method>{pattern.method}</Method>
      </div>
    </div>
  );
}

function Causes({ causes, focus }: { causes: PatternCauses; focus: string | null }) {
  const sources = new Map(causes.sources.map((s) => [s.source_id, s]));
  const list = [...causes.causes].sort(
    (a, b) => Number(b.label === focus) - Number(a.label === focus),
  );
  if (!list.length) return null;
  return (
    <DrawerSection
      title="What the literature associates with these patterns"
      description={causes.framing}
    >
      <ul className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-2">
        {list.map((c, k) => (
          <li
            key={`${c.label}-${k}`}
            className={cn(
              "min-w-0 border-t border-hairline pt-2",
              c.label === focus && "border-ink-3",
            )}
          >
            <p className="text-[14px] leading-5 text-ink">
              <span className="font-semibold">{patternName(c.label)}</span>
              <span className="text-ink-3">{`, ${c.confidence} confidence`}</span>
            </p>
            <p className="text-[14px] leading-5 text-ink-2">{c.hypothesis}</p>
            <ul className="mt-1.5 grid grid-cols-[minmax(0,1fr)] gap-1.5">
              {c.quotes.map((q, i) => {
                const src = sources.get(q.source_id);
                const href = src?.url ?? (src?.doi ? `https://doi.org/${src.doi}` : null);
                return (
                  <li key={i} className="text-[12px] leading-4 text-ink-3">
                    <q className="text-ink-2">{q.quote}</q>{" "}
                    {src ? (
                      href ? (
                        <a
                          href={href}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="underline underline-offset-2 hover:text-ink"
                        >
                          {`${src.authors[0]?.split(" ").at(-1) ?? src.source_id}${src.authors.length > 1 ? " et al." : ""} ${src.year ?? ""}`.trim()}
                        </a>
                      ) : (
                        <span>{src.title}</span>
                      )
                    ) : (
                      <span>{q.source_id}</span>
                    )}
                    {`, ${q.location}`}
                  </li>
                );
              })}
            </ul>
          </li>
        ))}
      </ul>
    </DrawerSection>
  );
}

function LotPanel({ lot, method, energy }: { lot: LotItemView; method: string; energy: number }) {
  const stacked = lot.stacked;
  const frequencies = stacked?.frequencies ?? null;
  // The highest share sets the legend: the page's first paint carries it without the map.
  const max = stacked
    ? Math.max(
        0.05,
        stacked.peak ?? 0,
        ...(frequencies ?? []).filter((v): v is number => v != null),
      )
    : 1;
  const tests = [...lot.tests].sort((a, b) => a.q_value - b.q_value);
  return (
    <DrawerSection
      title={`Lot ${lot.lot}`}
      description={`${plural(lot.wafers, "wafer")}. ${lot.flagged ? "A pattern repeats across the lot more often than chance." : "No pattern repeats more often than chance."}${
        energy
          ? ` ${energy === 1 ? "1 wafer with a predicted pattern counts" : `${formatInt(energy)} wafers with a predicted pattern count`} as unknown in this test: ${energy === 1 ? "its" : "their"} energy score is above the test's threshold.`
          : ""
      }`}
    >
      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,300px)_minmax(0,1fr)]">
        <div className="min-w-0">
          {stacked ? (
            <>
              <DieMap
                data={
                  frequencies
                    ? {
                        kind: "frequency",
                        height: stacked.height,
                        width: stacked.width,
                        values: frequencies,
                      }
                    : null
                }
                max={max}
                label={`Stacked failure map of ${lot.lot}: the share of its ${stacked.wafers} wafers that failed at each die`}
                className="max-w-[300px] rounded-full"
              />
              <FrequencyLegend max={max} className="mt-2 max-w-[300px]" />
            </>
          ) : (
            <p className="text-[13px] leading-5 text-ink-3">
              No stacked map: the lot&apos;s wafers are not all the same size.
            </p>
          )}
        </div>
        <ScrollRegion label={`Pattern tests of ${lot.lot}`}>
          <table className="w-full min-w-[440px] text-left text-[13px] leading-5">
            <caption className="sr-only">{`Pattern tests of ${lot.lot}`}</caption>
            <thead className="text-ink-3">
              <tr>
                <th scope="col" className="py-1 pr-3 font-normal">
                  Pattern
                </th>
                <th scope="col" className="py-1 pr-3 text-right font-normal">
                  Wafers
                </th>
                <th scope="col" className="py-1 pr-3 text-right font-normal">
                  Expected rate
                </th>
                <th scope="col" className="py-1 pr-3 text-right font-normal">
                  p
                </th>
                <th scope="col" className="py-1 text-right font-normal">
                  q
                </th>
              </tr>
            </thead>
            <tbody className="tnum">
              {tests.map((t) => (
                <tr
                  key={t.label}
                  className={cn("border-t border-hairline", t.flagged && "text-fail")}
                >
                  <td className="py-1 pr-3">
                    {patternName(t.label)}
                    {t.flagged ? <span className="sr-only">, repeats beyond chance</span> : null}
                  </td>
                  <td className="py-1 pr-3 text-right">{`${formatInt(t.count)} of ${formatInt(t.wafers)}`}</td>
                  <td className="py-1 pr-3 text-right">{formatPercent(t.expected_rate)}</td>
                  <td className="py-1 pr-3 text-right">{formatPValue(t.p_value)}</td>
                  <td className="py-1 text-right">{formatPValue(t.q_value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollRegion>
      </div>
      <Method>{method}</Method>
    </DrawerSection>
  );
}
