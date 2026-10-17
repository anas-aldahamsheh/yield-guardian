import {
  ArrowRightIcon,
  BookOpenIcon,
  CheckCircle2Icon,
  CpuIcon,
  ShieldCheckIcon,
} from "lucide-react";
import Link from "next/link";

import { PageFrame } from "@/components/page";
import { ViewTabs } from "@/components/view-tabs";
import { WorkOrdersTab } from "@/components/work-orders/work-orders-view";

import { InvestigationsIndex } from "./investigations-list";

export type InvestigationsTab = "investigations" | "work-orders";

const TABS: { id: InvestigationsTab; label: string; href: string }[] = [
  { id: "investigations", label: "Investigations", href: "/investigations" },
  { id: "work-orders", label: "Work orders", href: "/investigations?tab=work-orders" },
];

/**
 * Investigations, with its two views as address-backed tabs: the investigations grouped by
 * where they stand, and every work order with the audit log (`?tab=work-orders`).
 */
export function InvestigationsPage({
  tab,
  order,
}: {
  tab: InvestigationsTab;
  order: string | null;
}) {
  return (
    <PageFrame>
      {/* Modern Hero Header Banner */}
      <div className="relative mb-8 overflow-hidden rounded-[24px] border border-hairline/90 bg-surface p-6 shadow-xs sm:p-8">
        {/* Ambient Decorative Glow */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -top-24 -right-24 size-96 rounded-full bg-signal/5 blur-3xl"
        />

        <div className="relative flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="max-w-[760px] space-y-3.5">
            {/* Main Title */}
            <h1 className="text-[28px] font-[680] tracking-tight text-ink sm:text-[34px] sm:leading-[40px]">
              Investigations &amp; Maintenance Queue
            </h1>

            {/* Subtitle */}
            <p className="text-[14.5px] leading-relaxed text-ink-2 sm:text-[15.5px]">
              Specialized AI agents investigate semiconductor sensor excursions, fact-check all cited findings against raw telemetry, and prepare actionable work orders for engineering sign-off.
            </p>

            {/* Core Pillars / Badges */}
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2 pt-1 text-[12.5px] text-ink-2">
              <span className="inline-flex items-center gap-1.5 font-medium">
                <ShieldCheckIcon className="size-4 text-pass" />
                100% Deterministic Grounding
              </span>
              <span className="inline-flex items-center gap-1.5 font-medium">
                <CpuIcon className="size-4 text-signal" />
                Multi-Agent Synthesis
              </span>
              <span className="inline-flex items-center gap-1.5 font-medium">
                <CheckCircle2Icon className="size-4 text-ink-2" />
                Human-in-the-Loop Sign-off
              </span>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="flex flex-wrap items-center gap-3 lg:flex-col lg:items-end">
            <Link
              href="/line"
              className="inline-flex h-9 items-center gap-1.5 rounded-full bg-ink px-4 text-[13px] font-[550] text-surface no-underline shadow-xs transition-opacity hover:opacity-90"
            >
              <span>Simulate on Fab Line</span>
              <ArrowRightIcon className="size-3.5 transition-transform duration-(--dur-2) group-hover:translate-x-0.5" />
            </Link>
          </div>
        </div>
      </div>
      <ViewTabs
        label="Investigations views"
        items={TABS}
        current={tab}
        className="mb-10 sm:mb-12"
      />
      {tab === "work-orders" ? <WorkOrdersTab order={order} /> : <InvestigationsIndex />}
    </PageFrame>
  );
}
