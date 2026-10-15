"use client";

import type {
  ControlChartsResult,
  DriftHealthResult,
  FinalTestResult,
  GroupDrift,
  MetricValue,
  SensorRiskResult,
  UnitChartResult,
  UnitRiskResult,
} from "@yield-guardian/contracts";
import { type KeyboardEvent, useMemo, useState } from "react";

import { useWidth } from "@/components/charts/use-width";
import { ScrollRegion } from "@/components/scroll-region";
import {
  ciLabel,
  formatInt,
  formatInterval,
  formatNumber,
  formatPercent,
  formatPlantTime,
  formatProbability,
  formatReading,
  formatSigned,
  plural,
} from "@/lib/format";
import { BAND_NAME, HEALTH_STATUS, HEALTH_STATUS_ORDER } from "@/lib/labels";
import { stageResult, type RunState } from "@/lib/live/run-state";
import { cn } from "@/lib/utils";

import { DrawerSection, Fact, Method, NotYet } from "./drawer-parts";
import { decadeLabel, decades, logDomain, logPosition, riskDomain } from "./scales";

const VALIDITY: Record<UnitRiskResult["validity"], string> = {
  held_out: "Held out: the model never trained on this unit.",
  in_training:
    "In training: the model saw this unit while it learned, so its score here is in-sample and optimistic.",
  new_data: "New data: not a SECOM unit the model knows.",
};

/** "ROC-AUC 0.52 (95% CI 0.38–0.66)": a measured skill with its interval, by its label. */
export function skillText(m: MetricValue): string {
  const ci = formatInterval(m.estimate);
  return `${m.label} ${formatNumber(m.estimate.value)}${ci ? ` (${ciLabel(m.estimate)} ${ci})` : ""}`;
}

/**
 * Station 2 in detail, for every unit of the run: T² and SPE of each unit against the model's
 * limits (pick a unit there), the chosen unit's risk with the model's measured skill, the
 * sensors behind its risk and its statistics, drift of the leading sensor groups, sensor health,
 * and whether the warnings matched final test.
 */
function defaultUnit(charts: ControlChartsResult | null, risk: SensorRiskResult | null): number {
  const alarm = charts?.units.findIndex((u) => u.level === "alarm") ?? -1;
  if (alarm !== -1) return alarm;
  if (!risk?.units.length) return 0;
  return risk.units.reduce((best, u, i, all) => (u.risk > all[best]!.risk ? i : best), 0);
}

