import type {
  Investigation,
  InvestigationEvent,
  InvestigationStep,
  NumberRef,
  VerificationIssue,
} from "@yield-guardian/contracts";

/**
 * Applies investigation events (SSE) to an investigation record. Pure, tested against the
 * contract's recorded stream: replaying every event onto an empty run must give the stored run.
 */

export const LIVE_STATUSES = new Set<Investigation["status"]>(["queued", "running"]);

/** The run before any event: what a replay starts from. */
export function emptyRun(investigation: Investigation): Investigation {
  return {
    ...investigation,
    status: "queued",
    steps: [],
    evidence: [],
    report: null,
    verification: null,
    decision: null,
    error: null,
    work_order_id: null,
  };
}

function upsertStep(steps: InvestigationStep[], step: InvestigationStep): InvestigationStep[] {
  const rest = steps.filter((s) => s.index !== step.index);
  return [...rest, step].sort((a, b) => a.index - b.index);
}

export function applyInvestigationEvent(inv: Investigation, event: InvestigationEvent): Investigation {
  switch (event.type) {
    case "status":
      return { ...inv, status: event.status, updated_at: event.at };
    case "step":
      return { ...inv, steps: upsertStep(inv.steps, event.step), updated_at: event.at };
    case "evidence":
      return inv.evidence.some((e) => e.evidence_id === event.evidence.evidence_id)
        ? inv
        : { ...inv, evidence: [...inv.evidence, event.evidence], updated_at: event.at };
    case "report":
      return { ...inv, report: event.report, updated_at: event.at };
    case "verification":
      return { ...inv, verification: event.verification, updated_at: event.at };
    case "decision":
      return {
        ...inv,
        decision: event.decision,
        work_order_id: event.work_order_id,
        status: event.decision.verdict === "approve" ? "approved" : "rejected",
        updated_at: event.at,
      };
    case "error":
      return { ...inv, error: event.problem, updated_at: event.at };
    case "end":
      return { ...inv, status: event.status, updated_at: event.at };
    default:
      return inv;
  }
}

export const INVESTIGATION_EVENT_TYPES = [
  "status",
  "step",
  "evidence",
  "report",
  "verification",
  "decision",
  "error",
  "end",
] as const;

/** A part of a written text: plain, or a number the report lists with its evidence. */
export type Segment = { text: string; number?: number; unverified?: true };

/** What the verifier writes in place of a value it could not trace to evidence. */
export const UNVERIFIED_MARK = "[unverified]";

/**
 * Splits text at the numbers the report lists (`NumberRef.as_written`), so each number can link
 * to the evidence value it came from. Longer forms win ("18.4%" before "18.4"); each listed
 * number is matched where it appears.
 */
export function segmentNumbers(text: string, numbers: NumberRef[]): Segment[] {
  const order = numbers
    .map((n, index) => ({ index, written: n.as_written }))
    .filter((n) => n.written.length > 0)
    .sort((a, b) => b.written.length - a.written.length);
  const segments: Segment[] = [];
  let i = 0;
  let plain = "";
  while (i < text.length) {
    if (text.startsWith(UNVERIFIED_MARK, i)) {
      if (plain) segments.push({ text: plain });
      plain = "";
      segments.push({ text: UNVERIFIED_MARK, unverified: true });
      i += UNVERIFIED_MARK.length;
      continue;
    }
    const hit = order.find((n) => {
      if (!text.startsWith(n.written, i)) return false;
      // Do not match inside a longer number: "1.5" in "21.5" or "8" in "18.4".
      const end = i + n.written.length;
      const digit = (c: string | undefined) => c != null && /\d/.test(c);
      const before = text[i - 1];
      const after = text[end];
      const cleanBefore = !digit(before) && !(before === "." && digit(text[i - 2]));
      const cleanAfter = !digit(after) && !(after === "." && digit(text[end + 1]));
      return cleanBefore && cleanAfter;
    });
    if (hit) {
      if (plain) segments.push({ text: plain });
      plain = "";
      segments.push({ text: hit.written, number: hit.index });
      i += hit.written.length;
    } else {
      plain += text[i];
      i += 1;
    }
  }
  if (plain) segments.push({ text: plain });
  return segments;
}

/** Where a verification issue points: "numbers[3]" → { part: "numbers", index: 3 }. */
export function issueTarget(issue: VerificationIssue): { part: string; index: number | null } {
  const m = issue.location.match(/^([a-z_]+)(?:\[(\d+)\])?/);
  if (!m) return { part: issue.location, index: null };
  return { part: m[1]!, index: m[2] != null ? Number(m[2]) : null };
}

/** Issues grouped by the part of the report they flag, for drawing them in place. */
export function issuesByTarget(issues: VerificationIssue[]): Map<string, VerificationIssue[]> {
  const map = new Map<string, VerificationIssue[]>();
  for (const issue of issues) {
    const { part, index } = issueTarget(issue);
    const key = index == null ? part : `${part}[${index}]`;
    map.set(key, [...(map.get(key) ?? []), issue]);
  }
  return map;
}

/** Reads a JSON pointer (RFC 6901) from evidence data; undefined when it does not resolve. */
export function readPointer(data: unknown, pointer: string): unknown {
  if (pointer === "" || pointer === "/") return data;
  let node: unknown = data;
  for (const raw of pointer.split("/").slice(1)) {
    const key = raw.replace(/~1/g, "/").replace(/~0/g, "~");
    if (Array.isArray(node)) node = node[Number(key)];
    else if (node && typeof node === "object") node = (node as Record<string, unknown>)[key];
    else return undefined;
  }
  return node;
}
