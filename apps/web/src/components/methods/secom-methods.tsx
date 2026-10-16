"use client";

import { useQuery } from "@tanstack/react-query";
import type {
  Estimate,
  ModelResult,
  OperatingPoints,
  SecomMetrics,
} from "@yield-guardian/contracts";

import { EstimateText, IntervalMark } from "@/components/charts/interval";
import { Panel, Reading } from "@/components/page";
import { Placeholder, QueryView } from "@/components/states";
import { useApi } from "@/lib/api/context";
import { q } from "@/lib/api/queries";
import { formatInt, formatNumber, formatPValue, formatSigned } from "@/lib/format";
import { cn } from "@/lib/utils";

import { BlocksBar, PrCurve, ReliabilityDiagram } from "./charts";
import { Limitations } from "./limitations";
import { ScrollRegion } from "@/components/scroll-region";

const metricOf = (m: ModelResult, id: string) => m.metrics.find((x) => x.metric === id)?.estimate;

/** Axis for a metric column: probabilities on 0 to 1, Brier on its own small range. */
function domainFor(metric: string, models: ModelResult[]): [number, number] {
  if (metric === "brier" || metric === "ece") {
    const top = Math.max(
      0.01,
      ...models.map((m) => metricOf(m, metric)?.ci_high ?? metricOf(m, metric)?.value ?? 0),
    );
    return [0, top * 1.15];
  }
  return [0, 1];
}

/**
 * The plain-language reading of the SECOM comparison, computed from the API's numbers: which
 * model ranks failures best on PR-AUC, and how far that is from no skill.
 */
export function secomReading(metrics: SecomMetrics): string | null {
  const scored = metrics.models
    .map((m) => ({ m, v: metricOf(m, "pr_auc")?.value }))
    .filter((x): x is { m: ModelResult; v: number } => x.v != null);
  const main = scored.find((x) => x.m.main);
  const noSkill = scored.find((x) => x.m.model === "prevalence");
  const best = scored.filter((x) => x.m.model !== "prevalence").sort((a, b) => b.v - a.v)[0];
  if (!main || !best) return null;
  const parts: string[] = [];
  if (best.m.model !== main.m.model) {
    parts.push(
      `On PR-AUC the ${best.m.label} scores higher than the main model (${formatNumber(best.v, 3)} against ${formatNumber(main.v, 3)}).`,
    );
  } else {
    parts.push(`The main model has the highest PR-AUC, ${formatNumber(main.v, 3)}.`);
  }
  if (noSkill)
    parts.push(
      `No skill scores ${formatNumber(noSkill.v, 3)}, the failure rate of the test block.`,
    );
  parts.push(
    "The failure-risk score is therefore shown as an experimental signal, not as a prediction to act on alone.",
  );
  return parts.join(" ");
}

export function SecomMethods() {
  const api = useApi();
  const metrics = useQuery(q.secomMetrics(api));
  const points = useQuery(q.operatingPoints(api));
  return (
    <QueryView
      query={metrics}
      loading={<Placeholder className="h-[480px]" label="Loading SECOM methods" />}
    >
      {(m) => <SecomContent metrics={m} points={points.data} pointsError={points.isError} />}
    </QueryView>
  );
}

