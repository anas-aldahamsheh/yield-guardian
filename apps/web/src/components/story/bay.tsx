"use client";

import { useState, type CSSProperties, type ReactNode } from "react";

import { useChangeKey, useTicker } from "@/components/motion";
import { useEntrance } from "@/components/motion/entrance";
import { formatDuration, formatInt } from "@/lib/format";
import type { RunState, StageId } from "@/lib/live/run-state";
import { STATION_STAGES, type StationSummary, type StationTone } from "@/lib/live/stations";
import { cn } from "@/lib/utils";

import { useScene, type LineStation, type SceneStore } from "./scene";
import styles from "./story.module.css";
import { ChamberTool } from "./tools/chamber";
import { ConsoleTool } from "./tools/console";
import { ProberTool } from "./tools/prober";
import { StampTool } from "./tools/stamp";

/**
 * How long a station has been at work: waiting for its first stage to start, computing (the
 * server has not answered yet; measured on this page), or computed (the result is in and the
 * line is showing it; the server's own time).
 */
export type StationClock = { kind: "waiting" | "computing" | "computed"; ms: number } | null;

export type ClockStation = LineStation | "final_test";

/**
 * The bay: one machine body with four stations on one track. Each station is an instrument
 * screen (dark glass in both themes) that draws only computed values: the sensor bank (1), the
 * monitoring dials (2), the prober's wafer and the lot carrier (3) and the final-test seal. The
 * track's film light reaches a station when its first result is on screen, and only then.
 */
export function Bay({
  state,
  store,
  summaries,
  finalTest,
  clocks,
  onOpen,
  openStation,
}: {
  state: RunState | null;
  store: SceneStore;
  summaries: StationSummary[];
  finalTest: { tone: StationTone; sentence: string };
  clocks: Record<ClockStation, StationClock>;
  onOpen: (station: number) => void;
  openStation: number | null;
}) {
  const [manufacturing, monitoring, waferTest] = summaries as [
    StationSummary,
    StationSummary,
    StationSummary,
  ];
  const revealed = useScene(store, (s) => s.revealed);
  // Results arriving now (the line is playing them): they spring, tick and sweep. A run at rest
  // (restored, finished, or reduced motion) shows everything at once.
  const live = useScene(store, (s) => s.playing);
  const reached = (station: ClockStation, tone: StationTone) =>
    tone === "ok" ||
    tone === "alarm" ||
    tone === "failed" ||
    (station === "final_test"
      ? revealed.has("final_test")
      : STATION_STAGES[station].some((s) => revealed.has(s)));

  return (
    <section
      aria-labelledby="bay-title"
      className="relative min-w-0 rounded-[28px] bg-surface p-1.5 shadow-[inset_0_0_0_1px_var(--hairline),var(--highlight)] sm:p-2"
    >
      <h2 id="bay-title" className="sr-only">
        The line
      </h2>
      {/* Columns in proportion to the screens' drawings (214, 360, 360 and 200 wide, all 250
          high) plus each tile's fixed padding (64 px), so every instrument is drawn at one scale.
          Each tile spans three rows of the bay (heading, screen, what it computed) as a subgrid,
          so names, screens and sentences line up across the stations. */}
      <div className="grid grid-cols-[minmax(0,1fr)] md:grid-cols-2 xl:grid-cols-[calc((100%_-_256px)*0.189_+_64px)_calc((100%_-_256px)*0.31735_+_64px)_calc((100%_-_256px)*0.31735_+_64px)_calc((100%_-_256px)*0.1763_+_64px)]">
        <StationTile
          n={1}
          index={0}
          summary={manufacturing}
          clock={clocks.manufacturing}
          store={store}
          live={live}
          reached={reached("manufacturing", manufacturing.tone)}
          open={openStation === 1}
          onOpen={onOpen}
          stages={STATION_STAGES.manufacturing}
          tool={<ChamberTool state={state} store={store} />}
        />
        <StationTile
          n={2}
          index={1}
          summary={monitoring}
          clock={clocks.monitoring}
          store={store}
          live={live}
          reached={reached("monitoring", monitoring.tone)}
          open={openStation === 2}
          onOpen={onOpen}
          stages={STATION_STAGES.monitoring}
          tool={<ConsoleTool state={state} store={store} />}
        />
        <StationTile
          n={3}
          index={2}
          summary={waferTest}
          clock={clocks.wafer_test}
          store={store}
          live={live}
          reached={reached("wafer_test", waferTest.tone)}
          open={openStation === 3}
          onOpen={onOpen}
          stages={STATION_STAGES.wafer_test}
          tool={<ProberTool state={state} store={store} />}
        />
        <Tile
          index={3}
          tone={finalTest.tone}
          reached={reached("final_test", finalTest.tone)}
          live={live}
          stagesShown={revealed.has("final_test") ? 1 : 0}
          labelledBy="final-test"
          heading={
            <>
              <h3 id="final-test" className="text-[16px] leading-6 font-[630] tracking-[-0.01em]">
                Actual outcome
              </h3>
              <ToneChip tone={finalTest.tone} clock={clocks.final_test} live={live} />
            </>
          }
          tool={<StampTool state={state} store={store} />}
        >
          <Finding sentence={finalTest.sentence} />
        </Tile>
      </div>
    </section>
  );
}

