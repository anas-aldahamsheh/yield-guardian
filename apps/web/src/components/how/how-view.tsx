import type { ReactNode } from "react";

import { CATEGORIES } from "@/components/guide/guide-content";
import { GuideSection, guideCategoryId } from "@/components/guide/guide-view";
import {
  DataProvenance,
  MeasuredResults,
  ModelCardsPanel,
} from "@/components/methods/methods-view";
import { AiRoles } from "@/components/models/models-view";
import { PageFrame } from "@/components/page";
import type { HowAnchor } from "@/lib/routes";

import { Disclosure } from "./disclosure";
import { SecomMethods, WaferMethods } from "./method-tracks";
import { HowIntro } from "./intro";
import { SavingsCalculator } from "./savings-calculator";
import { type RailItem, SectionMenu, SectionRail } from "./section-rail";

const EXPERT_SECTIONS: { id: HowAnchor; label: string }[] = [
  { id: "results", label: "Measured results" },
  { id: "models", label: "Models" },
  { id: "methods", label: "Methods" },
  { id: "data", label: "Data and licences" },
  { id: "calculator", label: "Savings calculator" },
  { id: "guide", label: "User guide" },
];

/** The page's sections in page order, for the section map. */
const RAIL: readonly RailItem[] = [
  { id: "intro", label: "Introduction", level: 0 },
  { id: "what", label: "What it does", level: 1 },
  { id: "inputs", label: "Two kinds of input", level: 1 },
  { id: "sources", label: "Where the data comes from", level: 1 },
  { id: "experts", label: "For experts", level: 0 },
  ...EXPERT_SECTIONS.filter((s) => s.id !== "guide").map((s) => ({
    id: s.id,
    label: s.label,
    level: 1 as const,
  })),
  { id: "guide", label: "User guide", level: 0 },
  ...CATEGORIES.filter((c) => c.id !== "calculator").map((c) => ({ id: guideCategoryId(c.id), label: c.label, level: 1 as const })),
];

/**
 * How it works: a plain introduction, then "For experts", then the user guide, with a section
 * map on the right on wide screens.
 * Every number on the page is read from the API, which reads the bundles.
 */
export function HowView() {
  return (
    <PageFrame className="pt-10">
      <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_240px] lg:gap-12 xl:gap-16">
        <div className="min-w-0">
          <SectionMenu items={RAIL} />
          <HowIntro />

          <section
            id="experts"
            lang="en"
            dir="ltr"
            className="mt-20 scroll-mt-[calc(var(--bar-height)+72px)] border-t border-hairline pt-16 sm:mt-28 sm:pt-20"
            aria-labelledby="experts-title"
          >
            <header className="max-w-[80ch]">
              <h2
                id="experts-title"
                className="text-display font-[660] text-ink [font-stretch:112%]"
              >
                For experts
              </h2>
              <p className="mt-4 max-w-[66ch] text-[17px] leading-7 text-ink-2">
                Every number below is read from the API, which reads the model bundles: none is
                typed into this page. Each result comes with its confidence interval and the data it
                was measured on. Findings are associations in historical data, not causes.
              </p>
            </header>

            <div className="mt-14 grid grid-cols-[minmax(0,1fr)] gap-20 sm:gap-24">
              <Section
                id="results"
                title="Measured results"
                lede="The headline numbers. A row reads “Not measured yet” until it has been measured on held-out data."
              >
                <MeasuredResults />
              </Section>

              <Section
                id="models"
                title="Models"
                lede="The trained models, as their model cards describe them, and the language-model roles that write and explain: Claude Haiku 5.5 (Anthropic) on every role but document reading (OCR). The evaluations listed under them are earlier measurements of candidate models."
              >
                <Disclosure
                  title="Model cards"
                  summary="Written by each training pipeline with its bundle: data, method, results and limits."
                >
                  <ModelCardsPanel />
                </Disclosure>
                <h3 className="mt-10 mb-4 text-[20px] leading-7 font-[640] tracking-[-0.015em] text-ink">
                  AI roles
                </h3>
                <AiRoles />
              </Section>

              <Section
                id="methods"
                title="Methods"
                lede="How each number was measured: the splits, the baselines, the intervals and the operating points. Each track opens in place."
              >
                <div className="grid grid-cols-[minmax(0,1fr)] gap-street">
                  <Disclosure
                    title="SECOM: control charts and failure risk"
                    summary="Time-ordered splits, the risk models against their baselines, calibration, operating points and the control-chart limits."
                  >
                    <SecomMethods />
                  </Disclosure>
                  <Disclosure
                    title="Wafer maps: patterns, unknown patterns and similar wafers"
                    summary="The pattern classifier on the official and lot-grouped splits, the unknown-pattern check and similar-wafer retrieval."
                  >
                    <WaferMethods />
                  </Disclosure>
                </div>
              </Section>

              <Section
                id="data"
                title="Data and licences"
                lede="The datasets with their sources, licences and checksums, and the bundles the API loaded."
              >
                <DataProvenance />
              </Section>

              <Section
                id="calculator"
                title="Savings calculator"
                lede="What the product would change for your fab, from your own numbers and the measured rates above. Nothing is filled in for you."
              >
                <SavingsCalculator />
              </Section>
            </div>
          </section>

          <section
            id="guide"
            lang="en"
            dir="ltr"
            aria-labelledby="guide-title"
            className="mt-24 scroll-mt-[calc(var(--bar-height)+72px)] border-t border-hairline pt-16 sm:mt-28 sm:pt-20"
          >
            <GuideSection />
          </section>
        </div>
        <aside className="hidden lg:block">
          <SectionRail items={RAIL} />
        </aside>
      </div>
    </PageFrame>
  );
}

function Section({
  id,
  title,
  lede,
  children,
}: {
  id: HowAnchor;
  title: string;
  lede: string;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      aria-labelledby={`${id}-title`}
      className="scroll-mt-[calc(var(--bar-height)+72px)]"
    >
      <h2 id={`${id}-title`} className="text-title font-[650] text-ink">
        {title}
      </h2>
      <p className="mt-3 mb-8 max-w-[72ch] text-[16px] leading-[26px] text-ink-2 sm:text-[17px] sm:leading-7">
        {lede}
      </p>
      {children}
    </section>
  );
}
