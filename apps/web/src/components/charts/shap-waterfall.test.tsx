import type { Explanation } from "@yield-guardian/contracts";
import { render, screen } from "@testing-library/react";

import { fixture } from "@/mocks/fixtures";

import { ShapWaterfall, waterfallRows } from "./shap-waterfall";

const explanation = () => fixture<Explanation>("get_unit_explanation");

describe("waterfallRows", () => {
  it("steps from the base value to the model output", () => {
    const e = explanation();
    const rows = waterfallRows(e);
    expect(rows[0]!.end).toBe(e.base_value);
    const steps = rows.slice(1, -1);
    expect(steps[0]!.start).toBe(e.base_value);
    for (let i = 1; i < steps.length; i += 1)
      expect(steps[i]!.start).toBeCloseTo(steps[i - 1]!.end, 9);
    expect(steps.at(-1)!.end).toBeCloseTo(e.raw_score, 6);
    expect(rows.at(-1)!.end).toBe(e.raw_score);
  });

  it("names missing-value indicators as such", () => {
    const e = explanation();
    e.contributions[0] = {
      ...e.contributions[0]!,
      kind: "missing_indicator",
      feature: "S060_missing",
      value: 1,
    };
    expect(waterfallRows(e)[1]!.label).toBe("S060 missing");
  });
});

describe("ShapWaterfall", () => {
  it("renders one row per contribution plus base, rest and output, as a table", () => {
    const e = explanation();
    render(<ShapWaterfall explanation={e} />);
    expect(screen.getByRole("table", { name: /SHAP/ })).toBeInTheDocument();
    expect(screen.getAllByRole("rowheader")).toHaveLength(e.contributions.length + 3);
  });
});
