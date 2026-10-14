"use client";

import { useQuery } from "@tanstack/react-query";
import type { FdcContributions, UnitDetail } from "@yield-guardian/contracts";
import Link from "next/link";
import { useState } from "react";

import { ShapWaterfall } from "@/components/charts/shap-waterfall";
import { PageFrame, PageHeader, Panel, Reading } from "@/components/page";
import { EmptyState, ErrorState, Placeholder, QueryView } from "@/components/states";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useApi } from "@/lib/api/context";
import { ApiError } from "@/lib/api/errors";
import { useStartInvestigation } from "@/lib/api/investigations";
import { q } from "@/lib/api/queries";
import { useSession, useStartGuestSession } from "@/lib/api/session";
import { formatInt, formatPercent, formatPlantTime, formatProbability, formatReading, formatSigned } from "@/lib/format";
import { ALARM_KIND, BAND_NAME, BLOCK_NAME } from "@/lib/labels";
import { cn } from "@/lib/utils";

export function UnitView({ unitId }: { unitId: number }) {
  const api = useApi();
  const unit = useQuery(q.unit(api, unitId));

  if (unit.isError) {
    const notFound = unit.error instanceof ApiError && unit.error.status === 404;
    return (
      <PageFrame>
        <PageHeader title={`Unit ${formatInt(unitId)}`} />
        <ErrorState error={unit.error} onRetry={notFound ? undefined : () => void unit.refetch()} />
      </PageFrame>
    );
  }
  if (!unit.data) {
    return (
      <PageFrame>
        <Placeholder className="mb-6 h-24" label="Loading the unit" />
        <Placeholder className="h-[480px]" label="Loading the explanation" />
      </PageFrame>
    );
  }
  const u = unit.data;
  return (
    <PageFrame>
      <Link href="/line" className="mb-3 inline-block text-[13px] text-ink-2 underline decoration-hairline-strong underline-offset-4 hover:text-ink">
        Line
      </Link>
      <PageHeader
        title={`Unit ${formatInt(u.unit_id)}`}
        description={`Left the line at ${formatPlantTime(u.timestamp)} (plant time). ${BLOCK_NAME[u.block] ?? u.block}.`}
        actions={<InvestigateUnit unit={u} />}
      />
      <UnitReadings unit={u} />
      <div className="mt-street grid gap-street xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <Panel
          title="Why the model scores this unit as it does"
          description="TreeSHAP contributions of the sensors that moved the failure score most. An association in historical data, not a cause."
        >
          {u.explanation_available ? (
            <Explanation unitId={u.unit_id} />
          ) : (
            <EmptyState title="No explanation for this unit">
              {u.risk == null ? "Units in the warm-up period have no out-of-sample risk, so there is nothing to explain." : "The model bundle has no explanation for this unit."}
            </EmptyState>
          )}
        </Panel>
        <div className="grid min-w-0 content-start gap-street">
          <Contributions unitId={u.unit_id} />
          <UnitRecords unit={u} />
        </div>
      </div>
    </PageFrame>
  );
}

