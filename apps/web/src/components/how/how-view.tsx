import type { ReactNode } from "react";

import { GuideSection } from "@/components/guide/guide-view";
import {
  DataProvenance,
  MeasuredResults,
  ModelCardsPanel,
} from "@/components/methods/methods-view";
import { SecomMethods } from "@/components/methods/secom-methods";
import { WaferMethods } from "@/components/methods/wafer-methods";
import { AiRoles } from "@/components/models/models-view";
import { PageFrame } from "@/components/page";
import type { HowAnchor } from "@/lib/routes";

import { Disclosure } from "./disclosure";
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
        className="mt-4 border-t-2 border-ink pt-10"
        aria-labelledby="experts-title"
      >
        <header className="mb-8 max-w-[80ch]">
          <h2
            id="experts-title"
            className="text-[26px] leading-8 font-semibold tracking-[-0.02em] text-ink sm:text-title"
          >
            For experts
          </h2>
          <p className="mt-2 text-[15px] leading-6 text-ink-2">
            Every number below is read from the API, which reads the model bundles: none is typed
            into this page. Each result comes with its confidence interval and the data it was
            measured on. Findings are associations in historical data, not causes.
          </p>
          <nav
            aria-label="For experts"
            className="mt-4 flex flex-wrap gap-x-5 gap-y-2 border-y border-hairline py-2.5 text-[14px]"
          >
            {EXPERT_SECTIONS.map((s) => (
              <a
                key={s.id}
                href={`#${s.id}`}
                className="text-ink-2 underline decoration-hairline-strong underline-offset-4 hover:text-ink"
              >
                {s.label}
              </a>
            ))}
          </nav>
        </header>

        <div className="grid grid-cols-[minmax(0,1fr)] gap-14">
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
            <h3 className="mt-8 mb-3 text-[18px] leading-6 font-semibold text-ink">
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
        className="mt-16 border-t-2 border-ink pt-10"
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
    <section id={id} aria-labelledby={`${id}-title`}>
      <h2
        id={`${id}-title`}
        className="text-[22px] leading-8 font-semibold tracking-[-0.01em] text-ink"
      >
        {title}
      </h2>
      <p className="mt-1 mb-4 max-w-[80ch] text-[15px] leading-6 text-ink-2">{lede}</p>
      {children}
    </section>
  );
}
