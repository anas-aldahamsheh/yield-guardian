"use client";

import { useQuery } from "@tanstack/react-query";
import type { SplitResult, WaferMetrics } from "@yield-guardian/contracts";
import { useState } from "react";

import { EstimateText, IntervalMark } from "@/components/charts/interval";
import { Panel, Reading } from "@/components/page";
import { Placeholder, QueryView } from "@/components/states";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useApi } from "@/lib/api/context";
import { q } from "@/lib/api/queries";
import { formatInt, formatNumber, formatPercent } from "@/lib/format";
import { type PatternLabel, patternName } from "@/lib/labels";

import { ConfusionMatrix } from "./charts";
import { EstimateFootnote, Limitations } from "./secom-methods";
import { ScrollRegion } from "@/components/scroll-region";

const SPLIT_NAME: Record<SplitResult["split"], string> = {
  official: "Official split",
  lot_grouped: "Lot-grouped split",
};

/** "<mean> ± <sd> over <n> seeds", or "single fit" when the API gives no seed spread. */
export function seedText(s: SplitResult): string {
  if (s.seed_mean == null || s.seed_sd == null) return "single fit";
  return `${formatNumber(s.seed_mean, 3)} ± ${formatNumber(s.seed_sd, 3)} over ${s.seeds.length} ${s.seeds.length === 1 ? "seed" : "seeds"}`;
}

export function WaferMethods() {
  const api = useApi();
  const metrics = useQuery(q.waferMetrics(api));
  return (
    <QueryView query={metrics} loading={<Placeholder className="h-[480px]" label="Loading wafer-map methods" />}>
      {(m) => <WaferContent metrics={m} />}
    </QueryView>
  );
}

