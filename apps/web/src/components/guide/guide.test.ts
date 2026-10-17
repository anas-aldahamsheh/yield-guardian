import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { type Block, CATEGORIES, ENTRIES, SHOT_SLOTS } from "./guide-content";

describe("guide content", () => {
  it("gives every entry a unique id and a known category", () => {
    const ids = ENTRIES.map((e) => e.id);
    expect(new Set(ids).size).toBe(ids.length);
    const categories = new Set(CATEGORIES.map((c) => c.id));
    for (const e of ENTRIES) expect(categories.has(e.category), e.id).toBe(true);
  });

  it("is English only", () => {
    const text = JSON.stringify({ CATEGORIES, ENTRIES });
    expect(text).not.toMatch(/[\u0600-\u06FF]/);
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
            : [b.caption, b.alt];
    for (const e of ENTRIES)
      for (const b of e.blocks)
        for (const t of text(b)) {
          // No decimals, no counts in the thousands; the one percentage is the precision target the calculator names.
          expect(t, e.id).not.toMatch(/\d[.,]\d/);
          expect(t.replace("99%", ""), e.id).not.toMatch(/\d+\s?%/);
        }
  });

  it("gives every screenshot a unique id, a caption and alt text", () => {
    const ids = SHOT_SLOTS.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(SHOT_SLOTS.length).toBeGreaterThan(0);
    for (const s of SHOT_SLOTS) {
      expect(s.caption.length, s.id).toBeGreaterThan(0);
      expect(s.alt.length, s.id).toBeGreaterThan(0);
      expect(s.alt, s.id).not.toBe(s.caption);
    }
  });

  it("points every screenshot at its compressed file, at the file's own size", () => {
    for (const s of SHOT_SLOTS) {
      expect(s.src, s.id).toBe(`/guide/${s.id}.webp`);
      const file = path.join(PUBLIC, s.src);
      expect(statSync(file).size, s.id).toBeLessThanOrEqual(150 * 1024);
      expect(webpSize(readFileSync(file)), s.id).toEqual({ width: s.width, height: s.height });
    }
  });

  it("ships no picture that the guide does not show", () => {
    const shown = new Set(SHOT_SLOTS.map((s) => path.basename(s.src)));
    for (const f of readdirSync(path.join(PUBLIC, "guide"))) expect(shown.has(f), f).toBe(true);
  });
});

const PUBLIC = path.join(import.meta.dirname, "../../../public");

/** A WebP file's width and height, from its header (lossy, lossless or extended). */
function webpSize(b: Buffer): { width: number; height: number } {
  expect(b.toString("ascii", 0, 4)).toBe("RIFF");
  expect(b.toString("ascii", 8, 12)).toBe("WEBP");
  const chunk = b.toString("ascii", 12, 16);
  if (chunk === "VP8L")
    return {
      width: 1 + (b[21]! | ((b[22]! & 0x3f) << 8)),
      height: 1 + ((b[22]! >> 6) | (b[23]! << 2) | ((b[24]! & 0x0f) << 10)),
    };
  if (chunk === "VP8X") return { width: 1 + b.readUIntLE(24, 3), height: 1 + b.readUIntLE(27, 3) };
  return { width: b.readUInt16LE(26) & 0x3fff, height: b.readUInt16LE(28) & 0x3fff };
}