/** The film's colour where each station's stretch of track begins and ends. */
const SEGMENT: [string, string][] = [
  ["var(--film-1)", "var(--film-2)"],
  ["var(--film-2)", "var(--film-4)"],
  ["var(--film-4)", "var(--film-5)"],
  ["var(--film-5)", "var(--film-6)"],
];

/**
 * A station's stretch of the track and its node. When data reaches the station its stretch
 * fills with the film (growing from the station before it while results arrive, at once when
 * the line is at rest). Along the top from two columns up, down the left edge in one column.
 */
function Track({
  index,
  reached,
  working,
  live,
}: {
  index: number;
  reached: boolean;
  working: boolean;
  live: boolean;
}) {
  const [from, to] = SEGMENT[index]!;
  const style = { "--seg-a": from, "--seg-b": to } as CSSProperties;
  return (
    <div aria-hidden="true" className="pointer-events-none absolute -inset-[3px]" style={style}>
      {/* The bare track */}
      <span className="absolute top-0 bottom-0 left-[27px] w-[2px] rounded-full bg-hairline-strong md:hidden" />
      <span className="absolute inset-x-0 top-[25px] hidden h-[2px] bg-hairline-strong md:block" />
      {/* The film where data has reached: the stretch lights up, slowly while results arrive and
          at once when the line is at rest. It fades rather than grows (a stretch scaled from
          nothing would take the stations drawn after it onto layers of their own while it ran),
          and it stops a hair short of the next station so that, lighting up, it never overlaps it. */}
      <span
        className={cn(
          "absolute top-0.5 bottom-0.5 left-[27px] w-[2px] rounded-full bg-[linear-gradient(180deg,var(--seg-a),var(--seg-b))] md:hidden",
          live && "transition-opacity duration-[900ms] ease-in-out",
          reached ? "opacity-100" : "opacity-0",
        )}
      />
      <span
        className={cn(
          "absolute inset-x-0.5 top-[25px] hidden h-[2px] bg-[linear-gradient(90deg,var(--seg-a),var(--seg-b))] md:block",
          live && "transition-opacity duration-[900ms] ease-in-out",
          reached ? "opacity-100" : "opacity-0",
        )}
      />
      {/* The node, on a layer of its own: it sits on the film, so while the film lights up it is
          drawn above it, and on its own layer it goes there alone instead of taking the rest of
          the station with it. */}
      <span
        className={cn(
          "absolute top-[23px] left-[21px] size-[14px] rounded-full transition-[background-color,box-shadow] duration-(--dur-4) will-change-transform md:top-[19px]",
          reached
            ? "bg-(--seg-a) shadow-[0_0_0_4px_color-mix(in_oklab,var(--seg-a)_22%,transparent)]"
            : "bg-surface shadow-[inset_0_0_0_2px_var(--hairline-strong)]",
        )}
      >
        {working ? <span className="absolute inset-[3px] rounded-full bg-signal" /> : null}
      </span>
    </div>
  );
}

/**
 * One station: its node on the track, its name and state, its instrument screen and what it
 * computed. A station whose alarm turns it red is tinted and rings once.
 */
