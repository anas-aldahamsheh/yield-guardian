"use client";

import type { ComponentProps } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { useScrollFocus } from "@/lib/use-scroll-focus";
import { cn } from "@/lib/utils";

import { ScrollRegion } from "./scroll-region";

/**
 * Markdown from the API (model cards, chat answers), drawn with the console's type. Raw HTML in
 * the source is not rendered; links leave the product in a new tab without a referrer.
 */
const components: Components = {
  h1: ({ node: _n, ...p }) => <h2 className="mt-6 text-[20px] leading-7 font-semibold text-ink first:mt-0" {...p} />,
  h2: ({ node: _n, ...p }) => <h3 className="mt-6 text-[16px] leading-6 font-semibold text-ink first:mt-0" {...p} />,
  h3: ({ node: _n, ...p }) => <h4 className="mt-5 text-[14px] leading-5 font-semibold text-ink first:mt-0" {...p} />,
  p: ({ node: _n, ...p }) => <p className="mt-3 text-[15px] leading-6 text-ink-2 first:mt-0" {...p} />,
  ul: ({ node: _n, ...p }) => <ul className="mt-3 grid grid-cols-[minmax(0,1fr)] list-disc gap-1 pl-5 text-[15px] leading-6 text-ink-2" {...p} />,
  ol: ({ node: _n, ...p }) => <ol className="mt-3 grid grid-cols-[minmax(0,1fr)] list-decimal gap-1 pl-5 text-[15px] leading-6 text-ink-2" {...p} />,
  a: ({ node: _n, href, ...p }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-ink underline decoration-hairline-strong underline-offset-4 hover:decoration-ink" {...p} />
  ),
  code: ({ node: _n, className, ...p }) => <code className={cn("tnum rounded-[2px] bg-die-2 px-1 text-[13px] [overflow-wrap:anywhere]", className)} {...p} />,
  pre: ({ node: _n, ...p }) => <ScrollPre {...p} />,
  blockquote: ({ node: _n, ...p }) => <blockquote className="mt-3 border-l-2 border-hairline-strong pl-3 text-ink-2" {...p} />,
  table: ({ node: _n, ...p }) => (
    <ScrollRegion label="Table" className="mt-3">
      <table className="w-full border-collapse text-left text-[13px] leading-5" {...p} />
    </ScrollRegion>
  ),
  th: ({ node: _n, ...p }) => <th className="border-b border-hairline-strong px-2 py-1.5 font-normal text-ink-3" {...p} />,
  td: ({ node: _n, ...p }) => <td className="tnum border-b border-hairline px-2 py-1.5 text-ink" {...p} />,
  hr: () => <hr className="my-5 border-hairline" />,
};

export function Markdown({ children, className, ...props }: { children: string; className?: string } & Omit<ComponentProps<"div">, "children">) {
  return (
    <div className={cn("min-w-0", className)} {...props}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  );
}

/** A code block; while it scrolls sideways it is in the tab order. */
function ScrollPre(props: ComponentProps<"pre">) {
  const ref = useScrollFocus<HTMLPreElement>();
  return <pre ref={ref} className="mt-3 overflow-x-auto rounded-sm bg-die-2 p-3 text-[13px] leading-5" {...props} />;
}
