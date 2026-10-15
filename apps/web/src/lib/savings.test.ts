import type { Estimate } from "@yield-guardian/contracts";
import { describe, expect, it } from "vitest";

import {
  computeSavings,
  DAYS_PER_MONTH,
  type Inputs,
  isEmpty,
  parseInput,
  type Rates,
  roundFor,
} from "./savings";

// Test inputs only: rates shaped like the API's estimates, with round numbers to check the arithmetic.
const estimate = (value: number, ci_low: number | null, ci_high: number | null): Estimate => ({
  value,
  ci_low,
  ci_high,
  ci_level: 0.95,
  method: "test",
  n: 100,
});
const rate = (e: Estimate) => ({
  estimate: e,
  label: "test rate",
  data: "test data",
  source: "test",
});
const rates: Rates = {
  autoShare: rate(estimate(0.9, 0.8, 0.95)),
  falseAlarmRate: rate(estimate(0.02, 0.01, 0.05)),
};
const none: Inputs = {
  waferCost: null,
  engineerHourCost: null,
  downtimeHourCost: null,
  wafersPerDay: null,
  minutesPerMap: null,
};
const all: Inputs = {
  waferCost: 500,
  engineerHourCost: 60,
  downtimeHourCost: 2000,
  wafersPerDay: 100,
  minutesPerMap: 2,
};
const byId = (inputs: Inputs, r: Rates = rates) =>
  Object.fromEntries(computeSavings(inputs, r).map((l) => [l.id, l]));

describe("parseInput", () => {
  it("reads empty as no value, not zero", () => {
    expect(parseInput("")).toEqual({ value: null, error: null });
    expect(parseInput("   ")).toEqual({ value: null, error: null });
  });
  it("reads plain and grouped numbers", () => {
    expect(parseInput("1250").value).toBe(1250);
    expect(parseInput("1,250.5").value).toBe(1250.5);
    expect(parseInput(" 2.5 ").value).toBe(2.5);
    expect(parseInput(".5").value).toBe(0.5);
    expect(parseInput("0").value).toBe(0);
  });
  it("refuses negative, malformed and absurd values with a sentence", () => {
    expect(parseInput("-3").error).toBe("Enter 0 or more.");
    expect(parseInput("12,34").error).toMatch(/Enter a number/);
    expect(parseInput("1e5").error).toMatch(/Enter a number/);
    expect(parseInput("abc").error).toMatch(/Enter a number/);
    expect(parseInput("9".repeat(14)).error).toBe("This number is too large.");
  });
});

describe("computeSavings", () => {
  it("computes nothing from empty inputs and says what each line needs", () => {
    expect(isEmpty(none)).toBe(true);
    const lines = computeSavings(none, rates);
    expect(lines.every((l) => l.range == null)).toBe(true);
    expect(byId(none).engineerMoney!.needs).toEqual([
      "wafersPerDay",
      "minutesPerMap",
      "engineerHourCost",
    ]);
    expect(byId(none).waferMoney!.needs).toEqual(["wafersPerDay", "waferCost"]);
  });

  it("computes each line from the point value and both interval ends", () => {
    const l = byId(all);
    const wafers = 100 * DAYS_PER_MONTH;
    expect(l.maps!.range).toEqual({ value: wafers * 0.9, low: wafers * 0.8, high: wafers * 0.95 });
    expect(l.hours!.range!.value).toBeCloseTo((wafers * 0.9 * 2) / 60, 9);
    expect(l.hours!.range!.low).toBeCloseTo((wafers * 0.8 * 2) / 60, 9);
    expect(l.engineerMoney!.range!.high).toBeCloseTo(((wafers * 0.95 * 2) / 60) * 60, 9);
    expect(l.falseAlarms!.range).toEqual({
      value: wafers * 0.02,
      low: wafers * 0.01,
      high: wafers * 0.05,
    });
    expect(l.downtimeMoney!.range!.value).toBeCloseTo(wafers * 0.02 * 2000, 9);
    expect(l.waferMoney!.range!.high).toBeCloseTo(wafers * 0.05 * 500, 9);
  });

  it("computes a line as soon as its own inputs are there", () => {
    const l = byId({ ...none, wafersPerDay: 100, minutesPerMap: 2 });
    expect(l.hours!.range).not.toBeNull();
    expect(l.falseAlarms!.range).not.toBeNull();
    expect(l.engineerMoney!.range).toBeNull();
    expect(l.engineerMoney!.needs).toEqual(["engineerHourCost"]);
  });

  it("gives zero, not nothing, for zero inputs", () => {
    const l = byId({ ...all, wafersPerDay: 0 });
    expect(l.hours!.range).toEqual({ value: 0, low: 0, high: 0 });
    expect(l.falseAlarms!.range).toEqual({ value: 0, low: 0, high: 0 });
    expect(byId({ ...all, minutesPerMap: 0 }).engineerMoney!.range!.value).toBe(0);
  });

  it("needs the measured rate, and keeps a missing interval end missing", () => {
    const l = byId(all, { autoShare: null, falseAlarmRate: rate(estimate(0.02, null, null)) });
    expect(l.hours!.range).toBeNull();
    expect(l.hours!.needs).toEqual(["autoShare"]);
    expect(l.falseAlarms!.range).toEqual({ value: 3000 * 0.02, low: null, high: null });
  });
});

describe("roundFor", () => {
  it("rounds money to whole units and small counts to one decimal", () => {
    expect(roundFor("engineerMoney", 1234.56)).toEqual({ value: 1235, digits: 0 });
    expect(roundFor("engineerMoney", 3.4)).toEqual({ value: 3, digits: 0 });
    expect(roundFor("hours", 9.94)).toEqual({ value: 9.9, digits: 1 });
    expect(roundFor("hours", 12.5)).toEqual({ value: 13, digits: 0 });
    expect(roundFor("falseAlarms", 0.69)).toEqual({ value: 0.7, digits: 1 });
    expect(roundFor("falseAlarms", 0)).toEqual({ value: 0, digits: 0 });
  });
});
