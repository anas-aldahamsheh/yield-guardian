import type { ReactNode } from "react";

import { GuideSection } from "@/components/guide/guide-view";
import {
  DataProvenance,
  MeasuredResults,
  ModelCardsPanel,
} from "@/components/methods/methods-view";
import { AiRoles } from "@/components/models/models-view";
import { PageFrame } from "@/components/page";
import type { HowAnchor } from "@/lib/routes";

import { Disclosure } from "./disclosure";
import { ExpertsNav } from "./experts-nav";
import { SecomMethods, WaferMethods } from "./method-tracks";
import { PlainArabic } from "./plain-arabic";
import { SavingsCalculator } from "./savings-calculator";

const EXPERT_SECTIONS: { id: HowAnchor; label: string }[] = [
  { id: "results", label: "Measured results" },
  { id: "models", label: "Models" },
  { id: "methods", label: "Methods" },
  { id: "data", label: "Data and licences" },
  { id: "calculator", label: "Savings calculator" },
  { id: "guide", label: "Guide (Arabic)" },
];

/**
 * How it works: plain Arabic first, then "For experts" in English, then the Arabic guide.
 * Every number on the page is read from the API, which reads the bundles.
 */
export function HowView() {
  return (
    <PageFrame className="pt-10">
      <PlainArabic />

      <section
        id="experts"
        lang="en"
        dir="ltr"
        className="mt-20 border-t border-hairline pt-16 sm:mt-28 sm:pt-20"
        aria-labelledby="experts-title"
      >
        <header className="max-w-[80ch]">
          <h2 id="experts-title" className="text-display font-[660] text-ink [font-stretch:112%]">
            For experts
          </h2>
          <p className="mt-4 max-w-[66ch] text-[17px] leading-7 text-ink-2">
            Every number below is read from the API, which reads the model bundles: none is typed
            into this page. Each result comes with its confidence interval and the data it was
            measured on. Findings are associations in historical data, not causes.
          </p>
        </header>
        <ExpertsNav sections={EXPERT_SECTIONS} />

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
            lede="The trained models, as their model cards describe them, and the language models that write and explain on AMD Token Factory, with their measured latency and points."
          >
            <Disclosure
              title="Model cards"
              summary="Written by each training pipeline with its bundle: data, method, results and limits."
            >
              <ModelCardsPanel />
            </Disclosure>
            <h3 className="mt-10 mb-4 text-[20px] leading-7 font-[640] tracking-[-0.015em] text-ink">
              AI roles on AMD
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
            lede="The datasets with their sources, licences and checksums, the bundles the API loaded, and the product's limitations."
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
        lang="ar"
        dir="rtl"
        aria-labelledby="guide-title"
        className="mt-24 border-t border-hairline pt-16 sm:mt-28 sm:pt-20"
      >
        <GuideSection />
      </section>
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
