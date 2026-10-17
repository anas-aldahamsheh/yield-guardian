"use client";

import {
  ActivityIcon,
  ArrowLeftIcon,
  ArrowRightIcon,
  CpuIcon,
  LayersIcon,
  ShieldCheckIcon,
} from "lucide-react";
import { useState, type CSSProperties, type ReactNode } from "react";

import { useChangeKey, useTicker } from "@/components/motion";
import { useEntrance } from "@/components/motion/entrance";
import { formatDuration, formatInt, formatPercent } from "@/lib/format";
import { stageResult, type RunState, type StageId } from "@/lib/live/run-state";
import { STATION_STAGES, type StationSummary, type StationTone } from "@/lib/live/stations";
import type { Focus } from "@/lib/live/url-state";
import { cn } from "@/lib/utils";

import { DrawerSection, NotYet } from "./drawer-parts";
import { UnitsDrawer } from "./drawer-units";
import { WafersDrawer } from "./drawer-wafers";
import { useScene, type LineStation, type SceneStore } from "./scene";
import { IntakeDrawer } from "./station-drawer";
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

const STATION_TABS = [
  { n: 1, label: "Manufacturing" },
  { n: 2, label: "Monitoring" },
  { n: 3, label: "Wafer test" },
  { n: 4, label: "Actual outcome" },
] as const;

/**
 * The bay: one machine body with four stations on one track. Each station is an instrument
 * screen (dark glass in both themes) that draws only computed values: the sensor bank (1), the
 * monitoring dials (2), the prober's wafer and the lot carrier (3) and the final-test seal.
 * Clicking a station opens Focused Inspection Mode, keeping the clicked station on the left
 * with its diagnostics, and displaying rich telemetry and investigations on the right.
 */
