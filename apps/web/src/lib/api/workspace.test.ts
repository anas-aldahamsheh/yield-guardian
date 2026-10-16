import { describe, expect, it } from "vitest";

import { codeFromHash } from "./workspace";

// Opening this device's workspace, the API asleep included: opening.test.ts.

describe("a join link", () => {
  it("carries its code after #, which no server receives", () => {
    expect(codeFromHash("#code=7K2M-QX9D-4HRT")).toBe("7K2M-QX9D-4HRT");
    expect(codeFromHash("#from=phone&code=7k2m%20qx9d%204hrt")).toBe("7k2m qx9d 4hrt");
    expect(codeFromHash("")).toBeNull();
    expect(codeFromHash("#nocode")).toBeNull();
    expect(codeFromHash("#code=%E0%A4%A")).toBeNull();
    expect(codeFromHash(`#code=${"A".repeat(40)}`)).toHaveLength(24);
  });
});
