"use client";

import dynamic from "next/dynamic";
import { type ReactNode, useId, useState } from "react";

import { cn } from "@/lib/utils";

/** The attribution is Markdown; its renderer loads only when someone opens it. */
const Markdown = dynamic(() => import("@/components/markdown").then((m) => m.Markdown), {
  loading: () => <p className="text-[13px] text-ink-3">Loading the attribution…</p>,
});

/**
 * Where a WM-811K wafer map comes from: one short line with the citation, and the full
 * attribution from the API (Markdown) on demand. Use it wherever a wafer map is shown with the
 * API's `attribution` text; never print that text raw.
 */
export function WaferAttribution({
  attribution,
  children,
  className,
}: {
  /** The API's attribution, Markdown. */
  attribution: string;
  /** Extra text shown first when opened, such as how the wafer was chosen. */
  children?: ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  // A button, not <details>: a summary may not contain the citation link (nested interactive).
  return (
    <div className={cn("min-w-0 text-[13px] leading-5 text-ink-3", className)}>
      <p className="max-w-full">
        Wafer map from WM-811K, MIR Lab (
        <a
          href="https://doi.org/10.1109/TSM.2014.2364237"
          className="text-ink-2 underline decoration-hairline-strong underline-offset-4 hover:text-ink"
          rel="noreferrer"
        >
          Wu, Jang and Chen, 2015
        </a>
        ).{" "}
        <button
          type="button"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen((o) => !o)}
          className="cursor-pointer rounded-sm text-left text-ink-2 underline decoration-hairline-strong underline-offset-4 hover:text-ink"
        >
          {children ? "How it was chosen, licence and full attribution" : "Licence and full attribution"}
        </button>
      </p>
      <div id={id} hidden={!open} className="swap-in mt-3 grid grid-cols-[minmax(0,1fr)] gap-3 break-words">
        {children}
        {open ? (
          <Markdown className="[&_h2]:text-[14px] [&_li]:text-[13px] [&_li]:leading-5 [&_p]:text-[13px] [&_p]:leading-5 [&_ul]:text-[13px]">
            {attribution}
          </Markdown>
        ) : null}
      </div>
    </div>
  );
}
