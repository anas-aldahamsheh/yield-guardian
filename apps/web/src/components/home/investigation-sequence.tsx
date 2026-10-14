"use client";

import { useQuery } from "@tanstack/react-query";

import { useApi } from "@/lib/api/context";
import { q } from "@/lib/api/queries";

const STEPS = [
  {
    title: "An alarm, or a question",
    text: "Written rules raise alarms: failure risk above the operating threshold, Hotelling T² or SPE beyond their control limits, EWMA and CUSUM drifts. An engineer can also start from any unit, wafer or lot.",
    role: null,
  },
  {
    title: "Evidence",
    text: "The investigator calls data tools: the unit record, its SHAP explanation, the sensors that move T², correlated sensor groups, the literature. Each result is stored as numbered evidence.",
    role: "investigator",
  },
  {
    title: "Report",
    text: "A writer model drafts the report from that evidence only. Every finding cites evidence, and every number it uses is listed with the evidence it came from.",
    role: "writer",
  },
  {
    title: "Checks",
    text: "Code compares each number with the evidence, a verifier model checks each claim, and causal wording is rejected. The writer gets two chances to fix problems; anything left is flagged on the report.",
    role: "verifier",
  },
  {
    title: "Decision",
    text: "An engineer approves the actions, which opens a work order, or rejects the report. Only an outcome an engineer confirms may later be described as a cause.",
    role: null,
  },
] as const;

/** How an investigation runs. A real sequence, so the steps are numbered. */
export function InvestigationSequence() {
  const api = useApi();
  const roles = useQuery(q.llmRoles(api));
  const modelFor = (role: string) => roles.data?.find((r) => r.role === role)?.model_id;

  return (
    <section aria-labelledby="sequence-title" className="border-y border-hairline bg-die">
      <div className="mx-auto max-w-[1600px] px-gutter py-16">
        <h2 id="sequence-title" className="text-h2 font-semibold tracking-[-0.01em]">
          How an investigation runs
        </h2>
        <p className="mt-3 max-w-[64ch] text-[15px] leading-6 text-ink-2">
          Language models on AMD Token Factory plan, write and check. They never compute a
          statistic: the numbers come from the plant data and the trained models.
        </p>
        <ol className="mt-10 grid grid-cols-[minmax(0,1fr)] gap-x-8 gap-y-10 md:grid-cols-2 xl:grid-cols-5">
          {STEPS.map((step, i) => {
            const model = step.role ? modelFor(step.role) : undefined;
            return (
              <li key={step.title} className="relative min-w-0 border-t border-hairline-strong pt-4">
                <span className="tnum text-[13px] leading-5 text-ink-3">Step {i + 1}</span>
                <h3 className="mt-1 text-h4 font-semibold">{step.title}</h3>
                <p className="mt-2 text-[15px] leading-6 text-ink-2">{step.text}</p>
                {step.role ? (
                  <p className="mt-3 text-[13px] leading-5 text-ink-3">
                    Model: <span className="text-ink-2">{model ?? (roles.isError ? "unavailable" : "…")}</span>
                  </p>
                ) : null}
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}
