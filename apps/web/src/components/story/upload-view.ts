import type { UploadIssue, UploadSummary } from "@yield-guardian/contracts";

import { formatInt, plural } from "@/lib/format";

/**
 * What the upload view says about a parsed file, kept pure so it is tested on its own: a
 * headline (ready to run, or what blocks it), what was read, and each issue in plain words with
 * the file's own row and column.
 */

/** The API refuses larger files; the page says so before sending one. */
export const MAX_UPLOAD_BYTES = 32 * 1024 * 1024;
export const UPLOAD_ACCEPT =
  ".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
/** Issues listed one by one; the rest are counted. */
export const ISSUES_SHOWN = 50;

/** A file the page will not send, with the reason in plain words; null when it may go. */
export function checkFile(file: { name: string; size: number }): string | null {
  const lower = file.name.toLowerCase();
  if (!lower.endsWith(".csv") && !lower.endsWith(".xlsx")) {
    return `${file.name} is not a CSV or XLSX file. Save it as one of those and choose it again.`;
  }
  if (file.size === 0) return `${file.name} is empty.`;
  if (file.size > MAX_UPLOAD_BYTES) {
    const mb = file.size / (1024 * 1024);
    return `${file.name} is ${mb >= 100 ? formatInt(mb) : mb.toFixed(1)} MB; files up to 32 MB are accepted. Split it into smaller files.`;
  }
  return null;
}

/** Where an issue is: "Row 7, column x", "Column result", "Row 7", or "The file". */
export function issuePlace(issue: UploadIssue): string {
  if (issue.row != null && issue.column)
    return `Row ${formatInt(issue.row)}, column ${issue.column}`;
  if (issue.row != null) return `Row ${formatInt(issue.row)}`;
  if (issue.column) return `Column ${issue.column}`;
  return "The file";
}

/**
 * An issue as one line: its place in medium weight, then what is wrong. The API's messages
 * often begin with the place themselves ("Row 13: the result ..."); then that beginning is the
 * place, so it is not said twice.
 */
export function issueLine(issue: UploadIssue): { place: string; rest: string } {
  const own = /^(Row (\d(?:[\d,]*\d)?)(?:, (?:column )?[\w.]+)?)(?=[: ])(.*)$/s.exec(issue.message);
  if (own && issue.row != null && Number(own[2]!.replace(/,/g, "")) === issue.row) {
    return { place: own[1]!, rest: own[3]! };
  }
  return { place: issuePlace(issue), rest: `: ${issue.message}` };
}

/** Errors first, then warnings, each in file order (issues without a row first). */
export function sortIssues(issues: readonly UploadIssue[]): UploadIssue[] {
  const rank = (i: UploadIssue) => (i.severity === "error" ? 0 : 1);
  return issues
    .map((issue, k) => ({ issue, k }))
    .sort(
      (a, b) =>
        rank(a.issue) - rank(b.issue) || (a.issue.row ?? -1) - (b.issue.row ?? -1) || a.k - b.k,
    )
    .map((x) => x.issue);
}

export interface UploadView {
  ready: boolean;
  headline: string;
  /** What the file holds, in one sentence. */
  read: string;
  errors: number;
  warnings: number;
  shown: UploadIssue[];
  /** Issues not listed one by one. */
  more: number;
}

export function uploadView(summary: UploadSummary): UploadView {
  const errors = summary.issues.filter((i) => i.severity === "error").length;
  const warnings = summary.issues.length - errors;
  const ready = summary.runnable && errors === 0;
  const what =
    summary.kind === "sensors"
      ? `${plural(summary.units, "unit")}` +
        (summary.missing_readings
          ? ` with ${plural(summary.missing_readings, "missing reading")}`
          : ", no readings missing")
      : `${plural(summary.wafers, "wafer")} in ${plural(summary.lots, "lot")}`;
  const read = `${summary.filename}: ${summary.kind === "sensors" ? "sensor units" : "wafer maps"}, ${what}.`;
  const headline = ready
    ? warnings === 1
      ? "Ready to run. The warning below does not stop the run."
      : warnings
        ? `Ready to run. The ${formatInt(warnings)} warnings below do not stop the run.`
        : "Ready to run."
    : errors
      ? `This file cannot run yet: fix ${errors === 1 ? "the error" : `the ${formatInt(errors)} errors`} below and upload it again.`
      : "This file cannot run: it holds nothing the line can read.";
  const sorted = sortIssues(summary.issues);
  return {
    ready,
    headline,
    read,
    errors,
    warnings,
    shown: sorted.slice(0, ISSUES_SHOWN),
    more: Math.max(0, sorted.length - ISSUES_SHOWN),
  };
}
