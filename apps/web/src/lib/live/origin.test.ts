import { describe, expect, it } from "vitest";

import { originRule } from "./origin";

describe("originRule", () => {
  it("writes the seed after a rule the API cut after a whole sentence", () => {
    const rule =
      "Every demo wafer of real WM-811K lot lot36914 (24 wafers). So most lots carry a repeating pattern.…";
    expect(originRule(rule, 661347238)).toEqual({
      rule: "Every demo wafer of real WM-811K lot lot36914 (24 wafers). So most lots carry a repeating pattern.",
      seed: "Seed 661347238: the same seed repeats this pick.",
    });
  });

  it("leaves a rule that has its seed sentence as it is", () => {
    const rule = "Forty units. Seed 7: the same seed repeats this pick.";
    expect(originRule(rule, 7)).toEqual({ rule, seed: null });
  });

  it("keeps an ellipsis that cuts a sentence, and leaves rules without a seed alone", () => {
    expect(originRule("A long sentence that was cut…", 3)).toEqual({
      rule: "A long sentence that was cut…",
      seed: "Seed 3: the same seed repeats this pick.",
    });
    expect(originRule("Your drawing.", null)).toEqual({ rule: "Your drawing.", seed: null });
  });
});
