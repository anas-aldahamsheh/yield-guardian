import { describe, expect, it } from "vitest";

import { type Block, CATEGORIES, ENTRIES, SHOT_SLOTS } from "./guide-content";
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

  it("holds no measured number: those are read from the API above the guide", () => {
    const text = (b: Block): string[] =>
      b.type === "p" || b.type === "note"
        ? [b.text]
        : b.type === "list" || b.type === "steps"
          ? [...b.items]
          : b.type === "table"
            ? [...b.head, ...b.rows.flat()]
            : [b.caption];
    for (const e of ENTRIES)
      for (const b of e.blocks)
        for (const t of text(b)) {
          // No decimals, no counts in the thousands; the one percentage is the precision target the calculator names.
          expect(t, e.id).not.toMatch(/\d[.,]\d/);
          expect(t.replace("99%", ""), e.id).not.toMatch(/\d+\s?%/);
        }
  });

  it("gives every screenshot slot a unique id and a caption", () => {
    const ids = SHOT_SLOTS.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(SHOT_SLOTS.length).toBeGreaterThan(0);
    for (const s of SHOT_SLOTS) expect(s.caption.length, s.id).toBeGreaterThan(0);
  });
});

describe("guide search", () => {
  it("treats alef forms, ta marbuta and diacritics as the same letter", () => {
    expect(normalizeArabic("الإنذارُ")).toBe(normalizeArabic("الانذار"));
    expect(normalizeArabic("الدفعة")).toBe(normalizeArabic("الدفعه"));
  });

  it("finds entries by any form of a word and needs every word", () => {
    expect(matchEntries(ENTRIES, "انذار").length).toBeGreaterThan(0);
    expect(matchEntries(ENTRIES, "Investigate").some((e) => e.id === "guide-investigate")).toBe(
      true,
    );
    expect(matchEntries(ENTRIES, "Investigate zzzz")).toHaveLength(0);
    expect(matchEntries(ENTRIES, "   ")).toHaveLength(ENTRIES.length);
  });
});
