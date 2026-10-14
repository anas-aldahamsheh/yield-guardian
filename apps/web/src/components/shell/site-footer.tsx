"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { useApi } from "@/lib/api/context";
import { q } from "@/lib/api/queries";

export function SiteFooter() {
  const api = useApi();
  const meta = useQuery(q.meta(api));
  const bundles = meta.data?.bundles ?? [];

  return (
    <footer className="border-t border-hairline">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-start justify-between gap-x-10 gap-y-3 px-gutter py-6 text-[13px] leading-5 text-ink-3">
        <p className="max-w-[60ch]">
          Plant data: SECOM (UCI Machine Learning Repository). Wafer maps: WM-811K (MIR Lab,
          National Tsing Hua University). Findings are associations in historical data, not causes.{" "}
          <Link href="/methods" className="text-ink-2 underline hover:text-ink">
            Methods and limitations
          </Link>
        </p>
        {meta.data ? (
          <dl className="flex flex-wrap gap-x-6 gap-y-1">
            <div className="flex gap-1.5">
              <dt>Version</dt>
              <dd className="tnum text-ink-2">
                {meta.data.version}
                {meta.data.git_commit ? ` (${meta.data.git_commit.slice(0, 7)})` : ""}
              </dd>
            </div>
            {bundles.map((b) => (
              <div key={b.bundle.name} className="flex gap-1.5">
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