function Tile({
  index,
  tone,
  reached,
  live,
  stagesShown,
  heading,
  tool,
  overlay,
  labelledBy,
  open = false,
  children,
}: {
  index: number;
  tone: StationTone;
  reached: boolean;
  live: boolean;
  /** How many of the station's results are on screen: each new one sweeps the screen once. */
  stagesShown: number;
  heading: ReactNode;
  tool: ReactNode;
  overlay?: ReactNode;
  labelledBy: string;
  open?: boolean;
  children: ReactNode;
}) {
  const sweep = useChangeKey(stagesShown);
  return (
    <div
      role="group"
      aria-labelledby={labelledBy}
      data-open={open || undefined}
      className={cn(
        "group/tile glow relative row-span-3 grid min-w-0 grid-rows-subgrid rounded-[22px] border-[3px] border-transparent bg-clip-padding pt-4 pr-4 pb-5 pl-14 transition-[background-color,box-shadow] duration-(--dur-4) sm:pr-5 md:pt-12 md:pl-5",
        // Column rules between stations, inset so they never touch the rounded corners.
        "before:pointer-events-none before:absolute before:top-12 before:bottom-6 before:left-0 before:hidden before:w-px before:bg-hairline md:[&:nth-child(2n)]:before:block xl:[&:nth-child(n+2)]:before:block",
        tone === "alarm" && "bg-[color-mix(in_oklab,var(--fail)_7%,transparent)] before:opacity-0",
        open && "before:opacity-0",
      )}
    >
      <Track index={index} reached={reached} working={tone === "working"} live={live} />
      <div className="flex min-h-7 flex-wrap items-center gap-x-2.5 gap-y-1 self-start">
        {heading}
      </div>
      <div
        data-theme="dark"
        className="screen glow relative mt-3 flex flex-col justify-center overflow-hidden p-2.5 transition-[box-shadow] duration-(--dur-4) ease-out [--glow-size:260px] [--glow:rgb(255_255_255/0.07)] group-hover/tile:shadow-[inset_0_0_0_1px_rgb(255_255_255/0.12),inset_0_1px_0_rgb(255_255_255/0.08),0_18px_32px_-22px_rgb(0_0_0/0.6)] sm:p-3"
      >
        <div>{tool}</div>
        {tone === "working" ? <WorkingSweep /> : null}
        {live && sweep != null && tone !== "working" ? <Sweep key={sweep} /> : null}
      </div>
      <div className="mt-4 flex min-w-0 flex-col gap-1.5">{children}</div>
      {/* Drawn last: while it rings, nothing of the station is drawn over it, so nothing has to
          leave the page's layer to stay above it. */}
      {overlay}
    </div>
  );
}

/**
 * Light crossing a station's screen once as it starts computing on this page; its clock then
 * counts the time. A station that was computing when the page arrived (a reload) is drawn at
 * rest. Nothing loops while a station waits on the server: the line moves for what arrives.
 */
function WorkingSweep() {
  const entrance = useEntrance();
  return entrance ? <Sweep /> : null;
}

/**
 * One sweep of light across a screen. It leaves once played: an overlay kept over the screen,
 * clipped to its rounded corners, would cost the compositor a pass on every later frame.
 */
function Sweep() {
  const [played, setPlayed] = useState(false);
  if (played) return null;
  return <span aria-hidden className="sweep" data-once="" onAnimationEnd={() => setPlayed(true)} />;
}

/**
 * A station ringing red once as its alarm arrives. Like the sweep, it leaves once played: an
 * overlay kept over the station would hold the stations drawn after it on layers of their own.
 */
function Pulse() {
  const [played, setPlayed] = useState(false);
  if (played) return null;
  return (
    <span aria-hidden="true" className={styles.pulse} onAnimationEnd={() => setPlayed(true)} />
  );
}

const TONE_TEXT: Record<StationTone, string> = {
  idle: "",
  needs: "Needs data",
  working: "Computing",
  ok: "Done",
  alarm: "Alarm",
  failed: "Stopped",
};

/** A station's state in a word, with its clock while it works. Springs in when it changes live. */
export function ToneChip({
  tone,
  clock,
  live = false,
}: {
  tone: StationTone;
  clock: StationClock;
  live?: boolean;
}) {
  const change = useChangeKey(tone);
  if (tone === "idle") return null;
  const kind = tone === "working" ? (clock?.kind ?? "computing") : null;
  const springs = change != null && (live || tone === "working");
  // It springs inside a clip of its own, with room for the overshoot: while a transform runs the
  // compositor cannot tell where it ends up, and unclipped it would lift the rest of the station
  // onto layers of their own until it settles.
  return (
    <span className="-m-1 inline-flex overflow-hidden p-1">
      <span
        key={springs ? `${tone}-${change}` : tone}
        className={cn(
          "inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-[12.5px] leading-4 font-[560] whitespace-nowrap",
          springs && "chip-in",
          tone === "needs" && "bg-surface-2 text-ink-2",
          // Its clock ticks ten times a second: on a layer of its own, a tick redraws the chip and
          // not the instruments around it.
          tone === "working" && "bg-signal-wash text-ink will-change-transform",
          tone === "ok" && "bg-pass-wash text-ink",
          (tone === "alarm" || tone === "failed") && "bg-fail-wash text-ink",
        )}
      >
        {tone === "working" ? (
          <span className="size-1.5 rounded-full bg-signal" aria-hidden="true" />
        ) : null}
        {tone === "ok" ? (
          <span className="size-1.5 rounded-full bg-pass" aria-hidden="true" />
        ) : null}
        {tone === "alarm" || tone === "failed" ? (
          <span className="size-1.5 rounded-full bg-fail" aria-hidden="true" />
        ) : null}
        {tone === "needs" ? (
          <span className="size-1.5 rounded-full border border-ink-3" aria-hidden="true" />
        ) : null}
        {kind === "computed" ? "Computed in" : kind === "waiting" ? "Waiting" : TONE_TEXT[tone]}
        {kind && kind !== "waiting" && clock ? (
          <span className="tnum text-ink-2">
            {kind === "computed" && clock.ms < 1 ? "under 1 ms" : formatDuration(clock.ms)}
          </span>
        ) : null}
      </span>
    </span>
  );
}

