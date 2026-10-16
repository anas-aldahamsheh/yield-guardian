"use client";

import { ChevronDown, Search } from "lucide-react";
import Image from "next/image";
import { useEffect, useMemo, useState } from "react";

import { ScrollRegion } from "@/components/scroll-region";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import { type Block, CATEGORIES, ENTRIES, type Entry } from "./guide-content";

const ALL = "all";

/** Letters an Arabic reader treats as the same when searching: alef forms, ya, ta marbuta, diacritics. */
export function normalizeArabic(text: string): string {
  return text
    .toLowerCase()
    .replace(/[ً-ٰٟـ]/g, "")
    .replace(/[أإآ]/g, "ا")
    .replace(/ى/g, "ي")
    .replace(/ة/g, "ه")
    .replace(/ؤ/g, "و")
    .replace(/ئ/g, "ي");
}

function blockText(block: Block): string {
  switch (block.type) {
    case "p":
    case "note":
      return block.text;
    case "list":
    case "steps":
      return block.items.join(" ");
    case "table":
      return [...block.head, ...block.rows.flat()].join(" ");
    case "shot":
      return block.caption;
  }
}

const SEARCH_INDEX = new Map<string, string>(
  ENTRIES.map((e) => [e.id, normalizeArabic([e.title, ...e.blocks.map(blockText)].join(" "))]),
);

/** Entries whose title or text holds every word of the query. */
export function matchEntries(entries: readonly Entry[], query: string): Entry[] {
  const words = normalizeArabic(query).split(/\s+/).filter(Boolean);
  if (words.length === 0) return [...entries];
  return entries.filter((e) => {
    const text = SEARCH_INDEX.get(e.id) ?? "";
    return words.every((w) => text.includes(w));
  });
}

/**
 * The Arabic guide as the last section of How it works: search, categories and entries that
 * open in place. `#<entry id>` in the address opens that entry.
 */
