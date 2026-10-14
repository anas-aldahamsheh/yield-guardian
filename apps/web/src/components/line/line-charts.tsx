"use client";

import type { FdcLimits, LineState, UnitSummary } from "@yield-guardian/contracts";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type KeyboardEvent, useMemo, useState } from "react";

import {
  type LimitLine,
  type MarkTone,
  type SeriesPoint,
  ControlChart,
  axisMax,
} from "@/components/charts/control-chart";
import { useWidth } from "@/components/charts/use-width";
import { formatInt, formatPlantTime, formatProbability, formatReading } from "@/lib/format";
import { BAND_NAME } from "@/lib/labels";
import { cn } from "@/lib/utils";

const bandTone = (u: UnitSummary): MarkTone =>
  u.risk_band === "high" ? "fail" : u.risk_band === "elevated" ? "concern" : "neutral";

const limitTone = (value: number, warn: number, alarm: number): MarkTone =>
  value > alarm ? "fail" : value > warn ? "concern" : "neutral";

/**
 * Hotelling T², SPE and the experimental failure risk for the units in the window, stacked on one time axis with
 * one cursor. Hover or use the arrow keys to read a unit; click or Enter pins it.
 */
export function LineCharts({
  state,
  limits,
  newest,
}: {
  state: LineState;
  limits: FdcLimits | undefined;
  newest: number | null;
}) {
  const router = useRouter();
  const [ref, width] = useWidth<HTMLDivElement>(900);
  const [hover, setHover] = useState<number | null>(null);
  const [pinned, setPinned] = useState<number | null>(null);
  const units = state.recent;
  const first = units[0]?.sequence ?? 0;
  const last = units.at(-1)?.sequence ?? 0;
  const xDomain = useMemo<[number, number]>(() => [first, Math.max(first + 1, last)], [first, last]);
  const bySequence = useMemo(() => new Map(units.map((u) => [u.sequence, u])), [units]);
  const pinnedUnit = pinned != null ? bySequence.get(pinned) : undefined;
  const active = hover ?? pinnedUnit?.sequence ?? last;
  const unit = bySequence.get(active) ?? units.at(-1);

  const threshold = state.operating_point.threshold;
  const risk = useMemo(() => {
    const points: SeriesPoint[] = units.map((u) => ({ x: u.sequence, y: u.risk, tone: bandTone(u) }));
    const lines: LimitLine[] = [
      { value: threshold, label: `Threshold ${formatProbability(threshold)}`, pattern: "dashed" },
    ];
    return { points, lines, max: axisMax(points.map((p) => p.y), [threshold], 0.2) };
  }, [units, threshold]);

  const t2 = useMemo(() => {
    if (!limits) return null;
    const points: SeriesPoint[] = units.map((u) => ({
      x: u.sequence,
      y: u.t2,
      tone: limitTone(u.t2, limits.t2_99, limits.t2_999),
    }));
    const lines: LimitLine[] = [
      { value: limits.t2_99, label: `99% ${formatReading(limits.t2_99, 3)}`, pattern: "dotted" },
      { value: limits.t2_999, label: `99.9% ${formatReading(limits.t2_999, 3)}`, pattern: "dashed" },
    ];
    return { points, lines, max: axisMax(points.map((p) => p.y), [limits.t2_999]) };
  }, [units, limits]);

  const spe = useMemo(() => {
    if (!limits) return null;
    const points: SeriesPoint[] = units.map((u) => ({
      x: u.sequence,
      y: u.spe,
      tone: limitTone(u.spe, limits.spe_99, limits.spe_999),
    }));
    const lines: LimitLine[] = [
      { value: limits.spe_99, label: `99% ${formatReading(limits.spe_99, 3)}`, pattern: "dotted" },
      { value: limits.spe_999, label: `99.9% ${formatReading(limits.spe_999, 3)}`, pattern: "dashed" },
    ];
    return { points, lines, max: axisMax(points.map((p) => p.y), [limits.spe_999]) };
  }, [units, limits]);

  const rug = useMemo(
    () => ({
      label: "Final test",
      marks: units
        .filter((u) => u.final_test != null)
        .map((u) => ({ x: u.sequence, result: u.final_test as "pass" | "fail" })),
    }),
    [units],
  );

  const move = (to: number) => setPinned(Math.min(last, Math.max(first, to)));
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const from = pinned ?? last;
    const big = e.shiftKey ? 10 : 1;
    if (e.key === "ArrowLeft") move(from - big);
    else if (e.key === "ArrowRight") move(from + big);
    else if (e.key === "Home") move(first);
    else if (e.key === "End") move(last);
    else if (e.key === "Escape") setPinned(null);
    else if (e.key === "Enter" && unit) router.push(`/units/${unit.unit_id}`);
    else return;
    e.preventDefault();
  };

  const shared = {
    width,
    xDomain,
    cursorX: hover ?? pinned,
    pinned: hover == null && pinned != null,
    newestX: newest ?? undefined,
    onPointerX: setHover,
    onPick: (x: number) => setPinned((p) => (p === x ? null : x)),
  };

  return (
    <div className="min-w-0">
      <Readout unit={unit} pinned={pinnedUnit != null && hover == null} lag={state.clock.final_test_lag_units} />
      <div
        ref={ref}
        role="group"
        tabIndex={0}
        aria-label={`Control charts for units ${formatInt(first)} to ${formatInt(last)}. Left and right arrows move between units, Enter opens the unit, Escape returns to the latest.`}
        onKeyDown={onKeyDown}
        className="mt-3 rounded-sm"
      >
        {t2 && spe ? (
          <>
            <ControlChart
              {...shared}
              label="Hotelling T²"
              points={t2.points}
              yMax={t2.max}
              limits={t2.lines}
              formatTick={(v) => formatInt(v)}
              rug={rug}
              height={166}
            />
            <ControlChart {...shared} label="SPE (Q)" points={spe.points} yMax={spe.max} limits={spe.lines} formatTick={(v) => formatInt(v)} />
          </>
        ) : (
          <p className="py-6 pl-[52px] text-sm text-ink-3">Control limits are loading.</p>
        )}
        <ControlChart
          {...shared}
          label="Failure risk, experimental"
          points={risk.points}
          yMax={risk.max}
          limits={risk.lines}
          formatTick={(v) => `${Math.round(v * 100)}%`}
          showXAxis
          height={166}
        />
      </div>
      <Legend />
      <p className="sr-only" aria-live="polite">
        {pinnedUnit ? `Unit ${pinnedUnit.unit_id}: T² ${formatReading(pinnedUnit.t2)}, SPE ${formatReading(pinnedUnit.spe)}, experimental risk ${formatProbability(pinnedUnit.risk)}.` : ""}
      </p>
    </div>
  );
}

