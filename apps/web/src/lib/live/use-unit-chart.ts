"use client";

import { useQuery } from "@tanstack/react-query";

import { getUnitChart } from "./api";
import { stageResult, type RunState, type UnitChartView } from "./run-state";

/**
 * One unit's control-chart result with its standardised readings. The run's result carries them
 * for the first 200 units; for any other unit (or one whose details are still being read just
 * after a reload) they are read from the API once, when shown.
 */
export function useUnitChart(
  state: RunState | null,
  index: number | null,
): UnitChartView | undefined {
  const row =
    state && index != null ? stageResult(state, "control_charts")?.units[index] : undefined;
  const needsFetch = Boolean(state && row && row.z == null);
  const query = useQuery({
    queryKey: ["runs", state?.runId, "units", index, "chart"],
    queryFn: ({ signal }) => getUnitChart(state!.runId, index!, { signal }),
    enabled: needsFetch,
    staleTime: Infinity,
  });
  if (!row) return undefined;
  return row.z != null ? row : (query.data ?? row);
}
