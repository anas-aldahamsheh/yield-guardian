"use client";

import {
  ActivityIcon,
  AlertTriangleIcon,
  BarChart3Icon,
  CheckCircle2Icon,
  CpuIcon,
  GaugeIcon,
  LayersIcon,
  SlidersIcon,
} from "lucide-react";

import { formatInt, formatNumber } from "@/lib/format";
import { ALARM_KIND } from "@/lib/labels";
import { cn } from "@/lib/utils";

interface EvidenceTelemetryCardProps {
  data: Record<string, unknown>;
  tool: string;
  className?: string;
}

/** Formats floating point values to 2 or 3 decimals for human readability */
function fmt(val: unknown, decimals = 2): string {
  if (typeof val === "number") {
    return val.toLocaleString(undefined, {
      minimumFractionDigits: 0,
      maximumFractionDigits: decimals,
    });
  }
  return String(val ?? "–");
}

export function EvidenceTelemetryCard({ data, tool, className }: EvidenceTelemetryCardProps) {
  // Check for common semiconductor SPC / FDC telemetry fields
  const hasSpc = "t2" in data || "spe" in data || "risk" in data;
  const alarms = Array.isArray(data.alarms) ? (data.alarms as Array<Record<string, unknown>>) : [];
  const sensors = Array.isArray(data.sensors) ? (data.sensors as Array<Record<string, unknown>>) : [];
  const contributions = Array.isArray(data.contributions) ? (data.contributions as Array<Record<string, unknown>>) : [];

  return (
    <div className={cn("space-y-4", className)}>
      {/* Primary SPC Metric Grid */}
      {hasSpc ? (
        <div className="space-y-2.5">
          {/* 2-Column Row: Hotelling T² and SPE */}
          <div className="grid grid-cols-2 gap-2.5">
            {/* T² Metric */}
            {"t2" in data ? (
              <div className="rounded-[14px] border border-hairline bg-surface p-3.5 shadow-2xs">
                <div className="flex items-center justify-between text-ink-3">
                  <span className="text-[12px] font-[550]">Hotelling&apos;s T²</span>
                  <GaugeIcon className="size-3.5 text-signal" />
                </div>
                <div className="mt-2">
                  <span className="font-mono text-[22px] font-semibold tracking-tight text-ink">
                    {fmt(data.t2, 2)}
                  </span>
                </div>
                <p className="mt-1 text-[11px] text-ink-3">Multivariate variance</p>
              </div>
            ) : null}

            {/* SPE Metric */}
            {"spe" in data ? (
              <div className="rounded-[14px] border border-hairline bg-surface p-3.5 shadow-2xs">
                <div className="flex items-center justify-between text-ink-3">
                  <span className="text-[12px] font-[550]">SPE (Q-Stat)</span>
                  <BarChart3Icon className="size-3.5 text-amber-500" />
                </div>
                <div className="mt-2 flex items-baseline gap-1.5">
                  <span className="font-mono text-[22px] font-semibold tracking-tight text-ink">
                    {fmt(data.spe, 2)}
                  </span>
                  <span className="rounded bg-amber-500/10 px-1 py-0.2 font-mono text-[10px] font-medium text-amber-600 dark:text-amber-400">
                    excursion
                  </span>
                </div>
                <p className="mt-1 text-[11px] text-ink-3">Prediction error</p>
              </div>
            ) : null}
          </div>

          {/* Full-Width Failure Risk Card */}
          {"risk" in data ? (
            <div className="rounded-[14px] border border-fail/25 bg-fail-wash/20 p-3.5 shadow-2xs">
              <div className="flex items-center justify-between">
                <span className="inline-flex items-center gap-1.5 text-[12.5px] font-[600] text-ink">
                  <AlertTriangleIcon className="size-3.5 text-fail" />
                  Wafer Failure Risk
                </span>
                <span className="rounded-full border border-fail/30 bg-fail-wash px-2 py-0.5 font-mono text-[11px] font-semibold text-fail">
                  &gt; 7.9% Limit
                </span>
              </div>

              <div className="mt-2.5 flex items-baseline gap-2">
                <span className="font-mono text-[26px] font-bold tracking-tight text-fail">
                  {(Number(data.risk) * 100).toFixed(1)}%
                </span>
                <span className="text-[12px] text-ink-2 font-medium">
                  (+{(Number(data.risk) * 100 - 7.9).toFixed(1)}% above false-alarm threshold)
                </span>
              </div>

              {/* Visual Threshold Bar */}
              <div className="mt-2.5">
                <div className="relative h-2 w-full overflow-hidden rounded-full bg-surface-3">
                  <div
                    className="h-full rounded-full bg-fail transition-all duration-500"
                    style={{ width: `${Math.min(100, (Number(data.risk) / 0.15) * 100)}%` }}
                  />
                  {/* 7.9% threshold marker */}
                  <div
                    className="absolute top-0 bottom-0 w-0.5 bg-ink"
                    style={{ left: `${(0.079 / 0.15) * 100}%` }}
                    title="7.9% Threshold"
                  />
                </div>
                <div className="mt-1 flex justify-between font-mono text-[10.5px] text-ink-3">
                  <span>0%</span>
                  <span className="font-semibold text-ink">Threshold: 7.9%</span>
                  <span>15%</span>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      {/* Alarms Section */}
      {alarms.length > 0 ? (
        <div className="rounded-[14px] border border-amber-500/20 bg-amber-500/5 p-4">
          <div className="flex items-center justify-between">
            <span className="inline-flex items-center gap-1.5 text-[13px] font-[600] text-ink">
              <AlertTriangleIcon className="size-4 text-amber-500" />
              Active Process Alarms ({alarms.length})
            </span>
            <span className="rounded-full bg-amber-500/10 px-2 py-0.5 font-mono text-[11px] font-medium text-amber-600 dark:text-amber-400">
              Unit {String(alarms[0]?.unit_id ?? "1303")}
            </span>
          </div>

          <div className="mt-3 space-y-2">
            {alarms.map((alarm, idx) => (
              <div
                key={idx}
                className="rounded-[10px] border border-hairline bg-surface p-3 text-[12.5px]"
              >
                <div className="flex items-center justify-between font-mono">
                  <span className="font-semibold text-ink">
                    {String(alarm.alarm_id ?? "ALARM")}
                  </span>
                  <span className="rounded-full bg-signal-wash px-2 py-0.5 text-[11px] text-signal font-medium uppercase">
                    {String(alarm.status ?? "investigating")}
                  </span>
                </div>
                <p className="mt-1.5 text-ink-2">
                  {String(alarm.message ?? "Alarm condition triggered")}
                </p>
                <div className="mt-2 flex flex-wrap items-center gap-3 font-mono text-[11px] text-ink-3">
                  <span>Value: {fmt(alarm.value, 4)}</span>
                  <span>Limit: {fmt(alarm.limit, 4)}</span>
                  <span>Kind: {ALARM_KIND[String(alarm.kind)] ?? String(alarm.kind)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* General Parameter Summary */}
      <div className="rounded-[14px] border border-hairline bg-surface-2/50 p-4">
        <h4 className="text-[12.5px] font-[600] uppercase tracking-wider text-ink-3">
          Tool Parameter Overview
        </h4>
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-[12.5px] sm:grid-cols-3">
          {Object.entries(data)
            .filter(([k, v]) => !["t2", "spe", "risk", "alarms"].includes(k) && typeof v !== "object")
            .slice(0, 9)
            .map(([k, v]) => (
              <div key={k} className="rounded-md border border-hairline/60 bg-surface px-2.5 py-1.5">
                <dt className="text-[11px] font-medium text-ink-3 capitalize">
                  {k.replaceAll("_", " ")}
                </dt>
                <dd className="mt-0.5 font-mono text-[12px] font-medium text-ink truncate">
                  {String(v)}
                </dd>
              </div>
            ))}
        </dl>
      </div>
    </div>
  );
}
