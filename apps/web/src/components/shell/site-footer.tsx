"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { useApi } from "@/lib/api/context";
import { q } from "@/lib/api/queries";
import { howHref } from "@/lib/routes";

import { WaferMark } from "./wordmark";

export function SiteFooter() {
  const api = useApi();
  const meta = useQuery(q.meta(api));
  const bundles = meta.data?.bundles ?? [];

  return (
    <footer className="mt-8 border-t border-hairline">
      {/* The bottom padding is the floating Ask button's place at the end of a page (ask-button.tsx). */}
      <div className="mx-auto grid max-w-[1600px] gap-x-12 gap-y-6 px-gutter pt-10 pb-28 text-[13px] leading-5 text-ink-3 lg:grid-cols-[minmax(0,1fr)_auto]">
        <div className="flex max-w-[68ch] gap-4">
          <WaferMark idPrefix="yg-footer-mark" className="mt-0.5 size-6 shrink-0 text-ink-2" />
          <p>
            Plant data: SECOM (UCI Machine Learning Repository). Wafer maps: WM-811K (MIR Lab,
            National Tsing Hua University). Findings are associations in historical data, not
            causes.{" "}
            <Link
              href={howHref("limits")}
              className="text-ink-2 underline decoration-hairline-strong underline-offset-4 transition-colors duration-(--dur-1) hover:text-ink hover:decoration-signal"
            >
              How it works, and its limits
            </Link>
          </p>
        </div>
        {meta.data ? (
          <dl className="grid content-start gap-x-8 gap-y-1.5 sm:grid-cols-[auto_auto] lg:justify-end">
            <div className="flex gap-2">
              <dt>Version</dt>
              <dd className="tnum text-ink-2">
                {meta.data.version}
                {meta.data.git_commit ? ` (${meta.data.git_commit.slice(0, 7)})` : ""}
              </dd>
            </div>
            {bundles.map((b) => (
              <div key={b.bundle.name} className="flex gap-2">
                <dt>{b.bundle.name === "secom" ? "SECOM models" : "Wafer models"}</dt>
                <dd className="tnum text-ink-2">
                  {b.bundle.version}, {b.verified ? "checksums verified" : "checksums not verified"}
                </dd>
              </div>
            ))}
          </dl>
        ) : null}
      </div>
    </footer>
  );
}
