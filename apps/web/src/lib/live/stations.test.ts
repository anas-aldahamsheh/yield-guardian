import { describe, expect, it } from "vitest";

import { RUN_ID, sampleEvents } from "../../../e2e/story/fixture";

import { reduceRunEvents, stageResult } from "./run-state";
import {
  countsAsUnknown,
  energyUnknown,
  formatApart,
  lineStatus,
  needsSentence,
  needsText,
  patternCounts,
  summarizeLine,
  unknownSentence,
} from "./stations";

describe("what a skipped stage needs", () => {
  it("puts the API's phrase after the stage", () => {
    expect(needsText("the lot test", "needs at least two wafers of the same lot", "")).toBe(
      "the lot test needs at least two wafers of the same lot",
    );
    expect(needsSentence("needs wafer maps", "")).toBe("Needs wafer maps.");
  });

  it("lets the API's own sentence stand", () => {
    const sentence =
      "Drift and sensor health need a timestamp on every unit; 1 of 40 units have none (the first is unit 7).";
    expect(needsText("drift", sentence, "")).toBe(sentence.slice(0, -1));
    expect(needsSentence(sentence, "")).toBe(sentence);
  });

  it("falls back when the stage says nothing", () => {
    expect(needsText("The control charts", null, "needs more input")).toBe(
      "The control charts needs more input",
    );
  });
});

describe("the wafer test station", () => {
  const state = reduceRunEvents(RUN_ID, sampleEvents);
  const pattern = stageResult(state, "wafer_pattern")!;
  const lot = stageResult(state, "lot")!.lots[0]!;

  it("counts wafers by pattern as the lot test does", () => {
    const counts = patternCounts(pattern.wafers, stageResult(state, "lot"));
    expect(Object.fromEntries(counts)).toEqual(
      Object.fromEntries(Object.entries(lot.pattern_counts).filter(([, n]) => n > 0)),
    );
    expect(energyUnknown(pattern, lot)).toBe(0);
    expect(pattern.wafers.some((w) => countsAsUnknown(w, pattern))).toBe(false);
    // Without the lot test, each wafer counts as its predicted pattern.
    expect(counts).toEqual(patternCounts(pattern.wafers));
  });

  it("follows the lot test where its energy rule counts a predicted pattern as unknown", () => {
    // The fixture's lot as it would be with one wafer's energy score above the threshold.
    const raised = { ...pattern.wafers[0]!, energy_score: pattern.energy_threshold + 0.0004 };
    const above = { ...pattern, wafers: [raised, ...pattern.wafers.slice(1)] };
    const label = raised.top_label;
    const item = {
      ...lot,
      pattern_counts: { ...lot.pattern_counts, [label]: lot.pattern_counts[label]! - 1 },
    };
    expect(countsAsUnknown(raised, above)).toBe(true);
    expect(energyUnknown(above, item)).toBe(1);
    const counts = new Map(
      patternCounts(above.wafers, { ...stageResult(state, "lot")!, lots: [item] }),
    );
    expect(counts.get(label)).toBe(lot.pattern_counts[label]! - 1);
    // A wafer with no predicted pattern changes no count.
    expect(countsAsUnknown({ ...raised, top_label: "none" }, above)).toBe(false);
  });

  it("writes two close numbers apart", () => {
    expect(formatApart(-2.6173, -2.6177)).toEqual(["-2.617", "-2.618"]);
    expect(formatApart(-1.9, -2.6177)).toEqual(["-1.90", "-2.62"]);
  });

  it("keeps the prediction of a map that scores unknown and adds a caution", () => {
    const unknown = pattern.wafers.filter((w) => w.is_unknown).length;
    expect(unknown).toBeGreaterThan(0);
    const [, , wafers] = summarizeLine(state);
    const defect = pattern.wafers.filter((w) => w.top_label !== "none").length;
    expect(wafers!.sentence).toContain(`${defect} of ${pattern.wafers.length} wafers show`);
    expect(wafers!.sentence).toContain(unknownSentence(unknown));
  });

  it("writes the caution for one wafer and for several", () => {
    expect(unknownSentence(1)).toBe(
      "1 wafer looks unlike the maps the model learned from, so check it by eye.",
    );
    expect(unknownSentence(17)).toBe(
      "17 wafers look unlike the maps the model learned from, so check those by eye.",
    );
  });
});

describe("the line's status", () => {
  const state = reduceRunEvents(RUN_ID, sampleEvents);

  it("says when nothing more will arrive", () => {
    expect(lineStatus(state, false)).toBe("Running: each station shows its result as it arrives.");
    expect(lineStatus(state, true)).toBe(
      "The run is finished: every station has its result, and nothing more will arrive.",
    );
  });
});

describe("the wafer test sentence", () => {
  const state = reduceRunEvents(RUN_ID, sampleEvents);
  const pattern = stageResult(state, "wafer_pattern")!;
  // The fixture's lot with its labels changed, to cover each way of naming the patterns.
  const relabel = (labels: string[]) =>
    ({
      ...state,
      stages: {
        ...state.stages,
        wafer_pattern: {
          ...state.stages.wafer_pattern,
          result: {
            ...pattern,
            wafers: pattern.wafers.map((w, i) => ({
              ...w,
              is_unknown: false,
              top_label: labels[i] ?? "none",
            })),
          },
        },
        lot: {
          ...state.stages.lot,
          status: "skipped" as const,
          result: null,
          needs: "needs at least two wafers of the same lot",
        },
      },
    }) as typeof state;
  const sentence = (labels: string[]) => summarizeLine(relabel(labels))[2]!.sentence;

  it("names one pattern, lists a few, and gives the most frequent of many", () => {
    expect(sentence(["Center", "Center"])).toContain("2 of 6 wafers show Center.");
    expect(sentence(["Loc", "Scratch"])).toContain(
      "2 of 6 wafers show a defect pattern: Loc (1) and Scratch (1).",
    );
    expect(sentence(["Loc", "Loc", "Scratch", "Donut", "Random"])).toContain(
      "5 of 6 wafers show a defect pattern, most often Loc (2).",
    );
    expect(sentence(["Loc", "Scratch", "Donut", "Random"])).toContain(
      "most often Donut, Loc, Random and Scratch (1 each).",
    );
    expect(sentence([])).toContain("; none of the 6 wafers shows a defect pattern.");
  });
});
