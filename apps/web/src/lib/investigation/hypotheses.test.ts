import type { Hypothesis, Investigation, Report, WorkOrder } from "@yield-guardian/contracts";
import { describe, expect, it } from "vitest";

import { fixture } from "@/mocks/fixtures";

import {
  confirmedCauseUpdate,
  confirmedHypothesis,
  hypothesisEvidenceIds,
  readConfirmedCause,
  readHypotheses,
} from "./hypotheses";

const report = fixture<Investigation>("get_investigation").report!;
const order = fixture<{ items: WorkOrder[] }>("list_work_orders").items[0]!;

// Test inputs only, in the contract's shape.
const rows: Hypothesis[] = [
  {
    hypothesis: "The Edge-Ring pattern is associated in the literature with edge exposure drift.",
    source_ids: ["wu2015"],
    evidence_for: [
      { evidence_id: "E1", observation: "The predicted pattern is Edge-Ring." },
      { evidence_id: "E2", observation: "The lot repeats it." },
    ],
    evidence_against: [{ evidence_id: "E1", observation: "One wafer of the lot differs." }],
    assessment: "supported",
  },
  {
    hypothesis: "A chuck contamination.",
    source_ids: [],
    evidence_for: [],
    evidence_against: [{ evidence_id: "E3", observation: "No centre defects." }],
    assessment: "not_supported",
  },
];
const closed: WorkOrder = { ...order, status: "done", confirmed_cause: null };

describe("readHypotheses", () => {
  it("is null for a report without the field, and the list otherwise", () => {
    expect(readHypotheses({ ...report, hypotheses: undefined } as Report)).toBeNull();
    expect(readHypotheses(null)).toBeNull();
    expect(readHypotheses(report)).toEqual([]);
    expect(readHypotheses({ ...report, hypotheses: rows })).toBe(rows);
  });

  it("lists the evidence the table cites, once each", () => {
    expect(hypothesisEvidenceIds(rows)).toEqual(["E1", "E2", "E3"]);
    expect(hypothesisEvidenceIds([])).toEqual([]);
  });
});

describe("confirmed cause", () => {
  it("is null while the work order has none", () => {
    expect(readConfirmedCause(order)).toBeNull();
    expect(readConfirmedCause(closed)).toBeNull();
    expect(
      readConfirmedCause({ ...closed, confirmed_cause: { text: "  ", hypothesis_index: null } }),
    ).toBeNull();
  });

  it("names the hypothesis it confirms, when that hypothesis exists", () => {
    const cause = { text: "Worn chuck pins", hypothesis_index: 1 };
    expect(readConfirmedCause({ ...closed, confirmed_cause: cause })).toEqual(cause);
    expect(confirmedHypothesis(cause, rows)).toEqual({ index: 1, hypothesis: rows[1] });
    expect(confirmedHypothesis(cause, null)).toBeNull();
    expect(confirmedHypothesis({ ...cause, hypothesis_index: 5 }, rows)).toBeNull();
    expect(confirmedHypothesis({ ...cause, hypothesis_index: null }, rows)).toBeNull();
  });
});

describe("confirmedCauseUpdate", () => {
  const draft = { text: " Worn chuck pins ", hypothesisIndex: 0 };

  it("is sent only for a closed work order", () => {
    expect(confirmedCauseUpdate(order, "in_progress", draft)).toBeUndefined();
    expect(confirmedCauseUpdate(order, "done", draft)).toEqual({
      text: "Worn chuck pins",
      hypothesis_index: 0,
    });
  });

  it("sends nothing when it is unchanged, and null to clear it", () => {
    const recorded = {
      ...closed,
      confirmed_cause: { text: "Worn chuck pins", hypothesis_index: 0 },
    };
    expect(confirmedCauseUpdate(recorded, "done", draft)).toBeUndefined();
    expect(confirmedCauseUpdate(recorded, "done", { ...draft, hypothesisIndex: null })).toEqual({
      text: "Worn chuck pins",
      hypothesis_index: null,
    });
    expect(confirmedCauseUpdate(recorded, "done", { text: " ", hypothesisIndex: 0 })).toBeNull();
    expect(
      confirmedCauseUpdate(closed, "done", { text: "", hypothesisIndex: null }),
    ).toBeUndefined();
  });
});
