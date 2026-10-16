import { Panel } from "@/components/page";

/**
 * A list of limits as the API states them. In a module of its own so the product's limitations
 * on /how do not pull the method tracks (and their charts) into the page's first load.
 */
export function Limitations({ items, title }: { items: string[]; title: string }) {
  if (!items.length) return null;
  return (
    <Panel title={title}>
      <ul className="grid max-w-[90ch] list-disc grid-cols-[minmax(0,1fr)] gap-1.5 pl-5 text-[14px] leading-6 text-ink-2">
        {items.map((l) => (
          <li key={l}>{l}</li>
        ))}
      </ul>
    </Panel>
  );
}
