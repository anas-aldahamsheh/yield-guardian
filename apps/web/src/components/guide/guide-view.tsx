import Image from "next/image";

import { ScrollRegion } from "@/components/scroll-region";

import { type Block, CATEGORIES, ENTRIES, type Entry } from "./guide-content";

/** The id of a guide category's section, for links and the page's section map. */
export const guideCategoryId = (category: string) => `guide-cat-${category}`;

/**
 * The user guide as the last section of How it works: category links, then every entry in
 * full, each a heading and short points.
 */
export function GuideSection() {
  const groups = CATEGORIES.map((c) => ({
    category: c,
    entries: ENTRIES.filter((e) => e.category === c.id),
  })).filter((g) => g.entries.length > 0);

  return (
    <div className="guide mx-auto max-w-[1040px]">
      <header className="mb-8">
        <h2
          id="guide-title"
          className="text-[32px] leading-[1.25] font-[640] text-ink sm:text-[44px] sm:leading-[1.15]"
        >
          User guide
        </h2>
        <p className="mt-4 max-w-[64ch] text-[17px] leading-8 text-ink-2">
          The product step by step: pages, ways to start, stations, alarms, investigation, approval,
          chat and the calculator. Measured numbers are in the expert sections above.
        </p>
      </header>

      <nav
        aria-label="Guide sections"
        className="-mx-3 mb-12 flex [scrollbar-width:none] gap-1.5 overflow-x-auto px-3 pb-1 sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0 sm:pb-0"
      >
        {groups.map(({ category: c }) => (
          <a
            key={c.id}
            href={`#${guideCategoryId(c.id)}`}
            className="press inline-flex h-9 shrink-0 items-center rounded-full px-3.5 text-[14px] leading-6 text-ink-2 no-underline shadow-[inset_0_0_0_1px_var(--hairline-strong)] hover:bg-surface-2 hover:text-ink"
          >
            {c.label}
          </a>
        ))}
      </nav>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-14">
        {groups.map(({ category: c, entries }) => (
          <section
            key={c.id}
            id={guideCategoryId(c.id)}
            aria-labelledby={`${guideCategoryId(c.id)}-title`}
            className="scroll-mt-[calc(var(--bar-height)+72px)]"
          >
            <h3
              id={`${guideCategoryId(c.id)}-title`}
              className="text-[24px] leading-[1.35] font-[640] text-ink"
            >
              {c.label}
            </h3>
            <p className="mt-1 mb-5 text-[16px] leading-7 text-ink-2">{c.lede}</p>
            <div className="grid grid-cols-[minmax(0,1fr)] gap-3">
              {entries.map((e) => (
                <EntryPanel key={e.id} entry={e} />
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

function EntryPanel({ entry }: { entry: Entry }) {
  return (
    <article
      id={entry.id}
      aria-labelledby={`${entry.id}-title`}
      className="panel glow scroll-mt-[calc(var(--bar-height)+72px)]"
    >
      <h4
        id={`${entry.id}-title`}
        className="px-5 pt-4 text-[16px] leading-7 font-[600] text-ink sm:px-6"
      >
        {entry.title}
      </h4>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 px-5 pt-3 pb-5 text-[16px] leading-7 text-ink sm:px-6">
        {entry.blocks.map((b, i) => (
          <BlockView key={i} block={b} label={`Table ${i + 1}: ${entry.title}`} />
        ))}
      </div>
    </article>
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
