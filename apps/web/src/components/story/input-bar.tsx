"use client";

import type { RunCreate } from "@yield-guardian/contracts";
import { CircleAlertIcon, FileUpIcon, InfoIcon, ListChecksIcon, PaintbrushIcon, XIcon } from "lucide-react";
import dynamic from "next/dynamic";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  type CSSProperties,
  type ComponentType,
  type ReactNode,
  useEffect,
  useId,
  useRef,
} from "react";

import { useEntrance } from "@/components/motion/entrance";
import { Indicator } from "@/components/motion/indicator";
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

const WAYS: {
  way: Way;
  label: string;
  hint: string;
  Icon: ComponentType<{ className?: string; strokeWidth?: number }>;
}[] = [
  {
    way: "case",
    label: "Pick a case",
    hint: "Real chamber (SECOM) and wafer (WM-811K) scenarios or custom items",
    Icon: ListChecksIcon,
  },
  {
    way: "draw",
    label: "Draw a defect",
    hint: "Paint failing dies on a real wafer layout (Tests Station 3)",
    Icon: PaintbrushIcon,
  },
  {
    way: "upload",
    label: "Upload fab data",
    hint: "Chamber sensor telemetry (Station 2) or optical wafer maps (Station 3)",
    Icon: FileUpIcon,
  },
];

function PanelLoading() {
  return <Placeholder className="h-48" label="Loading" />;
}

/** A note under or over the bar: it fades in when it appears while the person is here. */
function Note({
  role,
  className,
  children,
}: {
  role?: "alert";
  className: string;
  children: ReactNode;
}) {
  const entrance = useEntrance();
  return (
    <p role={role} className={cn(entrance && "swap-in", className)}>
      {children}
    </p>
  );
}

/**
 * The four ways in. A real sample runs at once; the other three open a panel under the bar to
 * choose, draw or upload the input first. Only one panel is open at a time. The bar and the
 * panel are two items of the hero's grid: the bar sits beside the introduction, the panel spans
 * the whole width under both.
 */
