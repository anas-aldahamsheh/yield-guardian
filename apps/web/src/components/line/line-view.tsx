"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { PageFrame, PageHeader, Panel } from "@/components/page";
import { ErrorState, Placeholder } from "@/components/states";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useApi } from "@/lib/api/context";
import { q } from "@/lib/api/queries";
import { formatInt, formatPlantTime, formatProbability } from "@/lib/format";
import { useLiveLine } from "@/lib/line/use-live-line";
import { LINE_WINDOWS } from "@/lib/line/windows";

import { ConnectionStatus } from "./connection-status";
import { LineCharts } from "./line-charts";
import { LineKpis } from "./line-kpis";
import { OpenAlarms } from "./open-alarms";
import { RecentUnits } from "./recent-units";
import { RootCause } from "./root-cause";

export function LineView() {
  const api = useApi();
  const [size, setSize] = useState<number>(LINE_WINDOWS[0]);
  const { query, connection, lastUnitAt } = useLiveLine(size);
  const fdc = useQuery(q.fdcModel(api));
  const state = query.data;
  const newest = lastUnitAt != null ? (state?.recent.at(-1)?.sequence ?? null) : null;

  return (
    <PageFrame>
      <PageHeader
        title="Line"
        description="Every unit as it leaves the line, checked against multivariate control limits fitted on a reference period, with the sensors behind each excursion."
        meta={
          state ? (
            <span className="tnum">
              Unit {formatInt(state.clock.position)} of {formatInt(state.clock.units_total)}, replay cycle{" "}
              {formatInt(state.clock.cycle)}. Plant time {formatPlantTime(state.clock.plant_time)}.
            </span>
          ) : null
        }
        actions={<ConnectionStatus connection={connection} hasState={state != null} />}
      />

      {query.isError && !state ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : !state ? (
        <div className="grid gap-street">
          <Placeholder className="h-28" label="Loading the line" />
          <Placeholder className="h-[440px]" label="Loading the control charts" />
        </div>
      ) : (
        <div className="grid gap-street">
          <LineKpis kpis={state.kpis} className="mb-2" />
          <div className="grid gap-street xl:grid-cols-[minmax(0,1fr)_380px]">
            <Panel
              live={connection === "live"}
              className="xl:self-start"
              title="Control charts (FDC)"
              description={`Limits at 99% and 99.9% of the reference period. The failure-risk trace is an experimental signal, not a claim of predictive skill; Methods compares its precision with the no-skill rate. Its threshold is ${formatProbability(state.operating_point.threshold)}, ${state.operating_point.label}.`}
              actions={
                <ToggleGroup
                  type="single"
                  variant="outline"
                  size="sm"
                  value={String(size)}
                  onValueChange={(v) => v && setSize(Number(v))}
                  aria-label="Units shown"
                >
                  {LINE_WINDOWS.map((w) => (
                    <ToggleGroupItem key={w} value={String(w)} className="tnum px-2.5">
                      {w} units
                    </ToggleGroupItem>
                  ))}
                </ToggleGroup>
              }
            >
              {fdc.isError ? (
                <ErrorState compact error={fdc.error} onRetry={() => void fdc.refetch()} className="mb-3" />
              ) : null}
              <LineCharts state={state} limits={fdc.data?.limits} newest={newest} />
              {fdc.data ? (
                <p className="mt-4 text-[12px] leading-4 text-ink-3">
                  {fdc.data.method}. {formatInt(fdc.data.n_components)} components explain{" "}
                  {formatProbability(fdc.data.explained_variance)} of the variance of {formatInt(fdc.data.features)} sensors.
                </p>
              ) : null}
            </Panel>
            <div className="grid min-w-0 content-start gap-street">
              <RootCause alarms={state.open_alarms} />
              <OpenAlarms alarms={state.open_alarms} />
            </div>
          </div>
          <RecentUnits units={state.recent} lag={state.clock.final_test_lag_units} />
        </div>
      )}
    </PageFrame>
  );
}
