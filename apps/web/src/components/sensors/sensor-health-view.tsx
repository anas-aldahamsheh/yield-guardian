"use client";

import { useQuery } from "@tanstack/react-query";
import type { HealthWindow, SensorHealth, SensorHealthReport } from "@yield-guardian/contracts";
import { useMemo, useState } from "react";

import { PageFrame, PageHeader, Panel, Reading } from "@/components/page";
import { EmptyState, ErrorState, Placeholder, QueryView } from "@/components/states";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useApi } from "@/lib/api/context";
import { q } from "@/lib/api/queries";
import { formatInt, formatNumber, formatPercent, formatPValue, plural } from "@/lib/format";
import { HEALTH_STATUS, HEALTH_STATUS_ORDER, type HealthStatus } from "@/lib/labels";
import { useParam } from "@/lib/use-param";
import { cn } from "@/lib/utils";

import { SensorField, statusColour } from "./sensor-field";
import { groupingMethodText, SensorGroupsTable } from "./sensor-groups";
import { SensorSeriesChart } from "./sensor-series-chart";
import { ScrollRegion } from "@/components/scroll-region";

const ALL = new Set<HealthStatus>(HEALTH_STATUS_ORDER);
const TABLE_ROWS = 20;

function parseStatuses(value: string | null): Set<HealthStatus> {
  if (!value) return ALL;
  const picked = value
    .split(",")
    .filter((s): s is HealthStatus => (HEALTH_STATUS_ORDER as readonly string[]).includes(s));
  return picked.length ? new Set(picked) : ALL;
}

export function SensorHealthView() {
  const api = useApi();
  const health = useQuery(q.sensorHealth(api));
  const [significantOnly, setSignificantOnly] = useState(false);
  const groups = useQuery(q.sensorGroups(api, { significant_only: significantOnly, limit: 50 }));
  const [sensorParam, setSensor] = useParam("sensor");
  const [statusParam, setStatusParam] = useParam("status");
  const visible = useMemo(() => parseStatuses(statusParam), [statusParam]);

  const report = health.data;
  const fallback =
    groups.data?.groups[0]?.representative ??
    report?.sensors.find((s) => s.status !== "ok" && s.status !== "dead")?.sensor ??
    report?.sensors[0]?.sensor ??
    null;
  const selected = sensorParam ?? fallback;

  const toggleStatus = (status: HealthStatus) => {
    const next = new Set(visible.size === ALL.size ? [] : visible);
    if (next.has(status)) next.delete(status);
    else next.add(status);
    setStatusParam(
      next.size === 0 || next.size === ALL.size
        ? null
        : HEALTH_STATUS_ORDER.filter((s) => next.has(s)).join(","),
    );
  };

  return (
    <PageFrame>
      <PageHeader
        title="Sensor health"
        description="The state of every SECOM sensor over the replayed period, by written rules: missing readings, flat lines, jumps and readings outside the reference range. Below, the groups of sensors associated with failure."
      />

      {health.isError ? (
        <ErrorState error={health.error} onRetry={() => void health.refetch()} />
      ) : !report ? (
        <div className="grid grid-cols-[minmax(0,1fr)] gap-street xl:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
          <Placeholder className="h-[420px]" label="Loading sensor health" />
          <Placeholder className="h-[420px]" label="Loading the sensor" />
        </div>
      ) : report.sensors.length === 0 ? (
        <EmptyState title="No sensor health yet">The SECOM bundle has no health report.</EmptyState>
      ) : (
        <div className="grid grid-cols-[minmax(0,1fr)] gap-street">
          <div className="grid grid-cols-[minmax(0,1fr)] gap-street xl:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
            <Panel
              title={`All ${formatInt(report.sensors.length)} sensors`}
              description={`S001 at the top left, ${formatInt(30)} to a row. Choose a status to fade the others; choose a tile to read the sensor.`}
            >
              <StatusFilter counts={report.counts} visible={visible} onToggle={toggleStatus} />
              <SensorField
                sensors={report.sensors}
                selected={selected}
                onSelect={setSensor}
                visible={visible}
                className="mt-4"
              />
              <details className="mt-4 text-[13px] leading-5 text-ink-2">
                <summary className="cursor-pointer text-ink">How a status is set</summary>
                <ul className="mt-2 grid grid-cols-[minmax(0,1fr)] gap-1.5 pl-4">
                  {report.rules.map((r) => (
                    <li key={r} className="list-disc">
                      {r}
                    </li>
                  ))}
                </ul>
              </details>
            </Panel>
            {selected ? <SensorDetail sensor={selected} report={report} /> : null}
          </div>

          <Panel
            title="Sensor groups associated with failure"
            description={
              groups.data
                ? groups.data.wording
                : "Correlated sensors reported together, because SHAP splits credit between near-duplicates."
            }
            actions={
              <div className="flex items-center gap-2">
                <Switch
                  id="significant-only"
                  checked={significantOnly}
                  onCheckedChange={setSignificantOnly}
                />
                <Label htmlFor="significant-only" className="text-[13px] text-ink-2">
                  Significant only
                </Label>
              </div>
            }
            bodyClassName="px-0 sm:px-0"
          >
            <QueryView
              query={groups}
              loading={<Placeholder className="mx-4 h-48 sm:mx-5" label="Loading sensor groups" />}
            >
              {(g) =>
                g.groups.length === 0 ? (
                  <EmptyState
                    className="mx-4 sm:mx-5"
                    title={significantOnly ? "No significant group" : "No sensor groups"}
                  >
                    {significantOnly
                      ? "No group survives the permutation test. Show all groups to read them."
                      : "The SECOM bundle has no sensor groups."}
                  </EmptyState>
                ) : (
                  <>
                    <p className="tnum mx-4 mb-3 text-[13px] leading-5 text-ink-2 sm:mx-5">
                      {plural(g.significant_groups, "significant group")} holding{" "}
                      {formatInt(g.sensors_in_significant_groups)} of {formatInt(g.sensors_total)}{" "}
                      sensors.
                    </p>
                    <SensorGroupsTable
                      data={g}
                      selectedSensor={selected}
                      onSelectSensor={setSensor}
                    />
                    <p className="mx-4 mt-3 max-w-[100ch] text-[12px] leading-4 text-ink-3 sm:mx-5">
                      {groupingMethodText(g.method)}
                    </p>
                  </>
                )
              }
            </QueryView>
          </Panel>

          <AttentionTable
            report={report}
            visible={visible}
            selected={selected}
            onSelect={setSensor}
          />
        </div>
      )}
    </PageFrame>
  );
}

