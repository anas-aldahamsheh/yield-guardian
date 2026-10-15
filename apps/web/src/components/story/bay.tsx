"use client";

import type { CSSProperties, ReactNode } from "react";

import { formatDuration } from "@/lib/format";
import type { RunState } from "@/lib/live/run-state";
import type { StationSummary, StationTone } from "@/lib/live/stations";
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
 * The bay: the line in the yellow room, always dark because it depicts the room. Four tools on
 * one amber rail: the process chamber (1), the monitoring console (2), the prober with its lot
 * carrier (3) and the final-test stamp. Each station's result sits under its tool.
 */
export function Bay({
  state,
  store,
  summaries,
  finalTest,
  clocks,
  use3d,
  onOpen,
  openStation,
}: {
  state: RunState | null;
  store: SceneStore;
  summaries: StationSummary[];
  finalTest: { tone: StationTone; sentence: string };
  clocks: Record<ClockStation, StationClock>;
  use3d: boolean;
  onOpen: (station: number) => void;
  openStation: number | null;
}) {
  const [manufacturing, monitoring, waferTest] = summaries as [
    StationSummary,
    StationSummary,
    StationSummary,
  ];
  const lit = state != null;
  return (
    <section
      data-theme="dark"
      aria-labelledby="bay-title"
      className="bay relative min-w-0 overflow-hidden rounded-[2px] bg-room text-ink"
    >
      <h2 id="bay-title" className="sr-only">
        The line
      </h2>
      {/* Columns in proportion to the drawings' widths, so every tool is drawn at one scale and
          the captions start on one line. */}
      <div className="grid grid-cols-[minmax(0,1fr)] md:grid-cols-2 xl:grid-cols-[minmax(0,292fr)_minmax(0,392fr)_minmax(0,392fr)_minmax(0,272fr)]">
        <StationTile
          n={1}
          summary={manufacturing}
          lit={lit}
          clock={clocks.manufacturing}
          store={store}
          open={openStation === 1}
          onOpen={onOpen}
          toolWidth={TOOL_WIDTH.manufacturing}
          tool={
            <ChamberTool state={state} store={store} active={manufacturing.tone === "working"} />
          }
        />
        <StationTile
          n={2}
          summary={monitoring}
          lit={lit}
          clock={clocks.monitoring}
          store={store}
          open={openStation === 2}
          onOpen={onOpen}
          toolWidth={TOOL_WIDTH.monitoring}
          tool={<ConsoleTool state={state} store={store} active={monitoring.tone === "working"} />}
        />
        <StationTile
          n={3}
          summary={waferTest}
          lit={lit}
          clock={clocks.wafer_test}
          store={store}
          open={openStation === 3}
          onOpen={onOpen}
          toolWidth={TOOL_WIDTH.wafer_test}
          tool={
            <ProberTool
              state={state}
              store={store}
              active={waferTest.tone === "working"}
              use3d={use3d}
            />
          }
        />
        <Tile
          lit={lit}
          toolWidth={TOOL_WIDTH.final_test}
          tool={<StampTool state={state} store={store} active={finalTest.tone === "working"} />}
          labelledBy="final-test"
        >
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h3 id="final-test" className="text-[15px] leading-6 font-semibold">
              Final test
            </h3>
            <ToneChip tone={finalTest.tone} clock={clocks.final_test} />
          </div>
          <p className="text-[14px] leading-5 text-ink-2">{finalTest.sentence}</p>
        </Tile>
      </div>
    </section>
  );
}

/** Width of each tool's drawing in its own units (the viewBox, margins included). */
const TOOL_WIDTH: Record<ClockStation, number> = {
  manufacturing: 292,
  monitoring: 392,
  wafer_test: 392,
  final_test: 272,
};

/**
 * One tool on the line and its caption. From two columns up, the tile is a subgrid of two rows,
 * so the captions of tiles side by side start on one line; the drawings stand on the caption.
 */
function Tile({
  lit,
  tool,
  toolWidth,
  tone,
  overlay,
  labelledBy,
  children,
}: {
  lit: boolean;
  tool: ReactNode;
  toolWidth: number;
  tone?: StationTone;
  overlay?: ReactNode;
  labelledBy?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        "relative flex min-w-0 flex-col border-t border-hairline first:border-t-0 md:row-span-2 md:grid md:grid-rows-subgrid xl:border-t-0 md:[&:nth-child(-n+2)]:border-t-0",
        // Column rules drawn over the tile, so they take no width from the drawing.
        "before:pointer-events-none before:absolute before:inset-y-0 before:left-0 before:hidden before:w-px before:bg-hairline xl:[&:not(:first-child)]:before:block md:[&:nth-child(2n)]:before:block",
        tone === "alarm" && "bg-[color-mix(in_oklab,var(--fail)_7%,transparent)]",
      )}
      role={labelledBy ? "group" : undefined}
      aria-labelledby={labelledBy}
    >
      <Rail lit={lit} />
      {overlay}
      <div className="flex items-end justify-center pt-5">
        <div
          className="w-full max-w-(--tool-w) xl:max-w-none"
          style={{ "--tool-w": `${Math.round(toolWidth * 0.9)}px` } as CSSProperties}
        >
          {tool}
        </div>
      </div>
      <div className="flex min-w-0 flex-col gap-1 px-4 pt-3 pb-5">{children}</div>
    </div>
  );
}

