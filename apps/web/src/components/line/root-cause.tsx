"use client";

import { useQuery } from "@tanstack/react-query";
import type { Alarm } from "@yield-guardian/contracts";
import Link from "next/link";

import { ContributionTable } from "@/components/fdc/contribution-table";
import { Panel } from "@/components/page";
import { EmptyState, Placeholder, QueryView } from "@/components/states";
import { useApi } from "@/lib/api/context";
import { q } from "@/lib/api/queries";
import { formatInt, formatPlantTime } from "@/lib/format";
import { ALARM_KIND } from "@/lib/labels";
import { unitHref } from "@/lib/routes";

const TOP = 8;

/** The newest open T² or SPE alarm (alarms arrive newest first). */
export function newestControlAlarm(alarms: Alarm[]): (Alarm & { kind: "t2" | "spe" }) | undefined {
  return alarms.find((a): a is Alarm & { kind: "t2" | "spe" } => a.kind === "t2" || a.kind === "spe");
}

/**
 * Root cause, as far as the control charts can say it: which sensors carry the newest
 * control-chart alarm. Contributions are associations with the statistic, not causes.
 */
export function RootCause({ alarms, className }: { alarms: Alarm[]; className?: string }) {
  const api = useApi();
  const alarm = newestControlAlarm(alarms);
  const query = useQuery({ ...q.contributions(api, alarm?.unit_id ?? 0, alarm?.kind ?? "t2", TOP), enabled: alarm != null });

  return (
    <Panel
      title="Sensors behind the newest control-chart alarm"
      description={
        alarm ? (
          <>
            <span className="tnum">
              {ALARM_KIND[alarm.kind]} {alarm.severity === "alarm" ? "alarm" : "warning"} on{" "}
              <Link href={unitHref(alarm.unit_id)} className="text-ink underline decoration-hairline-strong underline-offset-4">
                unit {formatInt(alarm.unit_id)}
              </Link>
              , {formatPlantTime(alarm.timestamp)}.
            </span>{" "}
            The sensors that account for most of the statistic. They move with the alarm; that does not make them its cause.
          </>
        ) : (
          "The sensors that account for most of a control-chart statistic, for the newest T² or SPE alarm."
        )
      }
      className={className}
    >
      {alarm ? (
        <QueryView query={query} loading={<Placeholder className="h-64" label="Loading contributions" />} compactError>
          {(c) => <ContributionTable data={c} />}
        </QueryView>
      ) : (
        <EmptyState title="No open control-chart alarm">
          When a unit crosses the T² or SPE limit, the sensors that carry it are listed here.
        </EmptyState>
      )}
    </Panel>
  );
}
