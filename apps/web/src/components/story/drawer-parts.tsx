import type { ReactNode } from "react";

import type { StageView } from "@/lib/live/run-state";
import { needsText } from "@/lib/live/stations";

/** A titled part of a station's drawer. */
export function DrawerSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="min-w-0">
      <h3 className="text-[16px] leading-6 font-semibold text-ink">{title}</h3>
      {description ? (
        <p className="mb-3 max-w-[80ch] text-[13px] leading-5 text-ink-3">{description}</p>
      ) : (
        <div className="mb-3" />
      )}
      {children}
    </section>
  );
}

export function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[12px] leading-4 text-ink-3">{label}</dt>
      <dd className="text-[14px] leading-5 text-ink">{children}</dd>
    </div>
  );
}

/** How a result was computed, in the API's own words, folded away under the result. */
export function Method({ children }: { children: string }) {
  return (
    <details className="mt-3 max-w-[90ch] text-[12px] leading-5 text-ink-3">
      <summary className="cursor-pointer text-ink-2">How this is computed</summary>
      <p className="mt-1">{children}</p>
    </details>
  );
}

/**
 * A detail of a stored result that is still on its way to the page (a reload first shows what
 * was on screen; the rest of the run is read just after and shows here on its own).
 */
export function StillReading({ what }: { what: string }) {
  return <p className="text-[14px] leading-5 text-ink-3">{`Reading ${what}.`}</p>;
}

/** A stage whose result is not on the line yet: what it needs, why it stopped, or that it is coming. */
export function NotYet({ stage, what }: { stage: StageView; what: string }) {
  const text =
    stage.status === "skipped"
      ? needsText(what, stage.needs, "needs more input")
      : stage.status === "failed"
        ? `${what} stopped: ${stage.problem?.detail ?? stage.problem?.title ?? "the stage failed"}`
        : `${what} will show here when the line reaches it.`;
  return (
    <p className="text-[14px] leading-5 text-ink-3">{text.endsWith(".") ? text : `${text}.`}</p>
  );
}