/**
 * A station's sentence cut to its first finding: the station shows one finding beside its number,
 * and its drawer has the rest. The whole sentence stays for screen readers (and is announced as
 * it settles).
 */
function Finding({ sentence }: { sentence: string }) {
  const first = sentence.split("; ")[0]!.split(/(?<=[.!?])\s+/)[0]!;
  const shown = /[.!?]$/.test(first) ? first : `${first}.`;
  const rest = sentence.slice(first.length).replace(/^[;.]?\s*/, "");
  return (
    <p className="text-[14px] leading-5 text-ink-2">
      {shown}
      {rest ? <span className="sr-only">{` ${upperFirst(rest)}`}</span> : null}
    </p>
  );
}

function upperFirst(s: string): string {
  return s ? s[0]!.toUpperCase() + s.slice(1) : s;
}

/** A station's count. It runs up from zero when its result arrives live; at rest it is simply there. */
function Count({ value, live, alarm }: { value: string; live: boolean; alarm: boolean }) {
  const n = /^[\d,]+$/.test(value) ? Number(value.replace(/,/g, "")) : null;
  const shown = useTicker(n ?? 0, { from: live && n != null ? 0 : undefined, duration: 1100 });
  return (
    <span
      className={cn(
        "readout text-[40px] leading-[44px] sm:text-[44px] sm:leading-[48px]",
        alarm ? "text-fail" : "text-ink",
      )}
    >
      {n == null ? value : formatInt(Math.round(shown))}
    </span>
  );
}

function StationTile({
  n,
  index,
  summary,
  clock,
  store,
  live,
  reached,
  tool,
  open,
  onOpen,
  stages,
}: {
  n: number;
  index: number;
  summary: StationSummary;
  clock: StationClock;
  store: SceneStore;
  live: boolean;
  reached: boolean;
  tool: ReactNode;
  open: boolean;
  onOpen: (station: number) => void;
  stages: readonly StageId[];
}) {
  const station = summary.station as LineStation;
  const pulse = useScene(store, (s) => s.pulses[station]);
  const shownCount = useScene(store, (s) => stages.filter((st) => s.revealed.has(st)).length);
  const id = `station-${n}`;
  const canOpen = summary.tone !== "idle" && summary.tone !== "needs";
  return (
    <Tile
      index={index}
      tone={summary.tone}
      reached={reached}
      live={live}
      stagesShown={shownCount}
      labelledBy={id}
      open={open}
      overlay={pulse > 0 ? <Pulse key={pulse} /> : null}
      heading={
        <>
          <h3 id={id} className="text-[16px] leading-6 font-[630] tracking-[-0.01em]">
            <span className="tnum text-ink-3">{n}</span> {summary.name}
          </h3>
          <ToneChip tone={summary.tone} clock={clock} live={live} />
        </>
      }
      tool={tool}
    >
      {summary.number ? (
        <p className="flex flex-wrap items-baseline gap-x-2.5">
          <Count value={summary.number.value} live={live} alarm={summary.tone === "alarm"} />
          <span className="text-[13px] leading-5 font-[520] text-ink-2">
            {summary.number.label}
          </span>
        </p>
      ) : null}
      <Finding sentence={summary.sentence} />
      {canOpen ? (
        // The whole tile opens the station's details (no separate Details button).
        <button
          type="button"
          onClick={() => onOpen(n)}
          aria-expanded={open}
          aria-controls="station-drawer"
          className="absolute inset-0 z-10 cursor-pointer rounded-[22px] focus-visible:outline-2 focus-visible:outline-offset-2"
        >
          <span className="sr-only">
            {open
              ? `Showing ${summary.name.toLowerCase()} `
              : `Open ${summary.name.toLowerCase()} details`}
          </span>
        </button>
      ) : null}
    </Tile>
  );
}
