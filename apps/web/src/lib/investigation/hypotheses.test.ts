import type { Investigation, Report, WorkOrder } from "@yield-guardian/contracts";
import { describe, expect, it } from "vitest";

import { fixture } from "@/mocks/fixtures";

import { hypothesisEvidenceIds, readConfirmedCause, readEvidence, readHypotheses } from "./hypotheses";

const report = fixture<Investigation>("get_investigation").report!;
const order = fixture<{ items: WorkOrder[] }>("list_work_orders").items[0]!;

// Test inputs only: the shape of PLAN_V2 §7.3, written here to exercise the reader.
const withHypotheses = (hypotheses: unknown) => ({ ...report, hypotheses }) as unknown as Report;

describe("readHypotheses", () => {
  it("is null for a report without the field, and empty for an empty table", () => {
    expect(readHypotheses(withHypotheses(undefined))).toBeNull();
    expect(readHypotheses(report)).toEqual([]);
    expect(readHypotheses(null)).toBeNull();
    expect(readHypotheses(withHypotheses([]))).toEqual([]);
  });

  it("reads the plan's shape with evidence IDs", () => {
    const rows = readHypotheses(
      withHypotheses([
        { hypothesis: "Edge exposure drift", source_ids: ["wu2015"], evidence_for: ["E1", "E2"], evidence_against: ["E3"], assessment: "supported" },
      ]),
    );
    expect(rows).toEqual([
      {
        hypothesis: "Edge exposure drift",
        sourceIds: ["wu2015"],
        evidenceFor: [
          { text: null, evidenceIds: ["E1"] },
          { text: null, evidenceIds: ["E2"] },
        ],
        evidenceAgainst: [{ text: null, evidenceIds: ["E3"] }],
        assessment: "supported",
      },
    ]);
    expect(hypothesisEvidenceIds(rows!)).toEqual(["E1", "E2", "E3"]);
  });

  it("reads sentences, with or without their evidence", () => {
    expect(readEvidence(["Lot repeats the pattern", { text: "Confidence is high", evidence_ids: ["E4", "nope"] }, { claim: "Similar wafers agree", evidence_id: "E5" }, {}, 3])).toEqual([
      { text: "Lot repeats the pattern", evidenceIds: [] },
      { text: "Confidence is high", evidenceIds: ["E4"] },
      { text: "Similar wafers agree", evidenceIds: ["E5"] },
    ]);
  });

  it("drops rows without a hypothesis and unknown assessments", () => {
    const rows = readHypotheses(withHypotheses([{ source_ids: [] }, { hypothesis: "Chuck contamination", assessment: "proven" }]));
    expect(rows).toHaveLength(1);
    expect(rows![0]!.assessment).toBeNull();
    expect(rows![0]!.evidenceFor).toEqual([]);
  });
});

describe("readConfirmedCause", () => {
  it("is null while the work order has no confirmed cause", () => {
    expect(readConfirmedCause(order)).toBeNull();
    expect(readConfirmedCause({ ...order, confirmed_cause: null } as WorkOrder)).toBeNull();
    expect(readConfirmedCause({ ...order, confirmed_cause: "  " } as unknown as WorkOrder)).toBeNull();
  });

  it("reads a sentence or an object with the hypothesis it confirms", () => {
    expect(readConfirmedCause({ ...order, confirmed_cause: "Worn chuck pins" } as unknown as WorkOrder)?.text).toBe("Worn chuck pins");
    const rows = readHypotheses(withHypotheses([{ hypothesis: "Chuck contamination", assessment: "inconclusive" }]));
    expect(
      readConfirmedCause({ ...order, confirmed_cause: { text: "Particles on the chuck", hypothesis_index: 0, confirmed_by: "Engineer" } } as WorkOrder, rows),
    ).toEqual({ text: "Particles on the chuck", hypothesis: "Chuck contamination", confirmedBy: "Engineer", confirmedAt: null });
  });
});
