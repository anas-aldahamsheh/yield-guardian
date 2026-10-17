"use client";

import {
  ActivityIcon,
  ArrowRightIcon,
  BotIcon,
  CheckCircle2Icon,
  FileTextIcon,
  LayersIcon,
  PlayIcon,
  ShieldCheckIcon,
  WrenchIcon,
} from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { lineHref } from "@/lib/routes";
import { cn } from "@/lib/utils";

interface InvestigationGuideBannerProps {
  exampleId?: string;
  className?: string;
}

const LIFECYCLE_STEPS = [
  {
    step: "01",
    title: "Line Excursion Trigger",
    subtitle: "Statistical Process Control",
    description: "An alarm triggers when Hotelling's T², SPE (Q), or defect risk exceeds baseline limits on a wafer unit.",
    icon: ActivityIcon,
    badge: "Detection",
    tint: "from-amber-500/10 to-transparent text-amber-500 border-amber-500/20",
  },
  {
    step: "02",
    title: "Multi-Agent Telemetry",
    subtitle: "Sensor & Tool Retrieval",
    description: "Investigator agents query FDC telemetry, SHAP feature attributions, and sensor health metrics.",
    icon: BotIcon,
    badge: "Investigation",
    tint: "from-blue-500/10 to-transparent text-blue-500 border-blue-500/20",
  },
  {
    step: "03",
    title: "Grounded Synthesis",
    subtitle: "Deterministic Fact-Check",
    description: "Writer agent synthesizes findings; verifier guarantees every cited figure matches raw sensor evidence.",
    icon: ShieldCheckIcon,
    badge: "Verification",
    tint: "from-emerald-500/10 to-transparent text-emerald-500 border-emerald-500/20",
  },
  {
    step: "04",
    title: "Engineering Sign-off",
    subtitle: "Actionable Maintenance",
    description: "The line engineer reviews findings, selects corrective actions, and dispatches a tracked work order.",
    icon: WrenchIcon,
    badge: "Execution",
    tint: "from-purple-500/10 to-transparent text-purple-500 border-purple-500/20",
  },
];

export function InvestigationGuideBanner({
  exampleId = "inv_01m4xmvsh4tg5d5j13hgf8pr2n",
  className,
}: InvestigationGuideBannerProps) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-[24px] border border-hairline bg-surface p-6 sm:p-8 md:p-10 shadow-sm",
        className,
      )}
    >
      {/* Subtle ambient gradient mesh */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-24 -right-24 h-96 w-96 rounded-full bg-signal-wash opacity-40 blur-3xl"
      />

      <div className="relative z-10">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-[760px]">
            <h2 className="text-[26px] font-[650] tracking-[-0.02em] text-ink sm:text-[32px] sm:leading-[38px]">
              How Investigations Work
            </h2>
            <p className="mt-2 text-[15.5px] leading-relaxed text-ink-2">
              Yield Guardian deploys specialized AI agents to isolate root causes when wafer sensor anomalies fire. Every finding is strictly validated against telemetry before opening maintenance work orders.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button size="sm" asChild className="gap-2 font-[580] shadow-xs">
              <Link href={`/investigations/${exampleId}`}>
                <PlayIcon className="size-3.5 fill-current" />
                Explore Sample Investigation
              </Link>
            </Button>
          </div>
        </div>

        {/* 4-Step Interactive Process Cards */}
        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {LIFECYCLE_STEPS.map((step) => {
            const Icon = step.icon;
            return (
              <div
                key={step.step}
                className="group relative flex flex-col justify-between rounded-[18px] border border-hairline bg-surface-2/60 p-5 transition-all duration-200 hover:border-hairline-strong hover:bg-surface-2 hover:shadow-sm"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <div className={cn("inline-flex size-10 items-center justify-center rounded-[12px] border bg-gradient-to-br", step.tint)}>
                      <Icon className="size-5" />
                    </div>
                    <span className="font-mono text-[12px] font-semibold text-ink-3">
                      {step.step}
                    </span>
                  </div>

                  <h3 className="mt-4 text-[16px] font-[620] tracking-tight text-ink">
                    {step.title}
                  </h3>
                  <p className="text-[12.5px] font-[520] text-ink-3">
                    {step.subtitle}
                  </p>
                  <p className="mt-2 text-[13.5px] leading-relaxed text-ink-2">
                    {step.description}
                  </p>
                </div>

                <div className="mt-4 border-t border-hairline/60 pt-3">
                  <span className="inline-flex items-center gap-1.5 text-[11.5px] font-medium text-ink-3">
                    <CheckCircle2Icon className="size-3 text-pass" />
                    {step.badge}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Value assurances */}
        <div className="mt-6 flex flex-wrap items-center justify-between gap-4 border-t border-hairline pt-5 text-[13px] text-ink-2">
          <div className="flex flex-wrap items-center gap-6">
            <span className="inline-flex items-center gap-1.5 font-medium">
              <ShieldCheckIcon className="size-4 text-signal" />
              100% Numerically Grounded (No Hallucinations)
            </span>
            <span className="inline-flex items-center gap-1.5 font-medium">
              <WrenchIcon className="size-4 text-signal" />
              Human-in-the-Loop Sign-off
            </span>
            <span className="inline-flex items-center gap-1.5 font-medium">
              <FileTextIcon className="size-4 text-signal" />
              Audited Evidence Trails
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
