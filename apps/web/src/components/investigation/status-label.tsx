import type { Investigation } from "@yield-guardian/contracts";

import { INVESTIGATION_STATUS } from "@/lib/labels";
import { cn } from "@/lib/utils";

/** Investigation status as text, with a dot that repeats it. */
export function StatusLabel({ status }: { status: Investigation["status"] }) {
  const tone =
    status === "failed" || status === "rejected"
      ? "bg-fail"
      : status === "approved"
        ? "bg-pass"
        : status === "awaiting_decision"
          ? "bg-safelight"
          : "bg-mark-muted";
  return (
    <span className="inline-flex items-center gap-1.5 text-ink">
      <span
        aria-hidden="true"
        className={cn("size-2 rounded-full", status === "running" ? "live-dot" : tone)}
      />
      {INVESTIGATION_STATUS[status] ?? status}
    </span>
  );
}