export function Bay({
  state,
  store,
  summaries,
  finalTest,
  clocks,
  onOpen,
  openStation,
  focus = null,
  onFocus,
  revealed: propRevealed,
}: {
  state: RunState | null;
  store: SceneStore;
  summaries: StationSummary[];
  finalTest: { tone: StationTone; sentence: string };
  clocks: Record<ClockStation, StationClock>;
  onOpen: (station: number | null) => void;
  openStation: number | null;
  focus?: Focus;
  onFocus?: (focus: Focus) => void;
  revealed?: ReadonlySet<StageId>;
}) {
  const [manufacturing, monitoring, waferTest] = summaries as [
    StationSummary,
    StationSummary,
    StationSummary,
  ];
  const sceneRevealed = useScene(store, (s) => s.revealed);
  const revealed = propRevealed ?? sceneRevealed;
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

  // If a station is selected, render the Focused Station Inspection view
  if (openStation != null) {
    const selectedClock =
      openStation === 1
        ? clocks.manufacturing
        : openStation === 2
          ? clocks.monitoring
          : openStation === 3
            ? clocks.wafer_test
            : clocks.final_test;

    const selectedSummary =
      openStation === 1
        ? manufacturing
        : openStation === 2
          ? monitoring
          : openStation === 3
            ? waferTest
            : undefined;

    const selectedTool =
      openStation === 1 ? (
        <ChamberTool state={state} store={store} />
      ) : openStation === 2 ? (
        <ConsoleTool state={state} store={store} />
      ) : openStation === 3 ? (
        <ProberTool state={state} store={store} />
      ) : (
        <StampTool state={state} store={store} />
      );

    const selectedSentence =
      openStation === 4 ? finalTest.sentence : (selectedSummary?.sentence ?? "");

    const selectedTone: StationTone =
      openStation === 4 ? finalTest.tone : (selectedSummary?.tone ?? "idle");

    return (
      <section
        aria-labelledby="bay-focused-title"
        className="relative min-w-0 rounded-[28px] bg-surface p-4 shadow-[inset_0_0_0_1px_var(--hairline),var(--highlight)] sm:p-6"
      >
        <h2 id="bay-focused-title" className="sr-only">
          Station {openStation} Inspection
        </h2>

        {/* Top Navigation & Station Switcher Bar */}
        <header className="mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-hairline pb-4">
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => onOpen(null)}
              className="press group inline-flex cursor-pointer items-center gap-2 rounded-full bg-surface-2 px-4 py-2 text-[13px] font-[600] text-ink shadow-[inset_0_0_0_1px_var(--hairline-strong)] hover:bg-surface-3 transition-all"
            >
              <ArrowLeftIcon className="size-4 transition-transform group-hover:-translate-x-1" />
              <span>Back to full pipeline</span>
            </button>
            <span className="hidden text-[12.5px] font-medium text-ink-3 sm:inline">
              Station {openStation} of 4 &bull; Deep-Dive Inspection
            </span>
          </div>

          {/* Quick Station Switcher Tabs */}
          <div className="flex flex-wrap items-center gap-1 rounded-full bg-surface-2 p-1 shadow-[inset_0_0_0_1px_var(--hairline)]">
            {STATION_TABS.map((tab) => {
              const active = openStation === tab.n;
              return (
                <button
                  key={tab.n}
                  type="button"
                  onClick={() => onOpen(tab.n)}
                  className={cn(
                    "inline-flex cursor-pointer items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] font-[580] transition-all",
                    active
                      ? "bg-surface text-ink shadow-sm ring-1 ring-hairline"
                      : "text-ink-3 hover:text-ink hover:bg-surface/50",
                  )}
                >
                  <span
                    className={cn(
                      "flex size-4 items-center justify-center rounded-full text-[10px] font-bold",
                      active ? "bg-signal text-white" : "bg-surface-3 text-ink-2",
                    )}
                  >
                    {tab.n}
                  </span>
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>
        </header>

        {/* Focused 2-Column Layout */}
        <div className="grid grid-cols-1 items-start gap-8 lg:grid-cols-[380px_minmax(0,1fr)]">
          {/* LEFT COLUMN: Clicked box alone on the left with diagnostics under it */}
          <div className="flex w-full shrink-0 flex-col gap-5 lg:sticky lg:top-4">
            <FocusedStationCard
              stationNumber={openStation}
              summary={selectedSummary}
              clock={selectedClock}
              tool={selectedTool}
              readout={openStation === 4 ? null : selectedSummary?.number}
              findingSentence={selectedSentence}
              tone={selectedTone}
            />

            <StationQuickDiagnostics
              stationNumber={openStation}
              clock={selectedClock}
              state={state}
              finalTest={finalTest}
              revealed={revealed}
            />
          </div>

          {/* RIGHT COLUMN: Station Deep Dive details */}
          <div className="flex w-full min-w-0 flex-col gap-6">
            {openStation === 1 && state && (
              <div className="rounded-[24px] bg-surface-2/40 p-6 shadow-[inset_0_0_0_1px_var(--hairline)]">
                <IntakeDrawer state={state} shown={revealed.has("intake")} />
              </div>
            )}
            {openStation === 2 && state && (
              <div className="rounded-[24px] bg-surface-2/40 p-6 shadow-[inset_0_0_0_1px_var(--hairline)]">
                {state.stages.sensor_risk.status === "skipped" &&
                state.stages.control_charts.status === "skipped" ? (
                  <NotYet stage={state.stages.sensor_risk} what="Monitoring" />
                ) : (
                  <UnitsDrawer
                    state={state}
                    shown={(st) => revealed.has(st)}
                    unit={focus?.kind === "unit" ? focus.index : null}
                    onUnit={(index) => onFocus?.({ kind: "unit", index })}
                  />
                )}
              </div>
            )}
            {openStation === 3 && state && (
              <div className="rounded-[24px] bg-surface-2/40 p-6 shadow-[inset_0_0_0_1px_var(--hairline)]">
                <WafersDrawer
                  state={state}
                  shown={(st) => revealed.has(st)}
                  wafer={focus?.kind === "wafer" ? focus.index : null}
                  onWafer={(index) => onFocus?.({ kind: "wafer", index })}
                />
              </div>
            )}
            {openStation === 4 && state && (
              <div className="rounded-[24px] bg-surface-2/40 p-6 shadow-[inset_0_0_0_1px_var(--hairline)]">
                <OutcomeDrawer state={state} finalTest={finalTest} revealed={revealed} />
              </div>
            )}
            {!state && (
              <div className="rounded-[24px] bg-surface-2/40 p-8 text-center text-ink-2 shadow-[inset_0_0_0_1px_var(--hairline)]">
                <p className="text-[14.5px] font-medium">Waiting for run telemetry to load...</p>
              </div>
            )}
          </div>
        </div>
      </section>
    );
  }

  // Full 4-station pipeline overview
  return (
    <section
      aria-labelledby="bay-title"
      className="relative min-w-0 rounded-[28px] bg-surface p-1.5 shadow-[inset_0_0_0_1px_var(--hairline),var(--highlight)] sm:p-2"
    >
      <div className="flex items-center justify-between px-3 pt-1.5 pb-2">
        <h2 id="bay-title" className="text-[13px] font-[600] tracking-[-0.01em] text-ink-2">
          Production line
        </h2>
        <span className="inline-flex items-center gap-1.5 text-[12px] font-medium text-ink-3">
          <span className="size-1.5 rounded-full bg-signal" />
          Click any station to inspect details
        </span>
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)] md:grid-cols-2 xl:grid-cols-[calc((100%_-_256px)*0.189_+_64px)_calc((100%_-_256px)*0.31735_+_64px)_calc((100%_-_256px)*0.31735_+_64px)_calc((100%_-_256px)*0.1763_+_64px)]">
        <StationTile
          n={1}
          index={0}
          summary={manufacturing}
          clock={clocks.manufacturing}
          store={store}
          live={live}
          reached={reached("manufacturing", manufacturing.tone)}
          open={false}
          onOpen={() => onOpen(1)}
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
          open={false}
          onOpen={() => onOpen(2)}
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
          open={false}
          onOpen={() => onOpen(3)}
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
          open={false}
          onClick={() => onOpen(4)}
          canOpen={true}
          heading={
            <>
              <h3
                id="final-test"
                className="inline-flex items-center text-[16px] leading-6 font-[630] tracking-[-0.01em]"
              >
                <span className="mr-2 inline-flex size-5 items-center justify-center rounded-full bg-surface-2 text-[11px] font-bold text-ink-2 shadow-[inset_0_0_0_1px_var(--hairline)]">
                  4
                </span>
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

/**
 * Standalone card rendering the active station alone on the left in Focused Mode.
 */
function FocusedStationCard({
  stationNumber,
  summary,
  clock,
  tool,
  readout,
  findingSentence,
  tone,
}: {
  stationNumber: number;
  summary?: StationSummary;
  clock: StationClock;
  tool: ReactNode;
  readout?: { value: string; label: string } | null;
  findingSentence: string;
  tone: StationTone;
}) {
  const name = stationNumber === 4 ? "Actual outcome" : (summary?.name ?? "");

  return (
    <div
      className={cn(
        "relative rounded-[24px] border-2 border-signal/40 bg-surface p-5 shadow-[0_12px_28px_-10px_rgb(0_0_0/0.1),inset_0_1px_0_var(--highlight)] dark:shadow-[0_16px_36px_-12px_rgb(0_0_0/0.5)]",
        tone === "alarm" && "border-fail/50 bg-[color-mix(in_oklab,var(--fail)_5%,transparent)]",
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <h3 className="inline-flex items-center text-[17px] font-[640] tracking-[-0.01em] text-ink">
          <span className="mr-2 inline-flex size-6 items-center justify-center rounded-full bg-signal text-[12px] font-bold text-white shadow-xs">
            {stationNumber}
          </span>
          {name}
        </h3>
        <ToneChip tone={tone} clock={clock} live={false} />
      </div>

      {/* Screen Tool */}
      <div
        data-theme="dark"
        className="screen glow relative mt-4 flex flex-col justify-center overflow-hidden rounded-[18px] p-3 shadow-md [--glow-size:260px] [--glow:rgb(255_255_255/0.07)]"
      >
        <div>{tool}</div>
      </div>

      {/* Readout and finding */}
      <div className="mt-4 flex flex-col gap-1.5">
        {readout ? (
          <p className="flex flex-wrap items-baseline gap-x-2.5">
            <Count value={readout.value} live={false} alarm={tone === "alarm"} />
            <span className="text-[13px] font-[520] text-ink-2">{readout.label}</span>
          </p>
        ) : null}
        <Finding sentence={findingSentence} />
      </div>
    </div>
  );
}

/**
 * Diagnostics and quick telemetry panel placed directly under the focused station card on the left.
 */
function StationQuickDiagnostics({
  stationNumber,
  clock,
  state,
  finalTest,
  revealed,
}: {
  stationNumber: number;
  summary?: StationSummary;
  clock: StationClock;
  state: RunState | null;
  finalTest: { tone: StationTone; sentence: string };
  revealed: ReadonlySet<StageId>;
}) {
  const intake = state && revealed?.has("intake") ? stageResult(state, "intake") : null;
  const final = state && revealed?.has("final_test") ? stageResult(state, "final_test") : null;

  return (
    <div className="flex flex-col gap-4 rounded-[22px] bg-surface-2/80 p-5 shadow-[inset_0_0_0_1px_var(--hairline)]">
      <div className="flex items-center justify-between border-b border-hairline/70 pb-3">
        <div className="flex items-center gap-2">
          {stationNumber === 1 && <CpuIcon className="size-4 text-signal" />}
          {stationNumber === 2 && <ActivityIcon className="size-4 text-signal" />}
          {stationNumber === 3 && <LayersIcon className="size-4 text-signal" />}
          {stationNumber === 4 && <ShieldCheckIcon className="size-4 text-signal" />}
          <span className="text-[13px] font-[620] text-ink">
            Station {stationNumber} Diagnostics
          </span>
        </div>
        <span className="text-[11.5px] font-medium text-ink-3">
          {clock?.kind === "computed"
            ? `Computed (${formatDuration(clock.ms)})`
            : clock?.kind === "computing"
              ? "Computing..."
              : "Ready"}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 text-[12px]">
        {stationNumber === 1 && (
          <>
            <div>
              <span className="text-ink-3">Total Units</span>
              <p className="font-semibold text-ink">{formatInt(state?.units ?? intake?.units ?? 0)}</p>
            </div>
            <div>
              <span className="text-ink-3">Sensors / Unit</span>
              <p className="font-semibold text-ink">{formatInt(intake?.sensors ?? 590)}</p>
            </div>
            <div>
              <span className="text-ink-3">Missing Readings</span>
              <p className="font-semibold text-ink">
                {intake ? formatPercent(intake.missing_share) : "0%"}
              </p>
            </div>
            <div>
              <span className="text-ink-3">Temporal Order</span>
              <p className="font-semibold text-ink">{intake?.in_time_order ? "Strict" : "Standard"}</p>
            </div>
          </>
        )}

        {stationNumber === 2 && (
          <>
            <div>
              <span className="text-ink-3">Monitored</span>
              <p className="font-semibold text-ink">
                {intake ? `${intake.sensors - intake.unmonitored_sensors.length} sensors` : "Active"}
              </p>
            </div>
            <div>
              <span className="text-ink-3">Active Alarms</span>
              <p className="font-semibold text-fail">
                {state ? `${state.alarms.length} triggered` : "0"}
              </p>
            </div>
            <div>
              <span className="text-ink-3">Risk Assessment</span>
              <p className="font-semibold text-ink">
                {state?.stages.sensor_risk.status === "done" ? "Evaluated" : "Computing"}
              </p>
            </div>
            <div>
              <span className="text-ink-3">Control Charts</span>
              <p className="font-semibold text-ink">
                {state?.stages.control_charts.status === "done" ? "T² & SPE active" : "Pending"}
              </p>
            </div>
          </>
        )}

        {stationNumber === 3 && (
          <>
            <div>
              <span className="text-ink-3">Wafer Maps</span>
              <p className="font-semibold text-ink">{formatInt(state?.wafers ?? intake?.wafers ?? 0)}</p>
            </div>
            <div>
              <span className="text-ink-3">Lots</span>
              <p className="font-semibold text-ink">{formatInt(intake?.lots ?? 1)}</p>
            </div>
            <div>
              <span className="text-ink-3">Pattern Classifier</span>
              <p className="font-semibold text-ink">
                {state?.stages.wafer_pattern.status === "done" ? "Completed" : "Active"}
              </p>
            </div>
            <div>
              <span className="text-ink-3">Novelty Detection</span>
              <p className="font-semibold text-ink">Energy score</p>
            </div>
          </>
        )}

        {stationNumber === 4 && (
          <>
            <div>
              <span className="text-ink-3">Stamp Status</span>
              <p className="font-semibold text-ink">
                {revealed?.has("final_test") ? "Verified" : "Pending"}
              </p>
            </div>
            <div>
              <span className="text-ink-3">Failed Flagged</span>
              <p className="font-semibold text-pass">
                {final ? `${final.failed_flagged} of ${final.failed_units}` : "—"}
              </p>
            </div>
            <div>
              <span className="text-ink-3">Label Concordance</span>
              <p className="font-semibold text-ink">
                {final && final.wafers_with_label > 0
                  ? `${final.wafers_agreeing}/${final.wafers_with_label}`
                  : "Ground truth"}
              </p>
            </div>
            <div>
              <span className="text-ink-3">Outcome Tone</span>
              <p className="font-semibold capitalize text-ink">{finalTest.tone}</p>
            </div>
          </>
        )}
      </div>

      <div className="border-t border-hairline/70 pt-2.5 text-[11px] leading-4 text-ink-3">
        Inspect telemetry and graphs on the right. Click &quot;Back to full pipeline&quot; above to
        return to the 4-station overview.
      </div>
    </div>
  );
}

/**
 * Station 4 detailed outcome and accuracy drawer for the Focused view.
 */
function OutcomeDrawer({
  state,
  finalTest,
  revealed,
}: {
  state: RunState;
  finalTest: { tone: StationTone; sentence: string };
  revealed: ReadonlySet<StageId>;
}) {
  const finalStage = state.stages.final_test;
  const result = revealed.has("final_test") ? stageResult(state, "final_test") : null;

  if (finalStage.status === "skipped") {
    return <NotYet stage={finalStage} what="Actual outcome" />;
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h3 className="text-[20px] font-[620] tracking-[-0.01em] text-ink sm:text-[22px]">
          Outcome Verification & Correlation
        </h3>
        <p className="mt-1 max-w-[85ch] text-[14px] leading-6 text-ink-2">
          {finalTest.sentence}
        </p>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-4">
        <div className="rounded-[18px] bg-surface p-4 shadow-xs">
          <div className="text-[12px] font-medium text-ink-3">Verified Units</div>
          <div className="readout mt-1 text-[26px] font-semibold text-ink">
            {formatInt(result?.units_with_result ?? state.units ?? 0)}
          </div>
          <div className="mt-0.5 text-[11px] text-ink-3">physical electrical test</div>
        </div>

        <div className="rounded-[18px] bg-surface p-4 shadow-xs">
          <div className="text-[12px] font-medium text-ink-3">Defects Caught Early</div>
          <div className="readout mt-1 text-[26px] font-semibold text-pass">
            {result ? formatInt(result.failed_flagged) : "—"}
          </div>
          <div className="mt-0.5 text-[11px] text-ink-3">
            {result ? `of ${formatInt(result.failed_units)} failed units` : "correlating..."}
          </div>
        </div>

        <div className="rounded-[18px] bg-surface p-4 shadow-xs">
          <div className="text-[12px] font-medium text-ink-3">False Alarms</div>
          <div className="readout mt-1 text-[26px] font-semibold text-concern">
            {result ? formatInt(result.passed_flagged) : "—"}
          </div>
          <div className="mt-0.5 text-[11px] text-ink-3">passed units flagged</div>
        </div>

        <div className="rounded-[18px] bg-surface p-4 shadow-xs">
          <div className="text-[12px] font-medium text-ink-3">Wafer Concordance</div>
          <div className="readout mt-1 text-[26px] font-semibold text-ink">
            {result && result.wafers_with_label > 0
              ? formatPercent(result.wafers_agreeing / result.wafers_with_label)
              : "100%"}
          </div>
          <div className="mt-0.5 text-[11px] text-ink-3">
            {result ? `${result.wafers_agreeing} / ${result.wafers_with_label} matching` : "label verification"}
          </div>
        </div>
      </div>

      {/* Detail sections */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <DrawerSection
          title="Sensor Risk vs Physical Test"
          description="Did early sensor alarms in Station 2 predict the true electrical test failures at Station 4?"
        >
          <div className="space-y-3 rounded-[16px] bg-surface p-5 text-[13px] leading-6 text-ink-2 shadow-xs">
            {result ? (
              <>
                <p>
                  <strong>{formatInt(result.failed_flagged)}</strong> out of{" "}
                  <strong>{formatInt(result.failed_units)}</strong> failed units were successfully
                  flagged by the in-line models before wafer test.
                </p>
                {result.passed_flagged > 0 ? (
                  <p className="text-ink-3">
                    <strong>{formatInt(result.passed_flagged)}</strong> passing units were
                    conservatively flagged as high risk.
                  </p>
                ) : null}
                <div className="flex items-center gap-2 pt-2">
                  <span className="inline-flex size-2 rounded-full bg-pass" />
                  <span className="text-[12px] font-medium text-ink">
                    Early prediction precision:{" "}
                    {result.failed_flagged + result.passed_flagged > 0
                      ? formatPercent(
                          result.failed_flagged / (result.failed_flagged + result.passed_flagged),
                        )
                      : "100%"}
                  </span>
                </div>
              </>
            ) : (
              <p>Awaiting final test completion to compare model flags against ground truth.</p>
            )}
          </div>
        </DrawerSection>

        <DrawerSection
          title="Wafer Pattern Classification vs Defect Labels"
          description="Comparison between spatial defect recognition in Station 3 and fab inspection labels."
        >
          <div className="space-y-3 rounded-[16px] bg-surface p-5 text-[13px] leading-6 text-ink-2 shadow-xs">
            {result && result.wafers_with_label > 0 ? (
              <>
                <p>
                  <strong>{result.wafers_agreeing}</strong> of{" "}
                  <strong>{result.wafers_with_label}</strong> wafer defect maps had exact agreement
                  between predicted spatial cluster and fab ground truth.
                </p>
                <div className="flex items-center gap-2 pt-2">
                  <span className="inline-flex size-2 rounded-full bg-signal" />
                  <span className="text-[12px] font-medium text-ink">
                    Spatial agreement rate:{" "}
                    {formatPercent(result.wafers_agreeing / result.wafers_with_label)}
                  </span>
                </div>
              </>
            ) : (
              <p>
                Wafers in this run were tested without manual visual labels, so predictions serve as
                the primary defect classification.
              </p>
            )}
          </div>
        </DrawerSection>
      </div>
    </div>
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
  onClick,
  canOpen = true,
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
  onClick?: () => void;
  canOpen?: boolean;
  children: ReactNode;
}) {
  const sweep = useChangeKey(stagesShown);
  return (
    <div
      role="button"
      tabIndex={canOpen ? 0 : undefined}
      onClick={canOpen ? onClick : undefined}
      onKeyDown={(e) => {
        if (canOpen && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onClick?.();
        }
      }}
      aria-labelledby={labelledBy}
      data-open={open || undefined}
      className={cn(
        "group/tile glow relative row-span-3 grid min-w-0 grid-rows-subgrid rounded-[22px] border-[2.5px] border-transparent bg-clip-padding pt-4 pr-4 pb-4 pl-14 transition-all duration-200 sm:pr-5 md:pt-12 md:pl-5",
        canOpen &&
          "cursor-pointer hover:-translate-y-1 hover:border-hairline-strong/80 hover:bg-surface-2/30 hover:shadow-[0_12px_28px_-10px_rgb(0_0_0/0.1)] dark:hover:shadow-[0_16px_32px_-12px_rgb(0_0_0/0.6)] focus-visible:outline-2 focus-visible:outline-signal focus-visible:outline-offset-2",
        // Column rules between stations, inset so they never touch the rounded corners.
        "before:pointer-events-none before:absolute before:top-12 before:bottom-6 before:left-0 before:hidden before:w-px before:bg-hairline md:[&:nth-child(2n)]:before:block xl:[&:nth-child(n+2)]:before:block",
        tone === "alarm" && "bg-[color-mix(in_oklab,var(--fail)_7%,transparent)] before:opacity-0",
        open && "before:opacity-0 ring-2 ring-signal/50",
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
      <div className="mt-3.5 flex min-w-0 flex-col gap-1.5">{children}</div>
      {canOpen ? (
        <div className="mt-3 flex items-center justify-end border-t border-hairline/60 pt-2 text-[11.5px] font-medium text-ink-3 transition-colors">
          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-ink-2 transition-all group-hover/tile:text-signal group-hover/tile:translate-x-0.5">
            Details &rarr;
          </span>
        </div>
      ) : null}
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
  const canOpen = true;

  return (
    <Tile
      index={index}
      tone={summary.tone}
      reached={reached}
      live={live}
      stagesShown={shownCount}
      labelledBy={id}
      open={open}
      canOpen={canOpen}
      onClick={() => onOpen(n)}
      overlay={pulse > 0 ? <Pulse key={pulse} /> : null}
      heading={
        <>
          <h3
            id={id}
            className="inline-flex items-center text-[16px] leading-6 font-[630] tracking-[-0.01em]"
          >
            <span className="mr-2 inline-flex size-5 items-center justify-center rounded-full bg-surface-2 text-[11px] font-bold text-ink-2 shadow-[inset_0_0_0_1px_var(--hairline)]">
              {n}
            </span>
            {summary.name}
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
    </Tile>
  );
}
