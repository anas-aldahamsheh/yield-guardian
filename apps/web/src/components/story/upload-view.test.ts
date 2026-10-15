import type { UploadIssue } from "@yield-guardian/contracts";
import { describe, expect, it } from "vitest";

import { fixture } from "../../../e2e/story/fixture";

import {
  ISSUES_SHOWN,
  MAX_UPLOAD_BYTES,
  checkFile,
  issuePlace,
  sortIssues,
  uploadView,
} from "./upload-view";

const issue = (over: Partial<UploadIssue>): UploadIssue => ({
  severity: "error",
  row: null,
  column: null,
  message: "Test issue.",
  ...over,
});

describe("the upload view", () => {
  it("refuses files the API would refuse, before sending them", () => {
    expect(checkFile({ name: "units.csv", size: 1200 })).toBeNull();
    expect(checkFile({ name: "Units.XLSX", size: MAX_UPLOAD_BYTES })).toBeNull();
    expect(checkFile({ name: "units.csv", size: MAX_UPLOAD_BYTES + 1 })).toMatch(
      /32\.0 MB; files up to 32 MB are accepted/,
    );
    expect(checkFile({ name: "units.json", size: 10 })).toMatch(/not a CSV or XLSX file/);
    expect(checkFile({ name: "units.csv", size: 0 })).toMatch(/is empty/);
  });

  it("names the row and column of each issue in the file's own numbering", () => {
    expect(issuePlace(issue({ row: 7, column: "x" }))).toBe("Row 7, column x");
    expect(issuePlace(issue({ column: "result" }))).toBe("Column result");
    expect(issuePlace(issue({ row: 1200 }))).toBe("Row 1,200");
    expect(issuePlace(issue({}))).toBe("The file");
  });

  it("lists errors before warnings, each in file order", () => {
    const sorted = sortIssues([
      issue({ severity: "warning", row: 2 }),
      issue({ severity: "error", row: 9 }),
      issue({ severity: "error", row: null, column: "result" }),
      issue({ severity: "warning", row: 1 }),
      issue({ severity: "error", row: 3 }),
    ]);
    expect(sorted.map((i) => `${i.severity}:${i.row}`)).toEqual([
      "error:null",
      "error:3",
      "error:9",
      "warning:1",
      "warning:2",
    ]);
  });

  it("says a file with warnings is ready to run", () => {
    const view = uploadView(fixture.uploadOk);
    expect(view.ready).toBe(true);
    expect(view.headline).toBe("Ready to run. The warning below does not stop the run.");
    expect(view.read).toMatch(
      /^secom-units\.csv: sensor units, 40 units with [\d,]+ missing readings\.$/,
    );
    expect(view.shown).toHaveLength(1);
  });

  it("says what blocks a file with errors", () => {
    const view = uploadView(fixture.uploadBad);
    expect(view.ready).toBe(false);
    expect(view.headline).toBe(
      "This file cannot run yet: fix the 3 errors below and upload it again.",
    );
    expect(view.shown.map(issuePlace)).toEqual([
      "Row 7, column x",
      "Row 13, column result",
      "Row 22",
    ]);
  });

  it("lists the first issues and counts the rest", () => {
    const many = Array.from({ length: ISSUES_SHOWN + 12 }, (_, k) =>
      issue({ row: k + 2, column: "S001" }),
    );
    const view = uploadView({ ...fixture.uploadBad, issues: many });
    expect(view.shown).toHaveLength(ISSUES_SHOWN);
    expect(view.more).toBe(12);
    expect(view.errors).toBe(ISSUES_SHOWN + 12);
  });
});
