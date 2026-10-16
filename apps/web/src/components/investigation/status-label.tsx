import type { Investigation } from "@yield-guardian/contracts";

import { INVESTIGATION_STATUS } from "@/lib/labels";
import { cn } from "@/lib/utils";

/**
 * Investigation status as a word on a chip, with a dot that repeats it: the signal while it runs
 * (pulsing) and while a report waits for a decision, pass when approved, fail when rejected or
 * failed, an open ring while queued.
 */
export function StatusLabel({
  status,
  className,
}: {
  status: Investigation["status"];
  className?: string;
}) {
  const tone =
    status === "failed" || status === "rejected"
      ? "fail"
      : status === "approved"
        ? "pass"
        : status === "awaiting_decision" || status === "running"
          ? "signal"
          : "quiet";
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-[12.5px] leading-4 font-[560] whitespace-nowrap text-ink",
        tone === "fail" && "bg-fail-wash",
        tone === "pass" && "bg-pass-wash",
        tone === "signal" && "bg-signal-wash",
        tone === "quiet" && "bg-surface-2 text-ink-2",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "size-1.5 shrink-0 rounded-full",
          status === "running"
            ? "live-dot"
            : tone === "fail"
              ? "bg-fail"
              : tone === "pass"
                ? "bg-pass"
                : tone === "signal"
                  ? "bg-signal"
                  : "shadow-[inset_0_0_0_1.5px_var(--ink-3)]",
        )}
      />
      {INVESTIGATION_STATUS[status] ?? status}
    </span>
  );
}
