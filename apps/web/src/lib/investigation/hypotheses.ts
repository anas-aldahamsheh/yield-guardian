import type {
  ConfirmedCause,
  Hypothesis,
  HypothesisEvidence,
  Report,
  WorkOrder,
  WorkOrderUpdate,
} from "@yield-guardian/contracts";

/**
 * The report's hypothesis table (PLAN_V2 §7.3) and a work order's confirmed cause, in the
 * contract's own types. Only an investigation of an alarm raised in a run tests hypotheses;
 * every other report carries an empty list.
 */

export type { ConfirmedCause, Hypothesis, HypothesisEvidence };
export type Assessment = Hypothesis["assessment"];

/** The hypotheses of a report: null when the report has no such field (recorded before V5). */
export function readHypotheses(report: Report | null | undefined): Hypothesis[] | null {
  return report?.hypotheses ?? null;
}

/** Every evidence ID the table cites, in order of first mention. */
export function hypothesisEvidenceIds(rows: readonly Hypothesis[]): string[] {
  const seen = new Set<string>();
  for (const row of rows)
    for (const e of [...row.evidence_for, ...row.evidence_against]) seen.add(e.evidence_id);
  return [...seen];
}

/** The fab's own record of the cause, recorded when the work order was closed; null before. */
export function readConfirmedCause(order: WorkOrder): ConfirmedCause | null {
  const cause = order.confirmed_cause;
  return cause && cause.text.trim() ? cause : null;
}

/** The hypothesis of the report a confirmed cause confirms, when it names one that exists. */
export function confirmedHypothesis(
  cause: ConfirmedCause,
  hypotheses: readonly Hypothesis[] | null,
): { index: number; hypothesis: Hypothesis } | null {
  const index = cause.hypothesis_index;
  if (index == null || !hypotheses) return null;
  const hypothesis = hypotheses[index];
  return hypothesis ? { index, hypothesis } : null;
}

/** What the engineer has written in the form for the confirmed cause. */
export interface CauseDraft {
  text: string;
  hypothesisIndex: number | null;
}

/**
 * The `confirmed_cause` field of a work order update, or undefined when nothing changes. A
 * cause is recorded only on a closed (done) work order: with another status nothing is sent,
 * since the API withdraws the cause itself when the order is reopened. Empty text clears it.
 */
export function confirmedCauseUpdate(
  order: WorkOrder,
  status: WorkOrder["status"],
  draft: CauseDraft,
): WorkOrderUpdate["confirmed_cause"] | undefined {
  if (status !== "done") return undefined;
  const current = readConfirmedCause(order);
  const text = draft.text.trim();
  if (!text) return current ? null : undefined;
  const next: ConfirmedCause = { text, hypothesis_index: draft.hypothesisIndex };
  const same =
    current != null &&
    current.text === next.text &&
    (current.hypothesis_index ?? null) === next.hypothesis_index;
  return same ? undefined : next;
}
