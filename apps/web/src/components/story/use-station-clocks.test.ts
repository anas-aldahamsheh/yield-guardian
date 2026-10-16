import { describe, expect, it } from "vitest";

import { sampleEvents, snapshotOf } from "../../../e2e/story/fixture";
import { runStateFrom } from "@/lib/live/run-state";

import { computingWhenRead } from "./use-station-clocks";

describe("a station's clock after a reload", () => {
  const started = sampleEvents.findIndex(
    (e) => e.type === "stage_started" && e.stage === "control_charts",
  );

  it("goes on from what the stage had computed when the run was read", () => {
    const snapshot = {
      ...snapshotOf(sampleEvents.slice(0, started + 1)),
      read_at: new Date(Date.parse(sampleEvents[started]!.at) + 2_500).toISOString(),
    };
    const state = runStateFrom(snapshot);
    expect(state.stages.control_charts.status).toBe("running");
    expect(computingWhenRead(state, "monitoring")).toBe(2_500);
    // Nothing runs at the other stations.
    expect(computingWhenRead(state, "wafer_test")).toBe(0);
  });

  it("starts from nothing without a stored state, or for a stage started after the read", () => {
    const snapshot = snapshotOf(sampleEvents.slice(0, started + 1));
    expect(computingWhenRead(runStateFrom({ ...snapshot, read_at: null }), "monitoring")).toBe(0);
    const early = new Date(Date.parse(sampleEvents[started]!.at) - 1_000).toISOString();
    expect(computingWhenRead(runStateFrom({ ...snapshot, read_at: early }), "monitoring")).toBe(0);
  });
});
