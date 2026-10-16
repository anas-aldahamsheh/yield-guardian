import { ChevronDownIcon } from "lucide-react";
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
      <h3 className="text-[16px] leading-6 font-[630] tracking-[-0.01em] text-ink">{title}</h3>
      {description ? (
        <p className="mt-0.5 mb-4 max-w-[80ch] text-[13.5px] leading-5 text-ink-2">{description}</p>
      ) : (
        <div className="mb-4" />
      )}
      {children}
    </section>
  );
}

export function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[12.5px] leading-[18px] text-ink-3">{label}</dt>
      <dd className="mt-0.5 text-[15px] leading-6 font-[520] text-ink">{children}</dd>
    </div>
  );
}

/** How a result was computed, in the API's own words, folded away under the result. */
export function Method({ children }: { children: string }) {
  return (
    <details className="group/method mt-4 max-w-[90ch] text-[13px] leading-5 text-ink-2">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 rounded-full py-1 pr-2 pl-0 font-[560] text-ink transition-colors hover:text-signal [&::-webkit-details-marker]:hidden">
        How this is computed
        <ChevronDownIcon
          aria-hidden="true"
          className="size-3.5 text-ink-3 transition-[rotate] duration-(--dur-3) ease-spring group-open/method:rotate-180"
        />
      </summary>
      <p className="swap-in mt-1.5 rounded-[12px] bg-surface-2 px-3.5 py-2.5">{children}</p>
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
    <p className="unexposed rounded-[14px] px-4 py-4 text-[14px] leading-5 text-ink-2 shadow-[inset_0_0_0_1px_var(--hairline)]">
      {text.endsWith(".") ? text : `${text}.`}
    </p>
  );
}
