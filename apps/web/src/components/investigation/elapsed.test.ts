import { describe, expect, it } from "vitest";

import { formatElapsed } from "./elapsed";

describe("formatElapsed", () => {
  it("reads as seconds, then minutes and seconds, then hours and minutes", () => {
    expect(formatElapsed(0)).toBe("0 s");
    expect(formatElapsed(999)).toBe("0 s");
    expect(formatElapsed(45_400)).toBe("45 s");
    expect(formatElapsed(60_000)).toBe("1 min 00 s");
    expect(formatElapsed(16 * 60_000 + 5_000)).toBe("16 min 05 s");
    expect(formatElapsed(3_600_000 + 4 * 60_000)).toBe("1 h 04 min");
  });

  it("never shows negative time when clocks disagree", () => {
    expect(formatElapsed(-1_500)).toBe("0 s");
  });
});