export function UnitsDrawer({
  state,
  shown,
  unit,
  onUnit,
}: {
  state: RunState;
  shown: (stage: "sensor_risk" | "control_charts" | "drift_health" | "final_test") => boolean;
  unit: number | null;
  onUnit: (index: number) => void;
}) {
  const charts = shown("control_charts") ? stageResult(state, "control_charts") : null;
  const risk = shown("sensor_risk") ? stageResult(state, "sensor_risk") : null;
  const drift = shown("drift_health") ? stageResult(state, "drift_health") : null;
  const final = shown("final_test") ? stageResult(state, "final_test") : null;
  const count = charts?.units.length ?? risk?.units.length ?? 0;
  // Without a unit chosen, the drawer opens on the first unit beyond the 99.9% limits, else the
  // unit with the highest risk.
  const index = unit != null && unit < count ? unit : count ? defaultUnit(charts, risk) : null;

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-8">
      {charts ? (
        <DrawerSection
          title="Every unit against the control limits"
          description="Choose a unit on the chart, or move along it with the arrow keys."
        >
          <UnitsChart charts={charts} risk={risk} selected={index} onSelect={onUnit} />
          <Method>{charts.method}</Method>
        </DrawerSection>
      ) : (
        <NotYet stage={state.stages.control_charts} what="The control charts" />
      )}

      {index != null ? (
        <div className="grid grid-cols-[minmax(0,1fr)] gap-8 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          {risk ? (
            <RiskPanel result={risk} unit={risk.units[index]!} />
          ) : (
            <NotYet stage={state.stages.sensor_risk} what="The failure risk" />
          )}
          {charts ? <ChartPanel charts={charts} unit={charts.units[index]!} /> : null}
        </div>
      ) : count ? (
        <p className="text-[14px] text-ink-2">
          Choose a unit on the chart to see its risk and the sensors behind it.
        </p>
      ) : null}

      {drift ? (
        <DriftPanel
          drift={drift}
          unitIds={(charts ?? risk)?.units.map((u) => u.unit_id) ?? []}
          selected={index}
        />
      ) : (
        <NotYet stage={state.stages.drift_health} what="Drift and sensor health" />
      )}
      {drift ? <HealthPanel drift={drift} /> : null}
      {final && final.units_with_result > 0 ? (
        <FinalUnits final={final} unitIds={(charts ?? risk)?.units.map((u) => u.unit_id) ?? []} />
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
// T² and SPE per unit, log scale, the model's 99% and 99.9% limits
// ---------------------------------------------------------------------------------------------

const ROW = 112;
const LEFT = 44;
const RIGHT = 12;

function UnitsChart({
  charts,
  risk,
  selected,
  onSelect,
}: {
  charts: ControlChartsResult;
  risk: SensorRiskResult | null;
  selected: number | null;
  onSelect: (index: number) => void;
}) {
  const [ref, width] = useWidth<HTMLDivElement>(640);
  const units = charts.units;
  const n = units.length;
  const timed = n > 0 && units.every((u) => u.timestamp != null);
  const times = useMemo(
    () => (timed ? units.map((u) => Date.parse(u.timestamp!)) : null),
    [timed, units],
  );
  const t0 = times ? Math.min(...times) : 0;
  const t1 = times ? Math.max(...times) : 0;
  const plotW = Math.max(40, width - LEFT - RIGHT);
  const xOf = (i: number) => {
    if (times && t1 > t0) return LEFT + ((times[i]! - t0) / (t1 - t0)) * plotW;
    return LEFT + (n <= 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  };
  const rows = [
    {
      key: "t2" as const,
      label: "T²",
      values: units.map((u) => u.t2),
      l99: charts.limits.t2_99,
      l999: charts.limits.t2_999,
    },
    {
      key: "spe" as const,
      label: "SPE",
      values: units.map((u) => u.spe),
      l99: charts.limits.spe_99,
      l999: charts.limits.spe_999,
    },
  ];
  const height = rows.length * ROW + 34;
  const r = n > 300 ? 1.5 : n > 120 ? 2 : 2.6;
  const at = selected ?? null;

  const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
    const step =
      e.key === "ArrowRight" || e.key === "ArrowUp"
        ? 1
        : e.key === "ArrowLeft" || e.key === "ArrowDown"
          ? -1
          : 0;
    if (e.key === "Home") onSelect(0);
    else if (e.key === "End") onSelect(n - 1);
    else if (step) onSelect(Math.min(n - 1, Math.max(0, (at ?? (step > 0 ? -1 : n)) + step)));
    else return;
    e.preventDefault();
  };
  const nearest = (clientX: number, box: DOMRect) => {
    const x = clientX - box.left;
    let best = 0;
    let d = Infinity;
    for (let i = 0; i < n; i += 1) {
      const dx = Math.abs(xOf(i) - x);
      if (dx < d) {
        d = dx;
        best = i;
      }
    }
    return best;
  };
  const u = at != null ? units[at] : undefined;
  const xTicks = (count: number, ts: number[] | null, a: number, b: number, w: number) => {
    const max = Math.max(2, Math.floor(w / 110));
    if (ts && b > a) {
      return Array.from({ length: max }, (_, k) => {
        const t = a + ((b - a) * k) / (max - 1);
        return {
          x: LEFT + ((t - a) / (b - a)) * w,
          label: formatPlantTime(new Date(t).toISOString()).slice(5),
        };
      });
    }
    const step = Math.max(1, Math.ceil(count / max));
    const out: { x: number; label: string }[] = [];
    for (let i = 0; i < count; i += step) out.push({ x: xOf(i), label: String(i + 1) });
    return out;
  };
  const ticks = xTicks(n, times, t0, t1, plotW);

  return (
    <div ref={ref} className="min-w-0">
      <svg
        width={width}
        height={height}
        role="slider"
        tabIndex={0}
        aria-label="Unit"
        aria-valuemin={1}
        aria-valuemax={n}
        aria-valuenow={at != null ? at + 1 : undefined}
        aria-valuetext={
          u
            ? `Unit ${u.unit_id}: T² ${formatReading(u.t2)}, SPE ${formatReading(u.spe)}`
            : "No unit chosen"
        }
        onKeyDown={onKey}
        onClick={(e) => onSelect(nearest(e.clientX, e.currentTarget.getBoundingClientRect()))}
        className="block cursor-pointer touch-pan-y outline-offset-4 select-none"
      >
        {rows.map((row, k) => {
          const scale = logDomain(row.values, [row.l99, row.l999]);
          const top = k * ROW + 18;
          const h = ROW - 30;
          const yOf = (v: number) => top + h - logPosition(v, scale) * h;
          return (
            <g key={row.key}>
              <text x={0} y={top - 6} className="fill-ink text-[12px] font-semibold">
                {row.label}
                <tspan className="fill-ink-3 font-normal"> log scale</tspan>
              </text>
              {decades(scale).map((e) => (
                <g key={e}>
                  <line
                    x1={LEFT}
                    x2={LEFT + plotW}
                    y1={yOf(10 ** e)}
                    y2={yOf(10 ** e)}
                    stroke="var(--hairline)"
                    shapeRendering="crispEdges"
                  />
                  <text
                    x={LEFT - 6}
                    y={yOf(10 ** e)}
                    dy="0.32em"
                    textAnchor="end"
                    className="tnum fill-ink-3 text-[10px]"
                  >
                    {decadeLabel(e)}
                  </text>
                </g>
              ))}
              <rect
                x={LEFT}
                y={top}
                width={plotW}
                height={Math.max(0, yOf(row.l999) - top)}
                fill="var(--fail-wash)"
                opacity={0.45}
              />
              {[
                { v: row.l99, label: `99% ${formatReading(row.l99, 3)}`, dash: "4 3" },
                { v: row.l999, label: `99.9% ${formatReading(row.l999, 3)}`, dash: undefined },
              ].map((limit) => (
                <g key={limit.label}>
                  <line
                    x1={LEFT}
                    x2={LEFT + plotW}
                    y1={yOf(limit.v)}
                    y2={yOf(limit.v)}
                    stroke="var(--ink-2)"
                    strokeDasharray={limit.dash}
                    shapeRendering="crispEdges"
                  />
                  <text
                    x={LEFT + plotW}
                    y={yOf(limit.v) - 3}
                    textAnchor="end"
                    className="tnum fill-ink-2 text-[10px]"
                    style={{ paintOrder: "stroke", stroke: "var(--die)", strokeWidth: 3 }}
                  >
                    {limit.label}
                  </text>
                </g>
              ))}
              {row.values.map((v, i) => {
                const tone =
                  v > row.l999 ? "var(--fail)" : v > row.l99 ? "var(--concern)" : "var(--ink-3)";
                const high = risk?.units[i]?.above_threshold;
                return (
                  <circle
                    key={i}
                    cx={xOf(i)}
                    cy={yOf(v)}
                    r={v > row.l99 ? r + 0.6 : r}
                    fill={tone}
                    stroke={high ? "var(--ink)" : "none"}
                    strokeWidth={high ? 1 : 0}
                  />
                );
              })}
              {at != null ? (
                <circle
                  cx={xOf(at)}
                  cy={yOf(row.values[at]!)}
                  r={r + 4}
                  fill="none"
                  stroke="var(--safelight)"
                  strokeWidth={1.5}
                />
              ) : null}
            </g>
          );
        })}
        {at != null ? (
          <line
            x1={xOf(at)}
            x2={xOf(at)}
            y1={12}
            y2={rows.length * ROW}
            stroke="var(--safelight)"
            strokeWidth={1}
            opacity={0.8}
          />
        ) : null}
        {ticks.map((t) => (
          <text
            key={t.x}
            x={t.x}
            y={rows.length * ROW + 10}
            // Labels at the plot's ends align to them so they are not cut off.
            textAnchor={t.x < LEFT + 30 ? "start" : t.x > LEFT + plotW - 30 ? "end" : "middle"}
            className="tnum fill-ink-3 text-[11px]"
          >
            {t.label}
          </text>
        ))}
        <text x={LEFT + plotW} y={height - 2} textAnchor="end" className="fill-ink-3 text-[11px]">
          {timed ? "Unit time as recorded" : "Units in input order"}
        </text>
      </svg>
      <p className="mt-1 text-[12px] leading-4 text-ink-3">
        Points beyond the 99.9% limit are in the fail colour, beyond 99% in the muted one.
        {risk ? " A ring marks a unit above the risk threshold." : ""}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
// Risk of one unit
// ---------------------------------------------------------------------------------------------

function RiskPanel({ result, unit }: { result: SensorRiskResult; unit: UnitRiskResult }) {
  const top = riskDomain([unit.risk], result.threshold);
  const pos = (v: number) => `${Math.min(100, (v / top) * 100)}%`;
  const rest = unit.raw_score - unit.base_value - unit.top.reduce((s, f) => s + f.shap, 0);
  const maxShap = Math.max(Math.abs(rest), ...unit.top.map((f) => Math.abs(f.shap)), 1e-9);
  const groups = useMemo(() => {
    const by = new Map<string, { sensors: string[]; shap: number }>();
    for (const f of unit.top) {
      if (!f.group_id) continue;
      const g = by.get(f.group_id) ?? { sensors: [], shap: 0 };
      if (!g.sensors.includes(f.sensor)) g.sensors.push(f.sensor);
      g.shap += f.shap;
      by.set(f.group_id, g);
    }
    return [...by.entries()].sort((a, b) => Math.abs(b[1].shap) - Math.abs(a[1].shap));
  }, [unit]);

  return (
    <DrawerSection
      title={`Failure risk of unit ${unit.unit_id}`}
      description={result.operating_point}
    >
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span
          className={cn(
            "readout text-[34px] leading-10",
            unit.above_threshold ? "text-fail" : "text-ink",
          )}
        >
          {formatProbability(unit.risk)}
        </span>
        <span className="text-[14px] text-ink-2">
          {`${BAND_NAME[unit.band] ?? unit.band} band, ${unit.above_threshold ? "above" : "below"} the threshold of ${formatProbability(result.threshold)}`}
        </span>
      </div>
      <div className="relative mt-3 h-6" aria-hidden="true">
        <div className="absolute inset-x-0 top-2.5 h-1 rounded-full bg-hairline" />
        <div
          className="absolute top-2.5 h-1 bg-concern"
          style={{
            left: pos(result.elevated_threshold),
            width: `calc(${pos(result.threshold)} - ${pos(result.elevated_threshold)})`,
          }}
        />
        <div
          className="absolute top-2.5 right-0 h-1 bg-fail"
          style={{ left: pos(result.threshold) }}
        />
        <div
          className="absolute top-0 h-6 w-0.5 -translate-x-1/2 bg-ink"
          style={{ left: pos(unit.risk) }}
        />
      </div>
      <div
        className="tnum flex justify-between text-[11px] leading-4 text-ink-3"
        aria-hidden="true"
      >
        <span>0%</span>
        <span>{`elevated from ${formatProbability(result.elevated_threshold)}, high from ${formatProbability(result.threshold)}`}</span>
        <span>{formatPercent(top, 0)}</span>
      </div>
      <dl className="mt-4 grid grid-cols-[minmax(0,1fr)] gap-2">
        <Fact label="Measured skill">{result.skill.map(skillText).join("; ")}</Fact>
        <Fact label="What that means">{result.caution}</Fact>
        <Fact label="This unit">{VALIDITY[unit.validity]}</Fact>
      </dl>

      <h4 className="mt-5 text-[14px] leading-5 font-semibold text-ink">
        What moved this unit&apos;s risk
      </h4>
      <p className="text-[12px] leading-4 text-ink-3">
        {`TreeSHAP in log-odds: from the base ${formatSigned(unit.base_value)} to ${formatSigned(unit.raw_score)} for this unit. Right raises the risk, left lowers it.`}
      </p>
      <ul className="mt-2 grid grid-cols-[minmax(0,1fr)] gap-0.5">
        {unit.top.map((f) => (
          <ShapRow
            key={f.feature}
            name={f.sensor}
            detail={
              f.indicator ? "missing" : f.value == null ? "no reading" : formatReading(f.value)
            }
            shap={f.shap}
            max={maxShap}
          />
        ))}
        <ShapRow name="All other features" detail="" shap={rest} max={maxShap} muted />
      </ul>
      {groups.length ? (
        <>
          <h4 className="mt-5 text-[14px] leading-5 font-semibold text-ink">
            Sensor groups among them
          </h4>
          <p className="text-[12px] leading-4 text-ink-3">
            SECOM sensors are anonymous; groups of sensors that move together are what can be named.
          </p>
          <ul className="mt-1.5 grid grid-cols-[minmax(0,1fr)] text-[13px] leading-5">
            {groups.map(([id, g]) => (
              <li
                key={id}
                className="tnum flex justify-between gap-3 border-b border-hairline py-1"
              >
                <span className="text-ink">
                  {id} <span className="text-ink-3">{g.sensors.join(", ")}</span>
                </span>
                <span className="text-ink-2">{formatSigned(g.shap)}</span>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </DrawerSection>
  );
}

function ShapRow({
  name,
  detail,
  shap,
  max,
  muted = false,
}: {
  name: string;
  detail: string;
  shap: number;
  max: number;
  muted?: boolean;
}) {
  const w = `${(Math.abs(shap) / max) * 50}%`;
  return (
    <li className="tnum grid grid-cols-[96px_minmax(0,1fr)_52px] items-center gap-2 text-[12px] leading-5">
      <span
        className={cn("truncate", muted ? "text-ink-3" : "text-ink")}
        title={detail ? `${name}: ${detail}` : name}
      >
        {name}
        {detail ? <span className="text-ink-3"> {detail}</span> : null}
      </span>
      <span className="relative h-3" aria-hidden="true">
        <span className="absolute inset-y-0 left-1/2 w-px bg-hairline-strong" />
        <span
          className={cn(
            "absolute inset-y-0.5",
            shap >= 0 ? "left-1/2 bg-fail" : "right-1/2 bg-pass",
            muted && "opacity-40",
          )}
          style={{ width: w }}
        />
      </span>
      <span className={cn("text-right", muted ? "text-ink-3" : "text-ink-2")}>
        {formatSigned(shap)}
      </span>
    </li>
  );
}

// ---------------------------------------------------------------------------------------------
// T² and SPE of one unit, and the sensors behind them
// ---------------------------------------------------------------------------------------------

function ChartPanel({ charts, unit }: { charts: ControlChartsResult; unit: UnitChartResult }) {
  const [stat, setStat] = useState<"t2" | "spe">(
    unit.spe / charts.limits.spe_999 > unit.t2 / charts.limits.t2_999 ? "spe" : "t2",
  );
  const rows = stat === "t2" ? unit.top_t2 : unit.top_spe;
  const max = Math.max(...rows.map((r) => Math.abs(r.share)), 1e-9);
  return (
    <DrawerSection
      title={`Control statistics of unit ${unit.unit_id}`}
      description={
        unit.timestamp ? `Recorded ${formatPlantTime(unit.timestamp)}` : "No time recorded"
      }
    >
      <dl className="grid grid-cols-2 gap-4">
        {(
          [
            ["t2", "T²", unit.t2, charts.limits.t2_99, charts.limits.t2_999],
            ["spe", "SPE", unit.spe, charts.limits.spe_99, charts.limits.spe_999],
          ] as const
        ).map(([key, label, v, l99, l999]) => (
          <div key={key}>
            <dt className="text-[13px] leading-5 text-ink-3">{label}</dt>
            <dd
              className={cn(
                "readout text-[28px] leading-9",
                v > l999 ? "text-fail" : v > l99 ? "text-concern" : "text-ink",
              )}
            >
              {formatReading(v)}
            </dd>
            <dd className="tnum text-[12px] leading-4 text-ink-3">{`limits ${formatReading(l99)} (99%), ${formatReading(l999)} (99.9%)`}</dd>
            <dd className="tnum text-[12px] leading-4 text-ink-2">{`${formatNumber(v / l999)} times the 99.9% limit`}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-5 flex flex-wrap items-baseline justify-between gap-2">
        <h4 className="text-[14px] leading-5 font-semibold text-ink">Sensors behind it</h4>
        <div role="group" aria-label="Statistic" className="flex gap-1">
          {(["t2", "spe"] as const).map((s) => (
            <button
              key={s}
              type="button"
              aria-pressed={stat === s}
              onClick={() => setStat(s)}
              className={cn(
                "rounded-[4px] px-2 py-0.5 text-[13px] leading-5 text-ink hover:bg-die-2",
                stat === s && "lit",
              )}
            >
              {s === "t2" ? "T²" : "SPE"}
            </button>
          ))}
        </div>
      </div>
      <p className="text-[12px] leading-4 text-ink-3">
        {stat === "spe"
          ? "Each sensor's squared residual: the parts add up to SPE."
          : "Each sensor's part of T²: the parts add up to T², and one can be negative when it pulls the score back."}
      </p>
      <ul className="mt-2 grid grid-cols-[minmax(0,1fr)] gap-0.5">
        {rows.map((r) => (
          <li
            key={r.sensor}
            className="tnum grid grid-cols-[56px_minmax(0,1fr)_88px] items-center gap-2 text-[12px] leading-5"
          >
            <span className="text-ink">{r.sensor}</span>
            <span className="relative h-3" aria-hidden="true">
              <span
                className={cn("absolute inset-y-0.5 left-0", r.share >= 0 ? "bg-ink-2" : "bg-pass")}
                style={{ width: `${(Math.abs(r.share) / max) * 100}%` }}
              />
            </span>
            <span className="text-right text-ink-2">{`${formatReading(r.contribution, 3)}, ${formatPercent(r.share)}`}</span>
          </li>
        ))}
      </ul>
    </DrawerSection>
  );
}

// ---------------------------------------------------------------------------------------------
// Drift of the leading sensor groups
// ---------------------------------------------------------------------------------------------

function DriftPanel({
  drift,
  unitIds,
  selected,
}: {
  drift: DriftHealthResult;
  unitIds: string[];
  selected: number | null;
}) {
  return (
    <DrawerSection
      title="Slow drift in the leading sensor groups"
      description={`EWMA (λ ${formatNumber(drift.ewma_lambda, 1)}) and CUSUM (k ${formatNumber(drift.cusum_k, 1)}) of each group's score, unit by unit.`}
    >
      <ul className="grid grid-cols-[minmax(0,1fr)] gap-3 md:grid-cols-2 2xl:grid-cols-3">
        {drift.groups.map((g) => (
          <li key={g.group_id}>
            <DriftSpark group={g} unitIds={unitIds} selected={selected} />
          </li>
        ))}
      </ul>
      <Method>{drift.method}</Method>
    </DrawerSection>
  );
}

function DriftSpark({
  group,
  unitIds,
  selected,
}: {
  group: GroupDrift;
  unitIds: string[];
  selected: number | null;
}) {
  const [ref, width] = useWidth<HTMLDivElement>(300);
  const h = 64;
  const n = group.ewma.length;
  const lim = group.ewma_limit;
  const span = Math.max(lim * 1.4, ...group.ewma.map((v) => Math.abs(v)));
  const x = (i: number) => (n <= 1 ? width / 2 : (i / (n - 1)) * (width - 2) + 1);
  const y = (v: number) => h / 2 - (v / span) * (h / 2 - 3);
  const path = group.ewma
    .map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`)
    .join("");
  const alarm = group.first_ewma_alarm;
  const cusum = group.first_cusum_alarm;
  const text = [
    alarm != null
      ? `EWMA left its limit at unit ${unitIds[alarm] ?? alarm + 1}`
      : "EWMA within its limits",
    cusum != null ? `CUSUM signalled at unit ${unitIds[cusum] ?? cusum + 1}` : "no CUSUM signal",
  ].join("; ");
  return (
    <div ref={ref} className="min-w-0">
      <p className="tnum text-[13px] leading-5 text-ink">
        {group.group_id}{" "}
        <span className="text-ink-3">{plural(group.sensors.length, "sensor")}</span>
      </p>
      <svg
        width={width}
        height={h}
        role="img"
        aria-label={`${group.group_id}: ${text}.`}
        className="block"
      >
        <rect x={0} y={0} width={width} height={y(lim)} fill="var(--fail-wash)" opacity={0.35} />
        <rect
          x={0}
          y={y(-lim)}
          width={width}
          height={h - y(-lim)}
          fill="var(--fail-wash)"
          opacity={0.35}
        />
        <line x1={0} x2={width} y1={y(0)} y2={y(0)} stroke="var(--hairline)" />
        <line
          x1={0}
          x2={width}
          y1={y(lim)}
          y2={y(lim)}
          stroke="var(--ink-3)"
          strokeDasharray="3 3"
        />
        <line
          x1={0}
          x2={width}
          y1={y(-lim)}
          y2={y(-lim)}
          stroke="var(--ink-3)"
          strokeDasharray="3 3"
        />
        {selected != null && selected < n ? (
          <line x1={x(selected)} x2={x(selected)} y1={0} y2={h} stroke="var(--safelight)" />
        ) : null}
        <path
          d={path}
          fill="none"
          stroke={alarm != null ? "var(--fail)" : "var(--ink-2)"}
          strokeWidth={1.25}
        />
        {alarm != null ? (
          <circle cx={x(alarm)} cy={y(group.ewma[alarm]!)} r={3} fill="var(--fail)" />
        ) : null}
      </svg>
      <p className="tnum text-[12px] leading-4 text-ink-3">{`${text}. Limits ±${formatNumber(lim, 3)}.`}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
// Sensor health
// ---------------------------------------------------------------------------------------------

function HealthPanel({ drift }: { drift: DriftHealthResult }) {
  const [status, setStatus] = useState<(typeof HEALTH_STATUS_ORDER)[number]>("dead");
  const list = drift.health.filter((h) => h.status === status);
  return (
    <DrawerSection
      title="Sensor health on this input"
      description="Rules of sensor health applied to these readings, in time order."
    >
      <div role="group" aria-label="Health status" className="flex flex-wrap gap-1.5">
        {HEALTH_STATUS_ORDER.map((s) => (
          <button
            key={s}
            type="button"
            aria-pressed={status === s}
            onClick={() => setStatus(s)}
            className={cn(
              "tnum rounded-[4px] border border-hairline-strong px-2.5 py-1 text-[13px] leading-5 text-ink hover:bg-die-2",
              status === s && "lit border-transparent",
            )}
          >
            {`${HEALTH_STATUS[s]} ${formatInt(drift.health_counts[s] ?? 0)}`}
          </button>
        ))}
      </div>
      {list.length ? (
        <ScrollRegion
          label="Sensors with this status"
          className="mt-2 max-h-[260px] overflow-y-auto"
        >
          <table className="w-full text-left text-[13px] leading-5">
            <thead className="sticky top-0 bg-die text-ink-3">
              <tr>
                <th scope="col" className="py-1 pr-3 font-normal">
                  Sensor
                </th>
                <th scope="col" className="py-1 font-normal">
                  Why
                </th>
              </tr>
            </thead>
            <tbody>
              {list.map((h) => (
                <tr key={h.sensor} className="border-t border-hairline align-top">
                  <td className="tnum py-1 pr-3 text-ink">{h.sensor}</td>
                  <td className="py-1 text-ink-2">{h.reasons.join("; ") || "none of the rules"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollRegion>
      ) : (
        <p className="mt-2 text-[13px] text-ink-3">
          {status === "ok"
            ? "Sensors in good health are counted, not listed."
            : `No sensor is ${HEALTH_STATUS[status]?.toLowerCase()}.`}
        </p>
      )}
      <details className="mt-3 text-[12px] leading-4 text-ink-3">
        <summary className="cursor-pointer text-ink-2">The rules</summary>
        <ul className="mt-1 list-disc space-y-1 pl-4">
          {drift.rules.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      </details>
    </DrawerSection>
  );
}

// ---------------------------------------------------------------------------------------------
// Were the warnings right?
// ---------------------------------------------------------------------------------------------

function FinalUnits({ final, unitIds }: { final: FinalTestResult; unitIds: string[] }) {
  const failed = final.units.filter((u) => u.result === "fail");
  return (
    <DrawerSection title="Was the warning right?" description={final.summary}>
      <dl className="tnum grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
        <Fact label="Units with a result">{formatInt(final.units_with_result)}</Fact>
        <Fact label="Failed final test">{formatInt(final.failed_units)}</Fact>
        <Fact label="Failed, and the risk warned">{formatInt(final.failed_flagged)}</Fact>
        <Fact label="Passed, but the risk warned">{formatInt(final.passed_flagged)}</Fact>
      </dl>
      {failed.length ? (
        <p className="mt-2 text-[13px] leading-5 text-ink-2">
          {`Failed: ${failed.map((u) => `unit ${u.unit_id}${u.flagged ? " (warned)" : ""}`).join(", ")}.`}
        </p>
      ) : null}
      {unitIds.length > final.units_with_result ? (
        <p className="mt-1 text-[12px] leading-4 text-ink-3">{`${plural(unitIds.length - final.units_with_result, "unit")} came without a final-test result.`}</p>
      ) : null}
    </DrawerSection>
  );
}
