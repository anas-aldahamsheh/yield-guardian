"use client";

import { ChevronDown, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { PageFrame } from "@/components/page";
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
    case "fix":
      return [block.problem, block.solution, block.result ?? ""].join(" ");
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

export function GuideView() {
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
    <PageFrame>
      <div lang="ar" dir="rtl" className="guide mx-auto max-w-[920px]">
        <header className="mb-6">
          <h1 className="text-[28px] leading-10 font-semibold text-ink sm:text-[34px] sm:leading-[48px]">
            دليل الاستخدام
          </h1>
          <p className="mt-2 text-[16px] leading-8 text-ink-2">
            شرح كامل لـ Yield Guardian بكلام بسيط: ماذا يفعل، وكيف تستخدم كل شاشة، وما الموديلات
            وعلى كم بيانات تدربت، ومن أين تأتي البيانات وإلى أين تذهب، والمشاكل التي واجهناها وكيف
            حللناها، وكيف تتحقق من النجاح بنفسك. كل رقم هنا منقول من بطاقات الموديلات وتقارير
            القياس، ولا يوجد رقم مقدّر.
          </p>
        </header>

        <div className="sticky top-bar z-20 -mx-gutter mb-8 border-y border-hairline bg-room px-gutter py-3">
          <div className="flex flex-wrap items-center gap-2">
            <label className="relative min-w-0 flex-1 basis-56">
              <span className="sr-only">ابحث في الدليل</span>
              <Search
                aria-hidden="true"
                className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-ink-3"
              />
              <Input
                type="search"
                value={query}
                onChange={(e) => onSearch(e.target.value)}
                placeholder="ابحث: مثلاً «الإنذار» أو «CNN» أو «البيانات»"
                className="h-10 pr-9 text-[15px]"
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
            className="-mx-gutter mt-3 flex gap-1.5 overflow-x-auto px-gutter pb-1 sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0 sm:pb-0"
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
          <div className="panel px-5 py-8 text-center text-[15px] leading-7 text-ink-2">
            لا توجد نتيجة لـ «{query}» في هذا القسم. جرّب كلمة أخرى أو اختر «الكل».
          </div>
        ) : (
          <div className="grid grid-cols-[minmax(0,1fr)] gap-12">
            {groups.map(({ category: c, entries }) => (
              <section key={c.id} aria-labelledby={`cat-${c.id}`}>
                <h2 id={`cat-${c.id}`} className="text-[22px] leading-9 font-semibold text-ink">
                  {c.label}
                </h2>
                <p className="mt-1 mb-4 text-[15px] leading-7 text-ink-2">{c.lede}</p>
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
    </PageFrame>
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
        "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1 text-[14px] leading-6 transition-colors",
        active
          ? "border-safelight bg-safelight-wash text-ink"
          : "border-hairline text-ink-2 hover:bg-accent hover:text-ink",
      )}
    >
      {label}
      <span className="tnum text-[12px] text-ink-3">{count}</span>
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
      className="group panel scroll-mt-60"
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-3.5 text-[16px] leading-7 font-semibold text-ink sm:px-5 [&::-webkit-details-marker]:hidden">
        <span className="min-w-0">{entry.title}</span>
        <ChevronDown
          aria-hidden="true"
          className="size-4 shrink-0 text-ink-3 transition-transform group-open:rotate-180"
        />
      </summary>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 border-t border-hairline px-4 pt-4 pb-5 text-[15px] leading-8 text-ink sm:px-5">
        {entry.blocks.map((b, i) => (
          <BlockView key={i} block={b} />
        ))}
      </div>
    </details>
  );
}

function BlockView({ block }: { block: Block }) {
  switch (block.type) {
    case "p":
      return <p>{block.text}</p>;
    case "note":
      return (
        <p className="border-s-2 border-safelight bg-safelight-wash px-4 py-2.5 text-ink">
          {block.text}
        </p>
      );
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
        <div className="overflow-x-auto">
          <table className="w-full min-w-[480px] border-collapse text-[14px] leading-7">
            {hasHead ? (
              <thead>
                <tr className="border-b border-hairline-strong">
                  {block.head.map((h, i) => (
                    <th
                      key={i}
                      scope="col"
                      className="px-2 py-1.5 text-start font-semibold text-ink-2"
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
                        className="px-2 py-1.5 text-start align-top font-medium text-ink"
                      >
                        {cell}
                      </th>
                    ) : (
                      <td key={c} className="px-2 py-1.5 align-top text-ink-2">
                        {cell}
                      </td>
                    ),
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    case "fix":
      return (
        <dl className="grid grid-cols-[minmax(0,1fr)] gap-3">
          <div>
            <dt className="text-[13px] font-semibold text-fail">المشكلة</dt>
            <dd>{block.problem}</dd>
          </div>
          <div>
            <dt className="text-[13px] font-semibold text-pass">الحل</dt>
            <dd>{block.solution}</dd>
          </div>
          {block.result ? (
            <div>
              <dt className="text-[13px] font-semibold text-ink-3">النتيجة</dt>
              <dd>{block.result}</dd>
            </div>
          ) : null}
        </dl>
      );
  }
}
