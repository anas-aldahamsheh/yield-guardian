import { describe, expect, it } from "vitest";

import { RUN_ID, sampleEvents } from "../../../e2e/story/fixture";
import { reduceRunEvents, stageResult } from "@/lib/live/run-state";

import { lotTestCaution, waferVerdict } from "./drawer-wafers";

describe("the verdict on one wafer", () => {
  const state = reduceRunEvents(RUN_ID, sampleEvents);
  const pattern = stageResult(state, "wafer_pattern")!;
  const unknown = pattern.wafers.find((w) => w.is_unknown)!;
  const known = pattern.wafers.find((w) => !w.is_unknown && w.top_label !== "none")!;

  it("keeps the prediction and adds the caution for a map unlike the training maps", () => {
    const verdict = waferVerdict(unknown, pattern, true);
    expect(verdict).toMatch(/^Center at /);
    expect(verdict).toContain("so check it by eye.");
    expect(waferVerdict(known, pattern, true)).not.toContain("check it by eye");
  });

  it("says when the lot test counts a predicted pattern as unknown, once it has covered the lot", () => {
    // The fixture's wafer as it would be with its energy score above the threshold.
    const raised = { ...known, energy_score: pattern.energy_threshold + 0.5 };
    expect(lotTestCaution(known, pattern)).toBeNull();
    expect(lotTestCaution(raised, pattern)).toMatch(
      /^The lot test counts it as unknown, not as Center: its energy score -?\d\.\d+ is above the test's threshold -2\.62\.$/,
    );
    expect(waferVerdict(raised, pattern, true)).toContain("The lot test counts it as unknown");
    expect(waferVerdict(raised, pattern, false)).not.toContain("lot test");
  });
});