function UnitReadings({ unit: u }: { unit: UnitDetail }) {
  const r = u.risk_detail;
  return (
    <section aria-label="Readings" className="panel px-4 py-4 sm:px-5">
      <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3 lg:grid-cols-6">
        <Reading
          label="Failure risk"
          value={u.risk == null ? "Warm-up" : formatProbability(u.risk)}
          detail={u.risk_band ? BAND_NAME[u.risk_band] : undefined}
        />
        <Reading
          label="Against the threshold"
          value={r.above_threshold == null ? "–" : r.above_threshold ? "Above" : "Below"}
          detail={`${formatProbability(r.operating_point.threshold)}, ${r.operating_point.label}`}
        />
        <Reading label="Hotelling T²" value={formatReading(u.t2)} />
        <Reading label="SPE (Q)" value={formatReading(u.spe)} />
        <Reading
          label="Control charts"
          value={u.fdc_alarm === "alarm" ? "Beyond 99.9%" : u.fdc_alarm === "warning" ? "Beyond 99%" : "Within limits"}
          detail={[u.ewma_alarm && "EWMA", u.cusum_alarm && "CUSUM"].filter(Boolean).join(", ") || undefined}
        />
        <Reading
          label="Final test"
          value={
            u.final_test === "fail" ? <span className="text-fail">Fail</span> : u.final_test === "pass" ? <span className="text-pass">Pass</span> : "Pending"
          }
        />
      </dl>
      <p className="mt-4 text-[13px] leading-5 text-ink-3">
        {formatInt(u.sensors_measured)} sensors measured, {formatInt(u.sensors_missing)} missing.{" "}
        {r.risk_source ? `Risk is ${r.risk_source === "oof" ? "out-of-fold" : `scored on the ${r.risk_source} block`}, calibrated with ${r.calibration ?? "Platt"} scaling.` : ""}{" "}
        {r.note ?? ""}
      </p>
    </section>
  );
}

