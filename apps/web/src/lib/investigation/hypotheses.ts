import type { Report, WorkOrder } from "@yield-guardian/contracts";

/**
 * The report's hypothesis table (PLAN_V2 §7.3) and a work order's confirmed cause. The AI worker
 * adds both to the contract (V5): `Report.hypotheses` with an empty list by default, and the
 * confirmed cause when a work order is closed. Until that lands on main these readers take the
 * fields as optional and tolerate the two shapes the plan allows for an evidence entry (an
 * evidence ID, or a sentence with its evidence IDs), so the page shows them as soon as the API
 * sends them and shows nothing before.
 */

export type Assessment = "supported" | "not_supported" | "inconclusive";

/** One entry for or against: a sentence (numbers link through Report.numbers) and its evidence. */
export interface HypothesisEvidence {
  text: string | null;
  evidenceIds: string[];
}

export interface HypothesisRow {
  hypothesis: string;
  sourceIds: string[];
  evidenceFor: HypothesisEvidence[];
  evidenceAgainst: HypothesisEvidence[];
  assessment: Assessment | null;
}

const EVIDENCE_ID = /^E\d+$/;
const ASSESSMENTS = new Set<string>(["supported", "not_supported", "inconclusive"]);

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const strings = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);

function firstString(record: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return null;
}

/** An entry as the API sends it: "E3", "a sentence", or { text | claim | summary, evidence_ids | evidence_id }. */
export function readEvidence(entries: unknown): HypothesisEvidence[] {
  if (!Array.isArray(entries)) return [];
  const out: HypothesisEvidence[] = [];
  for (const entry of entries) {
    if (typeof entry === "string") {
      if (EVIDENCE_ID.test(entry)) out.push({ text: null, evidenceIds: [entry] });
      else if (entry.trim()) out.push({ text: entry, evidenceIds: [] });
    } else if (isRecord(entry)) {
      const ids = [...strings(entry.evidence_ids), ...(typeof entry.evidence_id === "string" ? [entry.evidence_id] : [])].filter((id) => EVIDENCE_ID.test(id));
      const text = firstString(entry, ["text", "claim", "summary", "statement", "note"]);
      if (text || ids.length) out.push({ text, evidenceIds: ids });
    }
  }
  return out;
}

/** The hypotheses of a report, or null when the report has no such field (older API). */
export function readHypotheses(report: Report | null | undefined): HypothesisRow[] | null {
  const raw = (report as (Report & { hypotheses?: unknown }) | null | undefined)?.hypotheses;
  if (!Array.isArray(raw)) return null;
  return raw.filter(isRecord).flatMap((h) => {
    const hypothesis = firstString(h, ["hypothesis", "text"]);
    if (!hypothesis) return [];
    const assessment = typeof h.assessment === "string" && ASSESSMENTS.has(h.assessment) ? (h.assessment as Assessment) : null;
    return [
      {
        hypothesis,
        sourceIds: strings(h.source_ids),
        evidenceFor: readEvidence(h.evidence_for),
        evidenceAgainst: readEvidence(h.evidence_against),
        assessment,
      },
    ];
  });
}

/** Every evidence ID the table cites, in order of first mention. */
export function hypothesisEvidenceIds(rows: HypothesisRow[]): string[] {
  const seen = new Set<string>();
  for (const row of rows) for (const e of [...row.evidenceFor, ...row.evidenceAgainst]) for (const id of e.evidenceIds) seen.add(id);
  return [...seen];
}

/** The fab's own record of what the cause was, written when the work order was closed. */
export interface ConfirmedCause {
  text: string;
  /** The hypothesis it confirms, as written in the report, when the engineer chose one. */
  hypothesis: string | null;
  confirmedBy: string | null;
  confirmedAt: string | null;
}

/**
 * Reads the confirmed cause from a work order: `confirmed_cause` as a sentence, or as an object
 * with the sentence and the hypothesis (by text or by its index in the report's table).
 */
export function readConfirmedCause(order: WorkOrder, hypotheses: HypothesisRow[] | null = null): ConfirmedCause | null {
  const raw = (order as WorkOrder & { confirmed_cause?: unknown }).confirmed_cause;
  if (typeof raw === "string") return raw.trim() ? { text: raw, hypothesis: null, confirmedBy: null, confirmedAt: null } : null;
  if (!isRecord(raw)) return null;
  const text = firstString(raw, ["text", "cause", "description"]);
  if (!text) return null;
  const index = typeof raw.hypothesis_index === "number" ? raw.hypothesis_index : null;
  const hypothesis =
    firstString(raw, ["hypothesis"]) ?? (index != null && hypotheses?.[index] ? hypotheses[index].hypothesis : null);
  return {
    text,
    hypothesis,
    confirmedBy: firstString(raw, ["confirmed_by", "by"]),
    confirmedAt: firstString(raw, ["confirmed_at", "at"]),
  };
}