function SecomContent({
  metrics,
  points,
  pointsError,
}: {
  metrics: SecomMetrics;
  points?: OperatingPoints;
  pointsError: boolean;
}) {
  const reading = secomReading(metrics);
  const metricIds = [...new Set(metrics.models.flatMap((m) => m.metrics.map((x) => x.metric)))];
  const labels = Object.fromEntries(
    metrics.models.flatMap((m) => m.metrics.map((x) => [x.metric, x.label])),
  );
  const modelLabel = Object.fromEntries(metrics.models.map((m) => [m.model, m.label]));
  const noSkill = metrics.models.find((m) => m.model === "prevalence");

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-street">
      <Panel
        title="How the units were split"
        description="By time, never shuffled: the model is fitted on the past and tested on the future."
      >
        <BlocksBar blocks={metrics.blocks} />
      </Panel>

      <Panel
        title="Failure-risk models on the test block"
        description="Each point is the estimate; the bar is its confidence interval. The vertical rule in the PR-AUC column is no skill."
        bodyClassName="px-0 sm:px-0"
      >
        {reading ? (
          <p className="mx-4 mb-4 max-w-[90ch] rounded-sm border-l-2 border-signal bg-surface-2 px-3 py-2 text-[14px] leading-6 text-ink sm:mx-5">
            {reading}
          </p>
        ) : null}
        <ScrollRegion label="SECOM model metrics">
          <table className="w-full min-w-[720px] border-collapse text-left text-[13px] leading-5">
            <caption className="sr-only">SECOM model metrics with confidence intervals</caption>
            <thead>
              <tr className="border-y border-hairline text-[12.5px] leading-4 text-ink-3">
                <th scope="col" className="px-5 py-3 font-[520] sm:px-6">
                  Model
                </th>
                {metricIds.map((id) => (
                  <th key={id} scope="col" className="px-3 py-3 font-[520]">
                    {labels[id]}
                    {id === "brier" ? " (lower is better)" : ""}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {metrics.models.map((model) => (
                <tr
                  key={model.model}
                  className={cn(
                    "border-b border-hairline last:border-b-0",
                    model.main && "bg-surface-2",
                  )}
                >
                  <th scope="row" className="px-5 py-3 align-top font-[420] sm:px-6">
                    <span className={model.main ? "font-[560] text-ink" : "text-ink-2"}>
                      {model.label}
                    </span>
                    {model.main ? (
                      <span className="block text-[12px] text-ink-3">
                        Main model, behind the line&rsquo;s risk trace
                      </span>
                    ) : null}
                  </th>
                  {metricIds.map((id) => {
                    const e = metricOf(model, id);
                    return (
                      <td key={id} className="px-3 py-3 align-top">
                        {e ? (
                          <>
                            <IntervalMark
                              estimate={e}
                              domain={domainFor(id, metrics.models)}
                              reference={
                                id === "pr_auc" && noSkill
                                  ? metricOf(noSkill, "pr_auc")?.value
                                  : id === "roc_auc"
                                    ? 0.5
                                    : null
                              }
                            />
                            <span className="mt-0.5 block text-[12px]">
                              <EstimateText
                                estimate={e}
                                digits={id === "brier" || id === "ece" ? 3 : 2}
                              />
                            </span>
                          </>
                        ) : (
                          <span className="text-ink-3">Not measured yet</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollRegion>
        <EstimateFootnote estimate={metricOf(metrics.models[0]!, metricIds[0] ?? "pr_auc")} />
      </Panel>

      {metrics.comparisons.length ? (
        <Panel
          title="Main model against each baseline"
          description="Paired on the same test units: main model minus baseline."
          bodyClassName="px-0 sm:px-0"
        >
          <ScrollRegion label="Paired comparisons">
            <table className="w-full min-w-[560px] border-collapse text-left text-[13px] leading-5">
              <caption className="sr-only">Paired comparisons</caption>
              <thead>
                <tr className="border-y border-hairline text-[12.5px] leading-4 text-ink-3">
                  <th scope="col" className="px-5 py-3 font-[520] sm:px-6">
                    Baseline
                  </th>
                  <th scope="col" className="px-3 py-3 font-[520]">
                    Metric
                  </th>
                  <th scope="col" className="px-3 py-3 font-[520]">
                    Difference
                  </th>
                  <th scope="col" className="px-5 py-3 text-right font-[520] sm:px-6">
                    p
                  </th>
                </tr>
              </thead>
              <tbody>
                {metrics.comparisons.map((c) => (
                  <tr
                    key={`${c.baseline}-${c.metric}`}
                    className="border-b border-hairline last:border-b-0"
                  >
                    <th scope="row" className="px-5 py-2.5 font-[420] text-ink sm:px-6">
                      {modelLabel[c.baseline] ?? c.baseline}
                    </th>
                    <td className="px-3 py-2.5 text-ink-2">{labels[c.metric] ?? c.metric}</td>
                    <td className="tnum px-3 py-2.5">
                      <span className="text-ink">{formatSigned(c.difference.value, 3)}</span>
                      {c.difference.ci_low != null && c.difference.ci_high != null ? (
                        <span className="text-ink-3">
                          {" "}
                          {Math.round((c.difference.ci_level ?? 0.95) * 100)}% CI{" "}
                          {formatSigned(c.difference.ci_low, 3)} to{" "}
                          {formatSigned(c.difference.ci_high, 3)}
                          {c.difference.ci_low <= 0 && c.difference.ci_high >= 0
                            ? ", includes no difference"
                            : ""}
                        </span>
                      ) : null}
                    </td>
                    <td className="tnum px-5 py-2.5 text-right text-ink sm:px-6">
                      {formatPValue(c.p_value)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollRegion>
          <EstimateFootnote estimate={metrics.comparisons[0]?.difference} />
        </Panel>
      ) : null}

      <div className="grid grid-cols-[minmax(0,1fr)] gap-street xl:grid-cols-2">
        <Panel
          title="Operating points"
          description="Thresholds chosen on the validation block, measured once on the test block."
        >
          {pointsError ? (
            <p className="text-[14px] text-ink-3">The operating points could not be loaded.</p>
          ) : !points ? (
            <Placeholder className="h-72" label="Loading operating points" />
          ) : (
            <OperatingPointsView data={points} />
          )}
        </Panel>
        <Panel
          title="Calibration"
          description={`Platt scaling, fitted on validation: a = ${formatNumber(metrics.calibration.a, 3)}, b = ${formatNumber(metrics.calibration.b, 3)}.`}
        >
          <ReliabilityDiagram bins={metrics.calibration.bins} />
          <dl className="mt-3 grid grid-cols-2 gap-4">
            <Reading
              label="Brier score"
              value={<EstimateText estimate={metrics.calibration.brier} digits={3} />}
            />
            <Reading
              label="Expected calibration error"
              value={<EstimateText estimate={metrics.calibration.ece} digits={3} />}
            />
          </dl>
          <p className="mt-3 text-[13px] leading-5 text-ink-3">{metrics.calibration.caveat}</p>
        </Panel>
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-street xl:grid-cols-2">
        {metrics.fdc ? (
          <Panel
            title="Control charts (FDC) on held-out reference units"
            description={`${formatInt(metrics.fdc.holdout_units)} units the limits were not fitted on.`}
          >
            <dl className="grid grid-cols-2 gap-4">
              <Reading
                label="False alarms at the 99% limit"
                value={<EstimateText estimate={metrics.fdc.false_alarm_rate_99} format="percent" />}
              />
              <Reading
                label="False alarms at the 99.9% limit"
                value={
                  <EstimateText estimate={metrics.fdc.false_alarm_rate_999} format="percent" />
                }
              />
            </dl>
            <dl className="mt-4 grid grid-cols-[minmax(0,1fr)] gap-2 text-[13px] leading-5">
              <div>
                <dt className="text-ink-3">EWMA</dt>
                <dd className="tnum text-ink">{metrics.fdc.ewma}</dd>
              </div>
              <div>
                <dt className="text-ink-3">CUSUM</dt>
                <dd className="tnum text-ink">{metrics.fdc.cusum}</dd>
              </div>
            </dl>
          </Panel>
        ) : (
          <Panel title="Control charts (FDC)">
            <p className="text-[14px] text-ink-3">Not measured yet.</p>
          </Panel>
        )}
        {metrics.tuning ? (
          <Panel
            title="Tuning"
            description={`${metrics.tuning.sampler}, ${formatInt(metrics.tuning.trials)} trials. Objective: ${metrics.tuning.objective}.`}
          >
            <dl>
              <Reading
                label="Best objective value"
                value={formatNumber(metrics.tuning.best_value, 3)}
              />
            </dl>
            <dl className="tnum mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-[13px] leading-5 sm:grid-cols-3">
              {Object.entries(metrics.tuning.best_params).map(([k, v]) => (
                <div key={k} className="min-w-0">
                  <dt className="truncate text-ink-3">{k}</dt>
                  <dd className="text-ink">{String(v)}</dd>
                </div>
              ))}
            </dl>
            {metrics.tuning.folds.length ? (
              <details className="mt-4 text-[13px]">
                <summary className="cursor-pointer text-ink">
                  Rolling-origin folds ({metrics.tuning.folds.length})
                </summary>
                <table className="tnum mt-2 w-full border-collapse text-left text-[12px] leading-5">
                  <thead>
                    <tr className="text-ink-3">
                      <th scope="col" className="py-1 pr-2 font-[520]">
                        Fold
                      </th>
                      <th scope="col" className="py-1 pr-2 text-right font-[520]">
                        Train units
                      </th>
                      <th scope="col" className="py-1 pr-2 text-right font-[520]">
                        Validation units
                      </th>
                      <th scope="col" className="py-1 pr-2 text-right font-[520]">
                        Failures
                      </th>
                      <th scope="col" className="py-1 text-right font-[520]">
                        Average precision
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {metrics.tuning.folds.map((f) => (
                      <tr key={f.fold} className="border-t border-hairline">
                        <td className="py-1 pr-2">{f.fold + 1}</td>
                        <td className="py-1 pr-2 text-right">{formatInt(f.train_units)}</td>
                        <td className="py-1 pr-2 text-right">{formatInt(f.validation_units)}</td>
                        <td className="py-1 pr-2 text-right">{formatInt(f.validation_failures)}</td>
                        <td className="py-1 text-right">{formatNumber(f.average_precision, 3)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            ) : null}
          </Panel>
        ) : null}
      </div>

      <Limitations items={metrics.limitations} title="SECOM limitations" />
    </div>
  );
}

function OperatingPointsView({ data }: { data: OperatingPoints }) {
  return (
    <>
      <p className="tnum mb-2 text-[13px] leading-5 text-ink-2">
        {formatInt(data.units)} {data.block} units, {formatInt(data.failures)} failed.
      </p>
      <PrCurve
        curve={data.curve}
        points={data.points}
        prevalence={data.prevalence}
        defaultId={data.default}
      />
      <ScrollRegion label="Operating points on the test block" className="mt-3">
        <table className="w-full min-w-[480px] border-collapse text-left text-[12px] leading-5">
          <caption className="sr-only">Operating points on the test block</caption>
          <thead>
            <tr className="border-b border-hairline text-ink-3">
              <th scope="col" className="py-2.5 pr-2 font-[520]">
                Point
              </th>
              <th scope="col" className="py-2.5 pr-2 font-[520]">
                Recall
              </th>
              <th scope="col" className="py-2.5 pr-2 font-[520]">
                Precision
              </th>
              <th scope="col" className="py-2.5 pr-2 font-[520]">
                False alarms per 100
              </th>
              <th scope="col" className="py-2.5 text-right font-[520]">
                TP / FP / FN
              </th>
            </tr>
          </thead>
          <tbody>
            {data.points.map((p) => (
              <tr key={p.id} className="border-b border-hairline align-top last:border-b-0">
                <th scope="row" className="py-1.5 pr-2 font-[420] text-ink">
                  {p.label}
                  {p.id === data.default ? (
                    <span className="block text-ink-3">Used on the line</span>
                  ) : null}
                </th>
                <td className="py-1.5 pr-2">
                  <EstimateText estimate={p.recall} format="percent" />
                </td>
                <td className="py-1.5 pr-2">
                  <EstimateText estimate={p.precision} format="percent" />
                </td>
                <td className="py-1.5 pr-2">
                  {p.false_alarms_per_100 ? (
                    <EstimateText estimate={p.false_alarms_per_100} format="number" />
                  ) : (
                    <span className="text-ink-3">–</span>
                  )}
                </td>
                <td className="tnum py-1.5 text-right text-ink-2">
                  {formatInt(p.tp)} / {formatInt(p.fp)} / {formatInt(p.fn)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </ScrollRegion>
    </>
  );
}

export function EstimateFootnote({
  estimate,
  className,
}: {
  estimate?: Estimate | null;
  className?: string;
}) {
  if (!estimate?.method && !estimate?.note) return null;
  return (
    <p className={cn("mx-4 mt-3 text-[12px] leading-4 text-ink-3 sm:mx-5", className)}>
      {estimate.method ? `Intervals: ${estimate.method}.` : ""} {estimate.note ?? ""}
    </p>
  );
}