export function InputBar({
  open,
  onOpen,
  onStart,
  starting,
  error,
  waitingFor = null,
  kept = false,
  arrive = false,
}: {
  open: Way | null;
  onOpen: (way: Way | null) => void;
  onStart: StartRun;
  starting: boolean;
  error: string | null;
  /** A station a link asked for before there is a run: the bar is lit and says so. */
  waitingFor?: string | null;
  /** The open panel was open before a reload: it is back as it was, without fading in. */
  kept?: boolean;
  /** The page opened on the line alone: the bar rises in with the headline. */
  arrive?: boolean;
}) {
  const noteId = useId();
  const current = WAYS.find((w) => w.way === open) ?? null;
  return (
    <>
      <div
        className={cn(arrive && "rise-in", "min-w-0")}
        style={{ "--d": "380ms" } as CSSProperties}
      >
        {waitingFor ? (
          <Note className="lit mb-4 flex items-start gap-2.5 rounded-[14px] px-4 py-3 text-[14px] leading-5 text-ink">
            <span
              aria-hidden="true"
              className="mt-[7px] size-1.5 shrink-0 rounded-full bg-signal"
            />
            {`Choose an input to start a run; the ${waitingFor.toLowerCase()} details open with its results.`}
          </Note>
        ) : null}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:gap-5">
          {/* The button leans, lifts and turns its glyph inside a clip of its own, wide enough for
              its shadow: while a transform runs the compositor cannot tell where it ends up, and
              unclipped it would lift the whole line below onto layers of their own until it
              settled. */}
          <div className="grid shrink-0 [overflow:clip] [overflow-clip-margin:48px]">
            <button
              type="button"
              onClick={() => void onStart({ source: "sample", seed: null })}
              disabled={starting}
              aria-describedby={noteId}
              className="group press lift sheen-hover magnetic inline-flex h-14 shrink-0 cursor-pointer items-center justify-center gap-3 rounded-full bg-ink pr-7 pl-5 text-[16px] font-[600] tracking-[-0.005em] text-canvas shadow-[0_1px_2px_rgb(0_0_0/0.12),0_14px_30px_-14px_rgb(17_22_32/0.55),inset_0_1px_0_rgb(255_255_255/0.14)] disabled:opacity-70 disabled:cursor-not-allowed"
            >
              <SampleGlyph working={starting} />
              {starting ? "Starting live run..." : "Run Random Real Sample"}
            </button>
          </div>
          <div className="flex items-center gap-2.5">
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  aria-label="Benchmark stream information"
                  className="press inline-flex size-9 shrink-0 items-center justify-center rounded-full border border-hairline-strong bg-surface text-ink-3 shadow-2xs hover:bg-surface-2 hover:text-ink transition-colors cursor-pointer"
                >
                  <InfoIcon className="size-4" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="right" className="max-w-[340px] p-3 text-[12.5px] leading-relaxed font-sans text-ink bg-surface border border-hairline shadow-float">
                <p className="font-semibold text-ink mb-1">Dual-Stream Benchmark</p>
                Runs both fab data streams concurrently: 40 units of physical tool chamber telemetry (590 sensor channels) for Station 2, and 25 optical wafer defect inspection maps for Station 3.
              </TooltipContent>
            </Tooltip>
            <span className="text-[12.5px] text-ink-3 hidden sm:inline">
              SECOM (590 sensors) &bull; WM-811K (wafer maps)
            </span>
          </div>
        </div>
        <div className="mt-5 grid grid-cols-[minmax(0,1fr)] overflow-hidden rounded-[18px] bg-surface shadow-[inset_0_0_0_1px_var(--hairline-strong),var(--highlight)] sm:grid-cols-3">
          {WAYS.map(({ way, label, hint, Icon }, i) => {
            const isOpen = open === way;
            return (
              <button
                key={way}
                type="button"
                aria-expanded={isOpen}
                aria-controls={`way-${way}`}
                aria-labelledby={`${noteId}-${way}`}
                aria-describedby={`${noteId}-${way}-hint`}
                onClick={() => onOpen(isOpen ? null : way)}
                className={cn(
                  "group/way glow relative flex min-w-0 cursor-pointer items-start gap-3 px-4 py-3.5 text-left transition-colors duration-(--dur-1) outline-none hover:bg-surface-2 focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-offset-[-3px] focus-visible:outline-signal sm:flex-col sm:gap-2.5 sm:px-5 sm:py-4",
                  i > 0 &&
                    "shadow-[inset_0_1px_0_var(--hairline)] sm:shadow-[inset_1px_0_0_var(--hairline)]",
                )}
              >
                {isOpen ? (
                  <Indicator layoutId="way-open" className="lit absolute inset-1 rounded-[14px]" />
                ) : null}
                <span
                  aria-hidden="true"
                  className={cn(
                    "relative flex size-9 shrink-0 items-center justify-center rounded-[11px] bg-surface-2 text-ink-2 transition-[color,background-color,scale] duration-(--dur-3) ease-spring group-hover/way:scale-[1.06] group-hover/way:text-ink group-active/way:scale-95",
                    isOpen && "bg-surface text-signal",
                  )}
                >
                  <Icon className="size-[18px]" strokeWidth={1.75} />
                </span>
                <span className="relative min-w-0">
                  <span
                    id={`${noteId}-${way}`}
                    className="block text-[15px] leading-6 font-[600] text-ink"
                  >
                    {label}
                  </span>
                  <span
                    id={`${noteId}-${way}-hint`}
                    className="block text-[13px] leading-[18px] text-ink-2"
                  >
                    {hint}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
        {error ? (
          <Note
            role="alert"
            className="mt-4 flex max-w-[72ch] items-start gap-2.5 rounded-[14px] bg-fail-wash px-4 py-3 text-[14px] leading-5 text-ink shadow-[inset_0_0_0_1px_color-mix(in_oklab,var(--fail)_30%,transparent)]"
          >
            <CircleAlertIcon aria-hidden="true" className="mt-px size-4 shrink-0 text-fail" />
            {error}
          </Note>
        ) : null}
      </div>
      {current ? (
        <WayPanel
          key={current.way}
          id={`way-${current.way}`}
          label={current.label}
          hint={current.hint}
          onClose={() => onOpen(null)}
          kept={kept}
        >
          {current.way === "case" ? <CasePicker onStart={onStart} starting={starting} /> : null}
          {current.way === "draw" ? <DrawTool onStart={onStart} starting={starting} /> : null}
          {current.way === "upload" ? <UploadPanel onStart={onStart} starting={starting} /> : null}
        </WayPanel>
      ) : null}
    </>
  );
}

/** A wafer in the film's light: the mark of a real sample. Turns while a run is starting. */
function SampleGlyph({ working }: { working: boolean }) {
  const id = useId();
  return (
    <svg
      viewBox="0 0 20 20"
      aria-hidden="true"
      className={cn(
        "size-5 shrink-0 transition-transform duration-[900ms] ease-spring-soft group-hover:rotate-90",
        working && "animate-spin [animation-duration:1.6s]",
      )}
    >
      <defs>
        <linearGradient id={`${id}-film`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="var(--film-1)" />
          <stop offset="0.5" stopColor="var(--film-3)" />
          <stop offset="1" stopColor="var(--film-6)" />
        </linearGradient>
      </defs>
      <circle cx="10" cy="10" r="8.5" fill={`url(#${id}-film)`} />
      <path d="M8.6 1.62h2.8l-.55 1.5h-1.7Z" fill="var(--ink)" />
      <g fill="rgb(255 255 255 / 0.55)">
        <rect x="6.2" y="6.2" width="2.4" height="2.4" rx="0.5" />
        <rect x="11.4" y="6.2" width="2.4" height="2.4" rx="0.5" />
        <rect x="6.2" y="11.4" width="2.4" height="2.4" rx="0.5" />
        <rect x="11.4" y="11.4" width="2.4" height="2.4" rx="0.5" />
      </g>
    </svg>
  );
}

function WayPanel({
  id,
  label,
  hint,
  onClose,
  kept,
  children,
}: {
  id: string;
  label: string;
  hint: string;
  onClose: () => void;
  kept: boolean;
  children: ReactNode;
}) {
  // The panel opens under the hero, often below the fold: bring it into view, its start first
  // when it is taller than the screen, clear of the bar above and the Ask button below. Its tool
  // loads after it opens and makes it taller, so it is brought into view again as it grows, for
  // the first moments only. A panel kept open across a reload stays where the page puts it.
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (kept || !el || typeof ResizeObserver === "undefined") return;
    const until = performance.now() + 3000;
    let frame = 0;
    const bring = () => {
      frame = 0;
      const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      el.scrollIntoView({ block: "nearest", behavior: still ? "auto" : "smooth" });
    };
    const grown = new ResizeObserver(() => {
      if (performance.now() > until) grown.disconnect();
      else if (!frame) frame = requestAnimationFrame(bring);
    });
    grown.observe(el);
    return () => {
      grown.disconnect();
      if (frame) cancelAnimationFrame(frame);
    };
  }, [kept]);
  return (
    <section
      ref={ref}
      id={id}
      aria-label={label}
      className={cn(!kept && "grow-in", "panel col-span-full min-w-0 scroll-mb-24 p-5 sm:p-7")}
    >
      <div className="mb-5 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="text-[22px] leading-7 font-[640] tracking-[-0.018em] text-ink [font-stretch:106%]">
            {label}
          </h2>
          <p className="mt-0.5 text-[14px] leading-5 text-ink-2">{hint}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="press inline-flex h-9 shrink-0 cursor-pointer items-center gap-1.5 rounded-full pr-3.5 pl-3 text-[13.5px] font-[560] text-ink-2 shadow-[inset_0_0_0_1px_var(--hairline-strong)] hover:bg-surface-2 hover:text-ink"
        >
          <XIcon aria-hidden="true" className="size-4" strokeWidth={2} />
          Close
        </button>
      </div>
      {children}
    </section>
  );
}
