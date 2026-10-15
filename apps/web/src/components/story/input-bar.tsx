"use client";

import type { RunCreate } from "@yield-guardian/contracts";
import dynamic from "next/dynamic";
import type { ReactNode } from "react";

import { Placeholder } from "@/components/states";
import { cn } from "@/lib/utils";

/** The three ways in that open a panel; each panel's code loads when it first opens. */
const CasePicker = dynamic(() => import("./case-picker").then((m) => m.CasePicker), {
  loading: () => <PanelLoading />,
});
const DrawTool = dynamic(() => import("./draw-tool").then((m) => m.DrawTool), {
  loading: () => <PanelLoading />,
});
const UploadPanel = dynamic(() => import("./upload-panel").then((m) => m.UploadPanel), {
  loading: () => <PanelLoading />,
});

export type Way = "case" | "draw" | "upload";

export type StartRun = (body: RunCreate) => Promise<void>;

const WAYS: { way: Way; label: string }[] = [
  { way: "case", label: "Pick a case" },
  { way: "draw", label: "Draw a defect" },
  { way: "upload", label: "Upload a file" },
];

function PanelLoading() {
  return <Placeholder className="h-48" label="Loading" />;
}

/**
 * The four ways in. A real sample runs at once; the other three open a panel under the bar to
 * choose, draw or upload the input first. Only one panel is open at a time.
 */
export function InputBar({
  open,
  onOpen,
  onStart,
  starting,
  error,
  waitingFor = null,
}: {
  open: Way | null;
  onOpen: (way: Way | null) => void;
  onStart: StartRun;
  starting: boolean;
  error: string | null;
  /** A station a link asked for before there is a run: the bar is lit and says so. */
  waitingFor?: string | null;
}) {
  return (
    <div className={cn(waitingFor && "lit -mx-3 rounded-[4px] px-3 py-3")}>
      {waitingFor ? (
        <p className="mb-3 text-[14px] leading-5 text-ink">
          {`Choose an input to start a run; the ${waitingFor.toLowerCase()} details open with its results.`}
        </p>
      ) : null}
      <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-center sm:gap-2.5">
        <button
          type="button"
          onClick={() => void onStart({ source: "sample", seed: null })}
          disabled={starting}
          className="col-span-2 inline-flex h-11 items-center justify-center gap-2.5 rounded-[4px] bg-ink px-5 text-[15px] font-semibold text-room transition-[background-color,transform] duration-[var(--dur-micro)] hover:bg-ink/90 active:translate-y-px disabled:opacity-60 sm:col-span-1"
        >
          <span aria-hidden="true" className="size-2 rounded-full bg-safelight-lamp" />
          {starting ? "Starting the run" : "Try a real sample"}
        </button>
        {WAYS.map(({ way, label }) => (
          <button
            key={way}
            type="button"
            aria-expanded={open === way}
            aria-controls={`way-${way}`}
            onClick={() => onOpen(open === way ? null : way)}
            className={cn(
              "inline-flex h-11 items-center justify-center rounded-[4px] border border-hairline-strong px-4 text-[15px] text-ink transition-colors duration-[var(--dur-micro)] last:col-span-2 hover:bg-die-2 sm:last:col-span-1",
              open === way && "lit border-transparent",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      <p className="mt-2.5 text-[13px] leading-5 text-ink-3">
        A real sample is a run of consecutive SECOM units and one WM-811K lot, picked at random. The
        rule and its seed are shown with the run, so the same sample can be run again.
      </p>
      {error ? (
        <p
          role="alert"
          className="mt-3 max-w-[72ch] rounded-[2px] bg-fail-wash px-3 py-2 text-[14px] leading-5 text-ink"
        >
          {error}
        </p>
      ) : null}
      {open ? (
        <WayPanel
          id={`way-${open}`}
          label={WAYS.find((w) => w.way === open)!.label}
          onClose={() => onOpen(null)}
        >
          {open === "case" ? <CasePicker onStart={onStart} starting={starting} /> : null}
          {open === "draw" ? <DrawTool onStart={onStart} starting={starting} /> : null}
          {open === "upload" ? <UploadPanel onStart={onStart} starting={starting} /> : null}
        </WayPanel>
      ) : null}
    </div>
  );
}

function WayPanel({
  id,
  label,
  onClose,
  children,
}: {
  id: string;
  label: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      aria-label={label}
      className="swap-in mt-4 rounded-[2px] border border-hairline bg-die p-4 sm:p-5"
    >
      <div className="mb-3 flex items-start justify-between gap-4">
        <h2 className="text-[17px] leading-6 font-semibold text-ink">{label}</h2>
        <button
          type="button"
          onClick={onClose}
          className="rounded-[4px] px-2 py-0.5 text-[13px] leading-5 text-ink-2 hover:bg-die-2 hover:text-ink"
        >
          Close
        </button>
      </div>
      {children}
    </section>
  );
}
