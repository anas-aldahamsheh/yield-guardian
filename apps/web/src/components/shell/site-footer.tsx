"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ActivityIcon,
  CheckCircle2Icon,
  DatabaseIcon,
  ExternalLinkIcon,
  GitBranchIcon,
  LayersIcon,
  ShieldCheckIcon,
} from "lucide-react";
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
    <footer className="mt-16 border-t border-hairline/80 bg-surface-2/40 backdrop-blur-xs">
      {/* Main Footer Content */}
      <div className="mx-auto max-w-[1600px] px-gutter pt-12 pb-24 text-[13px] leading-5 text-ink-3">
        <div className="grid grid-cols-1 gap-10 md:grid-cols-2 lg:grid-cols-12">
          {/* Column 1: Brand & Overview (4 cols) */}
          <div className="space-y-4 lg:col-span-4">
            <div className="flex items-center gap-2.5">
              <WaferMark idPrefix="yg-footer-mark" className="size-6 shrink-0 text-ink" />
              <span className="font-display text-[16px] font-[650] tracking-tight text-ink">
                Yield Guardian
              </span>
            </div>
            <p className="max-w-[38ch] text-[13px] leading-relaxed text-ink-2">
              Autonomous root-cause analysis and excursion triage engine for semiconductor wafer
              fabrication.
            </p>
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-hairline bg-surface px-2.5 py-1 text-[11.5px] font-medium text-ink-2">
                <DatabaseIcon className="size-3 text-signal" />
                SECOM (UCI)
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-hairline bg-surface px-2.5 py-1 text-[11.5px] font-medium text-ink-2">
                <LayersIcon className="size-3 text-signal" />
                WM-811K (MIR Lab)
              </span>
            </div>
          </div>

          {/* Column 2: Platform Navigation (2 cols) */}
          <div className="space-y-3 lg:col-span-2">
            <h4 className="text-[12px] font-[600] tracking-wider text-ink uppercase">Platform</h4>
            <ul className="space-y-2 text-[13px]">
              <li>
                <Link
                  href="/line"
                  className="text-ink-2 transition-colors duration-(--dur-1) hover:text-ink"
                >
                  Line Monitor
                </Link>
              </li>
              <li>
                <Link
                  href="/investigations"
                  className="text-ink-2 transition-colors duration-(--dur-1) hover:text-ink"
                >
                  Investigations
                </Link>
              </li>
              <li>
                <Link
                  href="/how"
                  className="text-ink-2 transition-colors duration-(--dur-1) hover:text-ink"
                >
                  How It Works
                </Link>
              </li>
              <li>
                <Link
                  href={howHref("methods")}
                  className="text-ink-2 transition-colors duration-(--dur-1) hover:text-ink"
                >
                  Methods
                </Link>
              </li>
            </ul>
          </div>

          {/* Column 3: Telemetry & Models Status Card (3 cols) */}
          <div className="space-y-3 lg:col-span-3">
            <h4 className="text-[12px] font-[600] tracking-wider text-ink uppercase">
              Engine &amp; Model Verifications
            </h4>
            <div className="space-y-2 rounded-[14px] border border-hairline bg-surface p-3.5 shadow-2xs">
              <div className="flex items-center justify-between text-[12px]">
                <span className="flex items-center gap-1.5 text-ink-2">
                  <span className="size-1.5 rounded-full bg-pass" />
                  Engine Core
                </span>
                <span className="tnum font-mono text-[11.5px] text-ink">
                  {meta.data?.version ?? "0.1.0"}
                  {meta.data?.git_commit ? ` (${meta.data.git_commit.slice(0, 7)})` : ""}
                </span>
              </div>

              {bundles.map((b) => (
                <div
                  key={b.bundle.name}
                  className="flex items-center justify-between border-t border-hairline/60 pt-2 text-[12px]"
                >
                  <span className="text-ink-2">
                    {b.bundle.name === "secom" ? "SECOM Models" : "Wafer Defect Models"}
                  </span>
                  <span className="inline-flex items-center gap-1 font-mono text-[11px] text-pass">
                    <CheckCircle2Icon className="size-3" />
                    {b.bundle.version} verified
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Column 4: Observational Guardrail Notice (3 cols) */}
          <div className="space-y-3 lg:col-span-3">
            <h4 className="text-[12px] font-[600] tracking-wider text-ink uppercase">
              Statistical Scope
            </h4>
            <div className="rounded-[14px] border border-hairline/80 bg-surface/60 p-3.5 text-[12px] leading-relaxed text-ink-2">
              <p>
                Findings represent statistical associations in historical fab telemetry, not
                physical causes. All corrective actions require engineer sign-off.
              </p>
              <div className="mt-2.5">
                <Link
                  href={howHref("methods")}
                  className="inline-flex items-center gap-1 text-[11.5px] font-medium text-ink underline decoration-hairline-strong underline-offset-2 hover:decoration-ink"
                >
                  Read the methodology
                  <ExternalLinkIcon className="size-3" />
                </Link>
              </div>
            </div>
          </div>
        </div>

        {/* Bottom Bar: Copyright & Operational State */}
        <div className="mt-10 flex flex-wrap items-center justify-between gap-4 border-t border-hairline/70 pt-6 text-[12px] text-ink-3">
          <p>© 2026 Yield Guardian. Autonomous Semiconductor RCA Engine.</p>
          <div className="flex items-center gap-4">
            <span className="inline-flex items-center gap-1.5 text-pass">
              <span className="live-dot size-1.5" />
              Telemetry Pipelines Connected
            </span>
          </div>
        </div>
      </div>
    </footer>
  );
}