function Explanation({ unitId }: { unitId: number }) {
  const api = useApi();
  const explanation = useQuery(q.explanation(api, unitId));
  return (
    <QueryView query={explanation} loading={<Placeholder className="h-96" label="Loading the explanation" />}>
      {(e) => (
        <>
          <ShapWaterfall explanation={e} />
          {e.groups.length ? (
            <div className="mt-6">
              <h3 className="text-[14px] leading-5 font-semibold text-ink">Correlated sensor groups</h3>
              <p className="text-[13px] leading-5 text-ink-3">Members of one group move together, so their contributions are summed.</p>
              <ul className="mt-2 grid gap-1 text-[13px] leading-5">
                {e.groups.slice(0, 6).map((g) => (
                  <li key={g.group_id} className="tnum flex justify-between gap-4 border-t border-hairline py-1.5">
                    <span className="text-ink-2">
                      <span className="text-ink">{g.group_id}</span> {g.sensors.join(", ")}
                    </span>
                    <span className={cn(g.shap >= 0 ? "text-ink" : "text-ink-2")}>{formatSigned(g.shap)}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      )}
    </QueryView>
  );
}

function Contributions({ unitId }: { unitId: number }) {
  const api = useApi();
  const [statistic, setStatistic] = useState<"t2" | "spe">("t2");
  const query = useQuery(q.contributions(api, unitId, statistic));
  return (
    <Panel
      title="Sensors behind the control-chart statistic"
      description="Each sensor's share of the unit's statistic, against the reference period."
      actions={
        <ToggleGroup type="single" variant="outline" size="sm" value={statistic} onValueChange={(v) => v && setStatistic(v as "t2" | "spe")} aria-label="Statistic">
          <ToggleGroupItem value="t2" className="px-2.5">T²</ToggleGroupItem>
          <ToggleGroupItem value="spe" className="px-2.5">SPE</ToggleGroupItem>
        </ToggleGroup>
      }
    >
      <QueryView query={query} loading={<Placeholder className="h-64" label="Loading contributions" />}>
        {(c) => <ContributionTable data={c} />}
      </QueryView>
    </Panel>
  );
}

function ContributionTable({ data }: { data: FdcContributions }) {
  const max = Math.max(...data.contributions.map((c) => c.share), data.other_share, 0.01);
  return (
    <>
      <p className="tnum mb-3 text-[13px] leading-5 text-ink-2">
        {data.statistic === "t2" ? "T²" : "SPE"} {formatReading(data.value)} against limits {formatReading(data.limit_99, 3)} (99%) and{" "}
        {formatReading(data.limit_999, 3)} (99.9%).
      </p>
      <table className="w-full border-collapse text-left text-[13px] leading-5">
        <caption className="sr-only">Contributions by sensor</caption>
        <thead>
          <tr className="text-[12px] text-ink-3">
            <th scope="col" className="py-1.5 pr-3 font-normal">Sensor</th>
            <th scope="col" className="w-[40%] py-1.5 pr-3 font-normal">Share</th>
            <th scope="col" className="py-1.5 pr-3 text-right font-normal">Reading</th>
            <th scope="col" className="py-1.5 text-right font-normal">Reference median</th>
          </tr>
        </thead>
        <tbody>
          {data.contributions.map((c) => (
            <tr key={c.sensor} className="border-t border-hairline">
              <th scope="row" className="tnum py-1.5 pr-3 font-normal">
                <Link href={`/sensors?sensor=${c.sensor}`} className="text-ink underline decoration-hairline-strong underline-offset-4">
                  {c.sensor}
                </Link>
              </th>
              <td className="py-1.5 pr-3">
                <span className="flex items-center gap-2">
                  <span className="h-2.5 rounded-[2px] bg-ink-2" style={{ width: `${(c.share / max) * 100}%`, minWidth: 2 }} aria-hidden="true" />
                  <span className="tnum shrink-0 text-ink-2">{formatPercent(c.share)}</span>
                </span>
              </td>
              <td className="tnum py-1.5 pr-3 text-right text-ink">{c.value == null ? <span className="text-ink-3">Not measured</span> : formatReading(c.value)}</td>
              <td className="tnum py-1.5 text-right text-ink-3">{formatReading(c.reference_median)}</td>
            </tr>
          ))}
          <tr className="border-t border-hairline">
            <th scope="row" className="py-1.5 pr-3 font-normal text-ink-3">Others</th>
            <td className="py-1.5 pr-3">
              <span className="flex items-center gap-2">
                <span className="h-2.5 rounded-[2px] bg-mark-muted" style={{ width: `${(data.other_share / max) * 100}%`, minWidth: 2 }} aria-hidden="true" />
                <span className="tnum shrink-0 text-ink-3">{formatPercent(data.other_share)}</span>
              </span>
            </td>
            <td />
            <td />
          </tr>
        </tbody>
      </table>
      <p className="mt-3 text-[12px] leading-4 text-ink-3">{data.method}.</p>
    </>
  );
}

function UnitRecords({ unit: u }: { unit: UnitDetail }) {
  return (
    <Panel title="Alarms and investigations">
      {u.alarms.length === 0 && u.investigation_ids.length === 0 ? (
        <p className="text-[14px] leading-5 text-ink-3">No alarm was raised on this unit.</p>
      ) : (
        <ul className="grid gap-2 text-[14px] leading-5">
          {u.alarms.map((a) => (
            <li key={a.alarm_id} className="border-t border-hairline pt-2">
              <span className="font-medium text-ink">{ALARM_KIND[a.kind] ?? a.kind}</span>{" "}
              <span className="text-ink-3">{a.severity === "alarm" ? "alarm" : "warning"}, {a.status}</span>
              <p className="text-ink-2">{a.message}</p>
            </li>
          ))}
          {u.investigation_ids.map((id) => (
            <li key={id} className="border-t border-hairline pt-2">
              <Link href={`/investigations/${id}`} className="text-ink underline decoration-hairline-strong underline-offset-4">
                Open investigation {id.slice(0, 12)}…
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function InvestigateUnit({ unit }: { unit: UnitDetail }) {
  const { canAct } = useSession();
  const guest = useStartGuestSession();
  const start = useStartInvestigation();
  if (!canAct) {
    return (
      <Button variant="outline" onClick={() => guest.mutate()} disabled={guest.isPending}>
        {guest.isPending ? "Signing in…" : "Try as engineer to investigate"}
      </Button>
    );
  }
  return (
    <Button onClick={() => start.mutate({ kind: "unit", ref: String(unit.unit_id) })} disabled={start.isPending}>
      {start.isPending ? "Starting…" : "Investigate this unit"}
    </Button>
  );
}