export function GuideSection() {
  const [category, setCategory] = useState<string>(ALL);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<ReadonlySet<string>>(() => new Set());

  // A link to a paragraph (#id) opens it and brings it into view.
  useEffect(() => {
    const id = decodeURIComponent(window.location.hash.slice(1));
    if (!id || !ENTRIES.some((e) => e.id === id)) return;
    const frame = requestAnimationFrame(() => {
      setOpen(new Set([id]));
      document.getElementById(id)?.scrollIntoView({ block: "start" });
    });
    return () => cancelAnimationFrame(frame);
  }, []);

  const shown = useMemo(() => {
    const inCategory = category === ALL ? ENTRIES : ENTRIES.filter((e) => e.category === category);
    return matchEntries(inCategory, query);
  }, [category, query]);

  const counts = useMemo(() => {
    const matched = matchEntries(ENTRIES, query);
    const byCategory = new Map<string, number>();
    for (const e of matched) byCategory.set(e.category, (byCategory.get(e.category) ?? 0) + 1);
    return { all: matched.length, byCategory };
  }, [query]);

  const onSearch = (value: string) => {
    setQuery(value);
    // Searching opens what it finds, so the matching words are on screen.
    if (value.trim()) setOpen(new Set(matchEntries(ENTRIES, value).map((e) => e.id)));
  };

  const toggle = (id: string, isOpen: boolean) => {
    setOpen((prev) => {
      if (prev.has(id) === isOpen) return prev;
      const next = new Set(prev);
      if (isOpen) next.add(id);
      else next.delete(id);
      return next;
    });
    if (isOpen) window.history.replaceState(null, "", `#${id}`);
  };

  const groups = CATEGORIES.map((c) => ({
    category: c,
    entries: shown.filter((e) => e.category === c.id),
  })).filter((g) => g.entries.length > 0);

  return (
    <div className="guide mx-auto max-w-[1040px]">
      <header className="mb-8">
        <h2
          id="guide-title"
          className="text-[32px] leading-[1.4] font-[640] text-ink sm:text-[44px] sm:leading-[1.3]"
        >
          دليل الاستخدام
        </h2>
        <p className="mt-4 max-w-[64ch] text-[17px] leading-9 text-ink-2">
          البرنامج خطوة بخطوة بكلام بسيط: الصفحات، وطرق البدء، والمحطات، والإنذارات، والتحقيق،
          والموافقة، وأوامر العمل، والمحادثة، والحاسبة، والحدود. أسماء الأزرار بالإنجليزية كما تظهر
          على الشاشة. لا يحتوي الدليل أرقاماً مقاسة: الأرقام كلها في الأقسام أعلاه، تُقرأ مباشرة من
          الموديلات.
        </p>
      </header>

      <div className="sticky top-[calc(var(--bar-height)+8px)] z-20 mb-10 rounded-[22px] bg-canvas/94 p-3 shadow-[inset_0_0_0_1px_var(--hairline),0_16px_40px_-28px_rgb(0_0_0/0.45)] backdrop-blur-xl sm:p-3.5">
        <div className="flex flex-wrap items-center gap-2">
          <label className="relative min-w-0 flex-1 basis-56">
            <span className="sr-only">ابحث في الدليل</span>
            <Search
              aria-hidden="true"
              className="pointer-events-none absolute top-1/2 right-4 size-4 -translate-y-1/2 text-ink-3"
            />
            <Input
              type="search"
              value={query}
              onChange={(e) => onSearch(e.target.value)}
              placeholder="ابحث: مثلاً «الإنذار» أو «Investigate» أو «ملف»"
              className="h-11 rounded-full pr-10 text-[15px]"
            />
          </label>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setOpen(new Set(shown.map((e) => e.id)))}
            >
              افتح الكل
            </Button>
            <Button variant="outline" size="sm" onClick={() => setOpen(new Set())}>
              أغلق الكل
            </Button>
          </div>
        </div>
        <div
          role="group"
          aria-label="اختر قسماً"
          className="-mx-3 mt-3 flex [scrollbar-width:none] gap-1.5 overflow-x-auto px-3 pb-1 sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0 sm:pb-0"
        >
          <Chip
            active={category === ALL}
            onClick={() => setCategory(ALL)}
            label="الكل"
            count={counts.all}
          />
          {CATEGORIES.map((c) => (
            <Chip
              key={c.id}
              active={category === c.id}
              onClick={() => setCategory(c.id)}
              label={c.label}
              count={counts.byCategory.get(c.id) ?? 0}
            />
          ))}
        </div>
      </div>

      {groups.length === 0 ? (
        <div className="unexposed swap-in rounded-[20px] px-5 py-10 text-center text-[16px] leading-8 text-ink-2 shadow-[inset_0_0_0_1px_var(--hairline)]">
          لا توجد نتيجة لـ «{query}» في هذا القسم. جرّب كلمة أخرى أو اختر «الكل».
        </div>
      ) : (
        <div className="grid grid-cols-[minmax(0,1fr)] gap-14">
          {groups.map(({ category: c, entries }) => (
            <section key={c.id} aria-labelledby={`guide-cat-${c.id}`}>
              <h3
                id={`guide-cat-${c.id}`}
                className="text-[24px] leading-[1.5] font-[640] text-ink"
              >
                {c.label}
              </h3>
              <p className="mt-1 mb-5 text-[16px] leading-8 text-ink-2">{c.lede}</p>
              <div className="grid grid-cols-[minmax(0,1fr)] gap-2">
                {entries.map((e) => (
                  <EntryPanel
                    key={e.id}
                    entry={e}
                    open={open.has(e.id)}
                    onToggle={(o) => toggle(e.id, o)}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

function Chip({
  active,
  onClick,
  label,
  count,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  count: number;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "press inline-flex h-9 shrink-0 items-center gap-2 rounded-full px-3.5 text-[14px] leading-6",
        active
          ? "bg-ink text-canvas"
          : "text-ink-2 shadow-[inset_0_0_0_1px_var(--hairline-strong)] hover:bg-surface-2 hover:text-ink",
      )}
    >
      {label}
      <span className={cn("tnum text-[12px]", active ? "text-canvas/70" : "text-ink-3")}>
        {count}
      </span>
    </button>
  );
}

function EntryPanel({
  entry,
  open,
  onToggle,
}: {
  entry: Entry;
  open: boolean;
  onToggle: (open: boolean) => void;
}) {
  return (
    <details
      id={entry.id}
      open={open}
      onToggle={(e) => onToggle(e.currentTarget.open)}
      className="group/entry panel glow scroll-mt-60"
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 rounded-[inherit] px-5 py-4 text-[16px] leading-7 font-[600] text-ink sm:px-6 [&::-webkit-details-marker]:hidden">
        <span className="min-w-0">{entry.title}</span>
        <span
          aria-hidden="true"
          className="grid size-8 shrink-0 place-items-center rounded-full bg-surface-2 text-ink-2 transition-[background-color,color,rotate] duration-(--dur-4) ease-spring group-open/entry:rotate-180 group-open/entry:bg-ink! group-open/entry:text-canvas! group-hover/entry:bg-surface-3"
        >
          <ChevronDown className="size-4" strokeWidth={2} />
        </span>
      </summary>
      <div className="grow-in grid grid-cols-[minmax(0,1fr)] gap-5 border-t border-hairline px-5 pt-5 pb-6 text-[16px] leading-8 text-ink sm:px-6">
        {entry.blocks.map((b, i) => (
          <BlockView key={i} block={b} label={`جدول ${i + 1}: ${entry.title}`} />
        ))}
      </div>
    </details>
  );
}

function BlockView({ block, label }: { block: Block; label: string }) {
  switch (block.type) {
    case "p":
      return <p>{block.text}</p>;
    case "note":
      return <p className="lit rounded-[14px] px-4 py-3 text-ink">{block.text}</p>;
    case "list":
      return (
        <ul className="grid list-disc gap-1.5 ps-5 marker:text-ink-3">
          {block.items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      );
    case "steps":
      return (
        <ol className="grid list-decimal gap-1.5 ps-6 marker:text-ink-3">
          {block.items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ol>
      );
    case "table": {
      const hasHead = block.head.some((h) => h.trim() !== "");
      return (
        <ScrollRegion label={label}>
          <table className="w-full min-w-[480px] border-collapse text-[14px] leading-7">
            {hasHead ? (
              <thead>
                <tr className="border-b border-hairline">
                  {block.head.map((h, i) => (
                    <th
                      key={i}
                      scope="col"
                      className="px-2 py-2 text-start text-[13px] font-[560] text-ink-3"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
            ) : null}
            <tbody>
              {block.rows.map((row, r) => (
                <tr key={r} className="border-b border-hairline last:border-b-0">
                  {row.map((cell, c) =>
                    c === 0 ? (
                      <th
                        key={c}
                        scope="row"
                        className="px-2 py-2 text-start align-top font-[560] text-ink"
                      >
                        {cell}
                      </th>
                    ) : (
                      <td key={c} className="px-2 py-2 align-top text-ink-2">
                        {cell}
                      </td>
                    ),
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollRegion>
      );
    }
    case "shot":
      // A screenshot of the real product, at most its own width (a narrow crop is not blown up).
      // The files are already compressed (public/guide/), so they are served as they are and the
      // interface text in them stays sharp.
      return (
        <figure className="grid gap-2" data-shot={block.id}>
          <Image
            src={block.src}
            alt={block.alt}
            width={block.width}
            height={block.height}
            unoptimized
            style={{ maxWidth: block.width }}
            className="h-auto w-full rounded-[14px] shadow-[0_0_0_1px_var(--hairline),0_18px_40px_-28px_rgb(0_0_0/0.45)]"
          />
          <figcaption className="text-[14px] leading-7 text-ink-2">{block.caption}</figcaption>
        </figure>
      );
  }
}
