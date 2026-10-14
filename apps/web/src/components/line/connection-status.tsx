import type { LineConnection } from "@/lib/line/use-live-line";
import { cn } from "@/lib/utils";

const COPY: Record<LineConnection, { label: string; detail: string }> = {
  connecting: { label: "Connecting", detail: "Opening the live feed." },
  live: { label: "Live", detail: "New units appear as they leave the line." },
  reconnecting: {
    label: "Reconnecting",
    detail: "The live feed dropped. Showing the last state received; it catches up on reconnect.",
  },
  offline: {
    label: "Offline",
    detail: "This device is offline. Showing the last state received.",
  },
};

/** Whether the line on screen is current. Text first; the dot only repeats it. */
export function ConnectionStatus({ connection, className }: { connection: LineConnection; className?: string }) {
  const copy = COPY[connection];
  return (
    <p role="status" className={cn("flex items-center gap-2 text-[13px] leading-5", className)} title={copy.detail}>
      <span
        aria-hidden="true"
        className={cn(
          "size-2 rounded-full",
          connection === "live" ? "bg-safelight" : connection === "offline" ? "bg-fail" : "bg-mark-muted",
        )}
      />
      <span className="font-medium text-ink">{copy.label}</span>
      <span className="hidden text-ink-3 sm:inline">{copy.detail}</span>
    </p>
  );
}
