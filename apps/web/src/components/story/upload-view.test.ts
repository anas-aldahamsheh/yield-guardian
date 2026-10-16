import type { UploadIssue } from "@yield-guardian/contracts";
import { describe, expect, it } from "vitest";

import { fixture } from "../../../e2e/story/fixture";

import {
  ISSUES_SHOWN,
  MAX_UPLOAD_BYTES,
  checkFile,
  isUpload,
  issueLine,
  issuePlace,
  keptUpload,
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

  it("keeps a checked upload across a reload only while the API keeps the file", () => {
    const summary = fixture.uploadOk;
    const kept = JSON.parse(JSON.stringify(summary)) as unknown;
    expect(isUpload(kept)).toBe(true);
    const now = Date.parse(summary.expires_at);
    expect(keptUpload(summary, now - 60_000)).toBe(summary);
    expect(keptUpload(summary, now + 1)).toBeNull();
    expect(keptUpload({ ...summary, expires_at: "never" }, now)).toBeNull();
    expect(keptUpload(null)).toBeNull();
    expect(isUpload({ ...summary, upload_id: 7 })).toBe(false);
    expect(isUpload({ ...summary, kind: "logs" })).toBe(false);
    expect(isUpload({ ...summary, issues: "none" })).toBe(false);
    expect(isUpload(null)).toBe(false);
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
    // The API's messages name the row themselves: the line does not say it twice.
    expect(view.shown.map(issueLine)).toEqual([
      {
        place: "Row 7",
        rest: ': "-1" is not a column (x); it must be a whole number of 0 or more.',
      },
      { place: "Row 13", rest: ': the result "maybe" is not pass or fail.' },
      {
        place: "Row 22",
        rest: " repeats the die at x 19, y 1 of lot lot5421, wafer 1 (first on row 21). List each die once.",
      },
    ]);
  });

  it("puts the place first when the message does not begin with it", () => {
    const warning = fixture.uploadOk.issues[0]!;
    expect(issueLine(warning)).toEqual({
      place: "Row 4, column timestamp",
      rest: `: ${warning.message}`,
    });
    expect(
      issueLine(issue({ row: 9, column: "S001", message: "Row 9, S001: not a number." })),
    ).toEqual({
      place: "Row 9, S001",
      rest: ": not a number.",
    });
    // A message about another row keeps its own place in front.
    expect(issueLine(issue({ row: 9, message: "Row 8 and row 9 repeat a unit." })).place).toBe(
      "Row 9",
    );
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