function Readout({ unit, pinned, lag }: { unit: UnitSummary | undefined; pinned: boolean; lag: number }) {
  if (!unit) return null;
  const finalTest =
    unit.final_test === "fail" ? (
      <span className="text-fail">Fail</span>
    ) : unit.final_test === "pass" ? (
      <span className="text-pass">Pass</span>
    ) : (
      <span className="text-ink-3">Pending</span>
    );
  return (
    <div className={cn("flex flex-wrap items-end gap-x-6 gap-y-2 rounded-sm px-3 py-2", pinned ? "lit" : "bg-die-2")}>
      <dl className="grid grow grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-3 lg:grid-cols-6">
        <ReadoutItem label="Unit" value={formatInt(unit.unit_id)} />
        <ReadoutItem label="Plant time" value={formatPlantTime(unit.timestamp)} />
        <ReadoutItem label="T²" value={formatReading(unit.t2)} />
        <ReadoutItem label="SPE" value={formatReading(unit.spe)} />
        <ReadoutItem
          label="Risk, experimental"
          value={unit.risk == null ? "Warm-up" : formatProbability(unit.risk)}
          detail={unit.risk_band ? BAND_NAME[unit.risk_band] : undefined}
        />
        <ReadoutItem
          label="Final test"
          value={finalTest}
          detail={unit.final_test == null ? `after ${lag} units` : undefined}
        />
      </dl>
      <Link
        href={`/units/${unit.unit_id}`}
        className="text-[13px] leading-5 whitespace-nowrap text-ink underline decoration-hairline-strong underline-offset-4 hover:decoration-ink"
      >
        Open unit {formatInt(unit.unit_id)}
      </Link>
    </div>
  );
}

function ReadoutItem({ label, value, detail }: { label: string; value: React.ReactNode; detail?: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[12px] leading-4 text-ink-3">{label}</dt>
      <dd className="tnum truncate text-[15px] leading-6 text-ink">
        {value}
        {detail ? <span className="ml-1.5 text-[12px] text-ink-3">{detail}</span> : null}
      </dd>
    </div>
  );
}

function Legend() {
  const item = "flex items-center gap-1.5";
  return (
    <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 pl-[52px] text-[12px] leading-4 text-ink-2" aria-label="Legend">
      <li className={item}>
        <svg width="10" height="10" aria-hidden="true"><circle cx="5" cy="5" r="3.5" fill="var(--fail)" /></svg>
        Beyond the 99.9% limit, or high risk
      </li>
      <li className={item}>
        <svg width="10" height="10" aria-hidden="true"><circle cx="5" cy="5" r="3.5" fill="var(--concern)" /></svg>
        Beyond the 99% limit, or elevated risk
      </li>
      <li className={item}>
        <svg width="10" height="10" aria-hidden="true"><path d="M5,1 l4,7 h-8z" fill="var(--ink-3)" /></svg>
        Above the axis: read the value above
      </li>
      <li className={item}>
        <svg width="10" height="12" aria-hidden="true"><line x1="5" x2="5" y1="1" y2="11" stroke="var(--fail)" strokeWidth="2" /></svg>
        Failed final test
      </li>
      <li className={item}>
        <svg width="10" height="12" aria-hidden="true"><line x1="5" x2="5" y1="4" y2="11" stroke="var(--pass)" strokeOpacity="0.55" /></svg>
        Passed
      </li>
    </ul>
  );
}