function WaferContent({ metrics }: { metrics: WaferMetrics }) {
  const [split, setSplit] = useState<SplitResult["split"]>(metrics.splits[0]?.split ?? "official");
  const current = metrics.splits.find((s) => s.split === split);
  const rows = [
    ...metrics.splits.map((s) => ({ key: `cnn-${s.split}`, model: "CNN", s })),
    ...metrics.baseline.map((s) => ({ key: `base-${s.split}`, model: "Baseline", s })),
  ];
  const ood = metrics.ood;

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-street">
      <Panel
        title="Pattern classifier on held-out wafers"
        description="The lot-grouped split keeps every lot on one side, so wafers from the same lot never sit in both training and test data."
        bodyClassName="px-0 sm:px-0"
      >
        <ScrollRegion label="Macro-F1 by split">
          <table className="w-full min-w-[720px] border-collapse text-left text-[13px] leading-5">
            <caption className="sr-only">Macro-F1 by split</caption>
            <thead>
              <tr className="border-y border-hairline text-[12px] text-ink-3">
                <th scope="col" className="px-4 py-2 font-normal sm:px-5">Model and split</th>
                <th scope="col" className="px-3 py-2 text-right font-normal">Test wafers</th>
                <th scope="col" className="w-[28%] px-3 py-2 font-normal">Macro-F1</th>
                <th scope="col" className="px-3 py-2 font-normal">Accuracy</th>
                <th scope="col" className="px-4 py-2 text-right font-normal sm:px-5">Lots in both</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ key, model, s }) => (
                <tr key={key} className="border-b border-hairline last:border-b-0 align-top">
                  <th scope="row" className="px-4 py-2.5 font-normal sm:px-5">
                    <span className={model === "CNN" ? "font-medium text-ink" : "text-ink-2"}>{model}</span>
                    <span className="block text-[12px] text-ink-3">{SPLIT_NAME[s.split]}</span>
                  </th>
                  <td className="tnum px-3 py-2.5 text-right text-ink-2">{formatInt(s.test_wafers)}</td>
                  <td className="px-3 py-2.5">
                    <IntervalMark estimate={s.macro_f1} />
                    <span className="mt-0.5 block text-[12px]">
                      <EstimateText estimate={s.macro_f1} digits={3} />
                    </span>
                    {s.seed_mean != null && s.seed_sd != null ? (
                      <span className="tnum mt-0.5 block text-[12px] text-ink">
                        Mean across seeds {seedText(s)}
                      </span>
                    ) : null}
                  </td>
                  <td className="px-3 py-2.5 text-[12px]">{s.accuracy ? <EstimateText estimate={s.accuracy} digits={3} /> : <span className="text-ink-3">Not measured yet</span>}</td>
                  <td className="tnum px-4 py-2.5 text-right text-ink-2 sm:px-5">{s.lots_in_both == null ? "–" : formatInt(s.lots_in_both)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollRegion>
        <EstimateFootnote estimate={metrics.splits[0]?.macro_f1} />
      </Panel>

      {current ? (
        <Panel
          title="Per pattern"
          description="Precision, recall and F1 for each pattern, with the confusion matrix of the same split."
          actions={
            metrics.splits.length > 1 ? (
              <ToggleGroup type="single" variant="outline" size="sm" value={split} onValueChange={(v) => v && setSplit(v as SplitResult["split"])} aria-label="Split">
                {metrics.splits.map((s) => (
                  <ToggleGroupItem key={s.split} value={s.split} className="px-2.5">
                    {SPLIT_NAME[s.split]}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            ) : null
          }
        >
          <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,1fr)_auto]">
            <ScrollRegion label="Per-pattern metrics">
              <table className="w-full min-w-[560px] border-collapse text-left text-[12px] leading-5">
                <caption className="sr-only">Per-pattern metrics, {SPLIT_NAME[split]}</caption>
                <thead>
                  <tr className="border-b border-hairline text-ink-3">
                    <th scope="col" className="py-1.5 pr-3 font-normal">Pattern</th>
                    <th scope="col" className="py-1.5 pr-3 text-right font-normal">Support</th>
                    <th scope="col" className="py-1.5 pr-3 font-normal">Precision</th>
                    <th scope="col" className="py-1.5 pr-3 font-normal">Recall</th>
                    <th scope="col" className="py-1.5 font-normal">F1</th>
                  </tr>
                </thead>
                <tbody>
                  {current.per_class.map((c) => (
                    <tr key={c.label} className="border-b border-hairline last:border-b-0">
                      <th scope="row" className="py-1.5 pr-3 font-normal text-ink">{patternName(c.label as PatternLabel)}</th>
                      <td className="tnum py-1.5 pr-3 text-right text-ink-2">{formatInt(c.support)}</td>
                      <td className="py-1.5 pr-3"><EstimateText estimate={c.precision} /></td>
                      <td className="py-1.5 pr-3"><EstimateText estimate={c.recall} /></td>
                      <td className="py-1.5">
                        <IntervalMark estimate={c.f1} className="max-w-[140px]" />
                        <EstimateText estimate={c.f1} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </ScrollRegion>
            <ConfusionMatrix matrix={current.confusion} />
          </div>
        </Panel>
      ) : null}

      <div className="grid grid-cols-[minmax(0,1fr)] gap-street xl:grid-cols-2">
        <Panel title="Unknown-pattern score (Mahalanobis)" description={ood.note}>
          <dl className="grid grid-cols-2 gap-4">
            <Reading
              label={`Threshold, set on the ${ood.threshold_set_on} set`}
              value={formatNumber(ood.threshold, 1)}
            />
            <Reading
              label="Known patterns kept"
              value={formatPercent(ood.in_distribution_recall)}
              detail={ood.in_distribution_recall_test != null ? `validation; ${formatPercent(ood.in_distribution_recall_test)} on test` : "validation"}
            />
            <Reading label="Mean AUROC, class held out" value={ood.mean_auroc ? <EstimateText estimate={ood.mean_auroc} digits={3} /> : "Not measured yet"} />
            <Reading
              label="Energy score, cross-check only"
              value={ood.energy_mean_auroc ? <EstimateText estimate={ood.energy_mean_auroc} digits={3} /> : "Not measured yet"}
            />
          </dl>
          {ood.leave_one_class_out.length ? (
            <>
              <h3 className="mt-5 text-[13px] leading-5 text-ink-3">AUROC when each pattern is left out of training</h3>
              <ul className="mt-1.5 grid grid-cols-[minmax(0,1fr)] gap-1.5">
                {ood.leave_one_class_out.map((l) => (
                  <li key={l.held_out} className="grid grid-cols-[6.5rem_minmax(0,1fr)_auto] items-center gap-3 text-[12px] leading-4">
                    <span className="text-ink">{patternName(l.held_out as PatternLabel)}</span>
                    <IntervalMark estimate={l.auroc} domain={[0.5, 1]} />
                    <EstimateText estimate={l.auroc} digits={2} />
                  </li>
                ))}
              </ul>
              <p className="mt-1.5 text-[12px] leading-4 text-ink-3">Axis from 0.5 (chance) to 1.</p>
            </>
          ) : null}
        </Panel>

        <Panel title="Calibration, retrieval and automation">
          <dl className="grid grid-cols-2 gap-4">
            <Reading label={`Temperature (${metrics.calibration.method} scaling)`} value={formatNumber(metrics.calibration.temperature, 2)} />
            <Reading
              label="Expected calibration error"
              value={<EstimateText estimate={metrics.calibration.ece_after} digits={3} />}
              detail={`before: ${formatNumber(metrics.calibration.ece_before.value, 3)}`}
            />
            <Reading label="Similar-wafer precision at 10" value={<EstimateText estimate={metrics.similarity_precision_at_10} format="percent" />} />
          </dl>
          <h3 className="mt-5 text-[13px] leading-5 font-medium text-ink">Classified automatically at a precision target</h3>
          {metrics.auto_classification.length ? (
            <table className="mt-1.5 w-full border-collapse text-left text-[12px] leading-5">
              <caption className="sr-only">Automatic classification by precision target</caption>
              <thead>
                <tr className="border-b border-hairline text-ink-3">
                  <th scope="col" className="py-1 pr-3 font-normal">Target</th>
                  <th scope="col" className="py-1 pr-3 font-normal">Confidence above</th>
                  <th scope="col" className="py-1 pr-3 font-normal">Share of wafers</th>
                  <th scope="col" className="py-1 font-normal">Precision reached</th>
                </tr>
              </thead>
              <tbody>
                {[...metrics.auto_classification]
                  .sort((a, b) => a.precision_target - b.precision_target)
                  .map((a) => (
                    <tr key={a.precision_target} className="border-b border-hairline last:border-b-0">
                      <th scope="row" className="tnum py-1.5 pr-3 font-normal text-ink">{formatPercent(a.precision_target, 0)}</th>
                      <td className="tnum py-1.5 pr-3 text-ink-2">{formatNumber(a.confidence_threshold, 2)}</td>
                      <td className="py-1.5 pr-3"><EstimateText estimate={a.share} format="percent" /></td>
                      <td className="py-1.5"><EstimateText estimate={a.precision} digits={3} /></td>
                    </tr>
                  ))}
              </tbody>
            </table>
          ) : (
            <p className="mt-1 text-[13px] text-ink-3">Not measured yet.</p>
          )}
          {metrics.published.length ? (
            <>
              <h3 className="mt-5 text-[13px] leading-5 font-medium text-ink">Published results on WM-811K</h3>
              <p className="text-[12px] leading-4 text-ink-3">Reported by their authors on their own splits, so not directly comparable.</p>
              <ul className="mt-1.5 grid grid-cols-[minmax(0,1fr)] gap-1.5 text-[12px] leading-4">
                {metrics.published.map((p, i) => (
                  <li key={i}>
                    <span className="text-ink">{p.source}</span>: <span className="tnum">{p.metric} {formatNumber(p.value, 3)}</span>
                    {p.note ? <span className="block text-ink-3">{p.note}</span> : null}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </Panel>
      </div>

      <Limitations items={metrics.limitations} title="Wafer-map limitations" />
    </div>
  );
}