function StatusFilter({
  counts,
  visible,
  onToggle,
}: {
  counts: SensorHealthReport["counts"];
  visible: ReadonlySet<HealthStatus>;
  onToggle: (s: HealthStatus) => void;
}) {
  const all = visible.size === ALL.size;
  return (
    <div role="group" aria-label="Statuses shown" className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {HEALTH_STATUS_ORDER.map((s) => {
        const on = visible.has(s);
        return (
          <button
            key={s}
            type="button"
            aria-pressed={!all && on}
            onClick={() => onToggle(s)}
            className={cn(
              "flex cursor-pointer flex-col items-start rounded-sm border px-2.5 py-1.5 text-left transition-colors",
              !all && on ? "border-ink bg-die-2" : "border-hairline hover:border-hairline-strong",
              !on && "opacity-55",
            )}
          >
            <span className="flex items-center gap-1.5 text-[12px] leading-4 text-ink-2">
              <span
                aria-hidden="true"
                className="size-2.5 rounded-[2px]"
                style={
                  s === "dead"
                    ? { boxShadow: `inset 0 0 0 1px ${statusColour(s)}` }
                    : { background: statusColour(s) }
                }
              />
              {HEALTH_STATUS[s]}
            </span>
            <span className="tnum text-[20px] leading-7 font-medium text-ink">
              {formatInt(counts[s])}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function SensorDetail({ sensor, report }: { sensor: string; report: SensorHealthReport }) {
  const api = useApi();
  const h = report.sensors.find((s) => s.sensor === sensor);
  const series = useQuery({
    ...q.sensorSeries(api, sensor),
    enabled: h != null && h.status !== "dead",
  });

  if (!h) {
    return (
      <Panel title={sensor}>
        <EmptyState title="Unknown sensor">
          The health report has no sensor {sensor}. Sensors run from S001 to S590.
        </EmptyState>
      </Panel>
    );
  }
  const status = h.status as HealthStatus;
  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          <span className="tnum">{h.sensor}</span>
          <span className="flex items-center gap-1.5 text-[13px] font-normal text-ink-2">
            <span
              aria-hidden="true"
              className="size-2.5 rounded-[2px]"
              style={
                status === "dead"
                  ? { boxShadow: `inset 0 0 0 1px ${statusColour(status)}` }
                  : { background: statusColour(status) }
              }
            />
            {HEALTH_STATUS[status]}
          </span>
          {series.data?.group_id ? (
            <span className="text-[13px] font-normal text-ink-3">
              in group {series.data.group_id}
            </span>
          ) : null}
        </span>
      }
      description={h.reasons.length ? h.reasons.join(". ") + "." : "No rule is triggered."}
    >
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
        <Reading label="Missing" value={formatPercent(h.missing_rate)} />
        <Reading
          label="Outside the reference range"
          value={
            h.out_of_reference_rate == null
              ? "No reference"
              : formatPercent(h.out_of_reference_rate)
          }
        />
        <Reading label="Jumps" value={formatInt(h.jump_unit_ids.length)} />
        <Reading
          label="Missing vs failure, q"
          value={
            h.missing_vs_failure?.q_value == null
              ? "not tested"
              : formatPValue(h.missing_vs_failure.q_value)
          }
          detail={
            h.missing_vs_failure?.odds_ratio != null
              ? `odds ratio ${formatNumber(h.missing_vs_failure.odds_ratio, 2)}`
              : undefined
          }
        />
      </dl>
      {h.stuck_value != null ? (
        <p className="tnum mt-3 text-[13px] leading-5 text-ink-2">
          Stuck at {formatNumber(h.stuck_value, 4)} in the flat-line weeks.
        </p>
      ) : null}

      <WeeklyMissing health={h} windows={report.windows} />

      <div className="mt-5">
        {status === "dead" ? (
          <p className="py-6 text-[14px] leading-5 text-ink-3">
            This sensor never gives a usable reading, so there is no series to draw.
          </p>
        ) : (
          <QueryView
            query={series}
            loading={<Placeholder className="h-[320px]" label={`Loading ${sensor}`} />}
          >
            {(s) =>
              s.points.length === 0 ? (
                <p className="py-6 text-[14px] leading-5 text-ink-3">
                  No units have left the line yet.
                </p>
              ) : (
                <SensorSeriesChart
                  series={s}
                  windows={report.windows}
                  flatlineWindows={h.flatline_windows}
                  jumpUnitIds={h.jump_unit_ids}
                />
              )
            }
          </QueryView>
        )}
      </div>
    </Panel>
  );
}

function WeeklyMissing({ health, windows }: { health: SensorHealth; windows: HealthWindow[] }) {
  if (!windows.length) return null;
  const max = Math.max(0.05, ...health.missing_by_window.map((v) => v ?? 0));
  return (
    <div className="mt-5">
      <h3 className="text-[13px] leading-5 text-ink-3">Missing readings by week</h3>
      <ol
        className="mt-1.5 grid grid-cols-[minmax(0,1fr)] gap-[3px]"
        style={{ gridTemplateColumns: `repeat(${windows.length}, minmax(0, 1fr))` }}
      >
        {windows.map((w, i) => {
          const v = health.missing_by_window[i] ?? null;
          const flat = health.flatline_windows.includes(w.window_id);
          const date = w.start.slice(5, 10);
          return (
            <li key={w.window_id} className="min-w-0">
              <div
                className={cn(
                  "relative h-9 rounded-[2px] bg-die-2",
                  flat && "outline outline-1 -outline-offset-1 outline-concern",
                )}
                title={`Week from ${w.start.slice(0, 10)}: ${v == null ? "no units" : `${formatPercent(v)} missing`}${flat ? ", flat line" : ""}`}
              >
                {v != null ? (
                  <span
                    aria-hidden="true"
                    className="absolute inset-x-0 bottom-0 rounded-[2px] bg-ink-2"
                    style={{ height: `${Math.max(v > 0 ? 6 : 0, (v / max) * 100)}%` }}
                  />
                ) : null}
              </div>
              <span
                aria-hidden="true"
                className={cn(
                  "tnum mt-0.5 block text-[10px] leading-3 whitespace-nowrap text-ink-3",
                  i % 2 === 1 && "invisible",
                )}
              >
                {date}
              </span>
              <span className="sr-only">
                Week from {w.start.slice(0, 10)}:{" "}
                {v == null ? "no units" : `${formatPercent(v)} missing`}
                {flat ? ", flat line" : ""}.
              </span>
            </li>
          );
        })}
      </ol>
      <p className="tnum mt-1 text-[12px] leading-4 text-ink-3">
        Bar height to {formatPercent(max, 0)}.{" "}
        {health.flatline_windows.length ? "Outlined weeks have a flat line." : ""}
      </p>
    </div>
  );
}

function AttentionTable({
  report,
  visible,
  selected,
  onSelect,
}: {
  report: SensorHealthReport;
  visible: ReadonlySet<HealthStatus>;
  selected: string | null;
  onSelect: (s: string) => void;
}) {
  const [all, setAll] = useState(false);
  const rank = (s: string) => HEALTH_STATUS_ORDER.indexOf(s as HealthStatus);
  const rows = report.sensors
    .filter(
      (s) =>
        visible.has(s.status as HealthStatus) && (visible.size < ALL.size || s.status !== "ok"),
    )
    .sort((a, b) => rank(a.status) - rank(b.status) || a.sensor.localeCompare(b.sensor));
  const shown = all ? rows : rows.slice(0, TABLE_ROWS);
  return (
    <Panel
      title={
        visible.size === ALL.size
          ? "Sensors with a status other than OK"
          : `Sensors: ${HEALTH_STATUS_ORDER.filter((s) => visible.has(s))
              .map((s) => HEALTH_STATUS[s])
              .join(", ")}`
      }
      description={`${plural(rows.length, "sensor")}, worst status first.`}
      bodyClassName="px-0 sm:px-0"
    >
      {rows.length === 0 ? (
        <EmptyState className="mx-4 sm:mx-5" title="No sensors">
          No sensor has this status.
        </EmptyState>
      ) : (
        <ScrollRegion label="Sensors by status">
          <table className="w-full min-w-[720px] border-collapse text-left text-[13px] leading-5">
            <caption className="sr-only">Sensors by status</caption>
            <thead>
              <tr className="border-y border-hairline text-[12px] text-ink-3">
                <th scope="col" className="px-4 py-2 font-normal sm:px-5">
                  Sensor
                </th>
                <th scope="col" className="px-2 py-2 font-normal">
                  Status
                </th>
                <th scope="col" className="px-2 py-2 font-normal">
                  Why
                </th>
                <th scope="col" className="px-2 py-2 text-right font-normal">
                  Missing
                </th>
                <th scope="col" className="px-2 py-2 text-right font-normal">
                  Outside range
                </th>
                <th scope="col" className="px-4 py-2 text-right font-normal sm:px-5">
                  Missing vs failure, q
                </th>
              </tr>
            </thead>
            <tbody>
              {shown.map((s) => (
                <tr
                  key={s.sensor}
                  className={cn(
                    "border-b border-hairline last:border-b-0 hover:bg-die-2",
                    selected === s.sensor && "bg-die-2",
                  )}
                >
                  <th scope="row" className="px-4 py-2 font-normal sm:px-5">
                    <button
                      type="button"
                      onClick={() => {
                        onSelect(s.sensor);
                        window.scrollTo({ top: 0, behavior: "smooth" });
                      }}
                      className="tnum cursor-pointer text-ink underline decoration-hairline-strong underline-offset-4"
                    >
                      {s.sensor}
                    </button>
                  </th>
                  <td className="px-2 py-2 whitespace-nowrap text-ink-2">
                    {HEALTH_STATUS[s.status]}
                  </td>
                  <td className="px-2 py-2 text-ink-2">
                    {s.reasons.join("; ") || <span className="text-ink-3">None</span>}
                  </td>
                  <td className="tnum px-2 py-2 text-right text-ink-2">
                    {formatPercent(s.missing_rate)}
                  </td>
                  <td className="tnum px-2 py-2 text-right text-ink-2">
                    {s.out_of_reference_rate == null ? "–" : formatPercent(s.out_of_reference_rate)}
                  </td>
                  <td className="tnum px-4 py-2 text-right text-ink-2 sm:px-5">
                    {s.missing_vs_failure?.q_value == null ? (
                      <span className="text-ink-3">not tested</span>
                    ) : (
                      formatPValue(s.missing_vs_failure.q_value)
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length > TABLE_ROWS && !all ? (
            <button
              type="button"
              onClick={() => setAll(true)}
              className="mx-4 mt-3 cursor-pointer text-[13px] font-medium text-ink sm:mx-5"
            >
              Show all {formatInt(rows.length)}
            </button>
          ) : null}
        </ScrollRegion>
      )}
    </Panel>
  );
}