function Rail({ lit }: { lit: boolean }) {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-[3px]">
      <div
        className={cn(
          "absolute inset-x-0 top-0 h-px bg-hairline-strong transition-opacity duration-[var(--dur-panel)]",
          lit && "opacity-0",
        )}
      />
      <div
        className={cn(
          "absolute inset-x-0 top-0 h-[2px] bg-safelight-lamp opacity-0 shadow-[0_0_10px_1px_color-mix(in_oklab,var(--safelight-lamp)_45%,transparent)] transition-opacity duration-[var(--dur-panel)]",
          lit && "opacity-100",
        )}
      />
    </div>
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

export function ToneChip({ tone, clock }: { tone: StationTone; clock: StationClock }) {
  if (tone === "idle") return null;
  const kind = tone === "working" ? (clock?.kind ?? "computing") : null;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[2px] px-1.5 text-[12px] leading-5",
        tone === "needs" && "bg-die-2 text-ink-3",
        tone === "working" && "bg-safelight-wash text-ink",
        tone === "ok" && "text-ink-2",
        tone === "alarm" && "bg-fail-wash text-ink",
        tone === "failed" && "bg-fail-wash text-ink",
      )}
    >
      {tone === "working" ? (
        <span className="size-1.5 rounded-full bg-safelight-lamp" aria-hidden="true" />
      ) : null}
      {tone === "alarm" ? (
        <span className="size-1.5 rounded-full bg-fail" aria-hidden="true" />
      ) : null}
      {kind === "computed" ? "Computed in" : kind === "waiting" ? "Waiting" : TONE_TEXT[tone]}
      {kind && kind !== "waiting" && clock ? (
        <span className="tnum text-ink-2">
          {kind === "computed" && clock.ms < 1 ? "under 1 ms" : formatDuration(clock.ms)}
        </span>
      ) : null}
    </span>
  );
}

function StationTile({
  n,
  summary,
  lit,
  clock,
  store,
  tool,
  toolWidth,
  open,
  onOpen,
}: {
  n: number;
  summary: StationSummary;
  lit: boolean;
  clock: StationClock;
  store: SceneStore;
  tool: ReactNode;
  toolWidth: number;
  open: boolean;
  onOpen: (station: number) => void;
}) {
  const station = summary.station as LineStation;
  const pulse = useScene(store, (s) => s.pulses[station]);
  const id = `station-${n}`;
  const canOpen = summary.tone !== "idle" && summary.tone !== "needs";
  return (
    <Tile
      lit={lit}
      tool={tool}
      toolWidth={toolWidth}
      tone={summary.tone}
      labelledBy={id}
      overlay={pulse > 0 ? <span key={pulse} aria-hidden="true" className={styles.pulse} /> : null}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <h3 id={id} className="text-[15px] leading-6 font-semibold">
          <span className="tnum text-ink-3">{n}</span> {summary.name}
        </h3>
        <ToneChip tone={summary.tone} clock={clock} />
      </div>
      <p className="text-[14px] leading-5 text-ink-2">{summary.sentence}</p>
      {summary.number ? (
        <p className="mt-1 flex items-baseline gap-2">
          <span
            className={cn(
              "readout text-[30px] leading-9",
              summary.tone === "alarm" ? "text-fail" : "text-ink",
            )}
          >
            {summary.number.value}
          </span>
          <span className="text-[13px] leading-5 text-ink-3">{summary.number.label}</span>
        </p>
      ) : null}
      {canOpen ? (
        <button
          type="button"
          onClick={() => onOpen(n)}
          aria-expanded={open}
          aria-controls="station-drawer"
          className={cn(
            "mt-2 self-start rounded-[4px] border border-hairline-strong px-2.5 py-1 text-[13px] leading-5 text-ink hover:bg-accent",
            open && "lit",
          )}
        >
          {open
            ? `Showing ${summary.name.toLowerCase()} details`
            : `Open ${summary.name.toLowerCase()} details`}
        </button>
      ) : null}
    </Tile>
  );
}
