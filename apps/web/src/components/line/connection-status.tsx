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

const NO_STATE: Partial<Record<LineConnection, string>> = {
  reconnecting: "The live feed is not answering yet; it connects as soon as it can.",
  offline: "This device is offline.",
};

/** Whether the line on screen is current. Text first; the dot only repeats it. */
export function ConnectionStatus({
  connection,
  hasState = true,
  className,
}: {
  connection: LineConnection;
  /** False until a line state has been received, so the copy does not promise one. */
  hasState?: boolean;
  className?: string;
}) {
  const base = COPY[connection];
  const copy = !hasState && NO_STATE[connection] ? { ...base, detail: NO_STATE[connection]! } : base;
  return (
    <p role="status" className={cn("flex items-center gap-2 text-[13px] leading-5", className)} title={copy.detail}>
      <span
        aria-hidden="true"
        className={cn(
          "size-2 rounded-full",
          connection === "live" ? "live-dot" : connection === "offline" ? "bg-fail" : "bg-mark-muted",
        )}
      />
      <span className="font-medium text-ink">{copy.label}</span>
      <span className="hidden text-ink-3 sm:inline">{copy.detail}</span>
    </p>
  );
}
