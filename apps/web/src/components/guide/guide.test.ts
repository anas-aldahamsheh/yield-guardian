import { describe, expect, it } from "vitest";

import { CATEGORIES, ENTRIES } from "./guide-content";
import { matchEntries, normalizeArabic } from "./guide-view";

describe("guide content", () => {
  it("gives every entry a unique id and a known category", () => {
    const ids = ENTRIES.map((e) => e.id);
    expect(new Set(ids).size).toBe(ids.length);
    const categories = new Set(CATEGORIES.map((c) => c.id));
    for (const e of ENTRIES) expect(categories.has(e.category), e.id).toBe(true);
  });

  it("has at least one entry in every category", () => {
    for (const c of CATEGORIES)
      expect(
        ENTRIES.some((e) => e.category === c.id),
        c.id,
      ).toBe(true);
  });

  it("keeps table rows as wide as their header", () => {
    for (const e of ENTRIES)
      for (const b of e.blocks)
        if (b.type === "table")
          for (const row of b.rows) expect(row.length, e.id).toBe(b.head.length);
  });
});

describe("guide search", () => {
  it("treats alef forms, ta marbuta and diacritics as the same letter", () => {
    expect(normalizeArabic("الإنذارُ")).toBe(normalizeArabic("الانذار"));
    expect(normalizeArabic("الدفعة")).toBe(normalizeArabic("الدفعه"));
  });

  it("finds entries by any form of a word and needs every word", () => {
    expect(matchEntries(ENTRIES, "انذار").length).toBeGreaterThan(0);
    expect(matchEntries(ENTRIES, "LightGBM").some((e) => e.id === "ml-lightgbm")).toBe(true);
    expect(matchEntries(ENTRIES, "LightGBM zzzz")).toHaveLength(0);
    expect(matchEntries(ENTRIES, "   ")).toHaveLength(ENTRIES.length);
  });
});
