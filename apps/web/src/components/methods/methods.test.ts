import type { SecomMetrics, SplitResult } from "@yield-guardian/contracts";
import { describe, expect, it } from "vitest";

import { secomReading } from "./secom-methods";
import { seedText } from "./wafer-methods";

const est = (value: number) => ({
  value,
  ci_low: null,
  ci_high: null,
  ci_level: 0.95,
  method: null,
  n: null,
  note: null,
});
const model = (id: string, label: string, main: boolean, pr: number) => ({
  model: id,
  label,
  main,
  metrics: [{ metric: "pr_auc", label: "PR-AUC", estimate: est(pr) }],
});

describe("secomReading", () => {
  it("says when a baseline beats the main model, from the API's numbers", () => {
    const text = secomReading({
      models: [
        model("lightgbm", "LightGBM", true, 0.075),
        model("logistic_regression", "logistic baseline", false, 0.172),
        model("prevalence", "No skill", false, 0.054),
      ],
    } as unknown as SecomMetrics);
    expect(text).toContain(
      "logistic baseline scores higher than the main model (0.172 against 0.075)",
    );
    expect(text).toContain("No skill scores 0.054");
    expect(text).toContain("experimental signal");
  });
  it("names the main model when it is best", () => {
    const text = secomReading({
      models: [model("lightgbm", "LightGBM", true, 0.3), model("rf", "RF", false, 0.2)],
    } as unknown as SecomMetrics);
    expect(text).toContain("The main model has the highest PR-AUC, 0.300.");
  });
});

describe("seedText", () => {
  it("renders a single fit when the seed spread is null, never 0", () => {
    expect(seedText({ seed_mean: null, seed_sd: null, seeds: [] } as unknown as SplitResult)).toBe(
      "single fit",
    );
  });
  it("renders mean and spread over seeds", () => {
    expect(
      seedText({ seed_mean: 0.86, seed_sd: 0.0036, seeds: [{}, {}, {}] } as unknown as SplitResult),
    ).toBe("0.860 ± 0.004 over 3 seeds");
  });
});
