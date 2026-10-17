"use client";

import { XIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { formatInt, formatPercent, formatPlantTime, plural } from "@/lib/format";
import { stageResult, type RunState, type StageId } from "@/lib/live/run-state";
import { STATION_NAME } from "@/lib/live/stations";
import { stationAt, type Focus } from "@/lib/live/url-state";
import { cn } from "@/lib/utils";

import { DrawerSection, Fact, NotYet } from "./drawer-parts";
// Imported with the page, not when a drawer first opens: a drawer the page arrives with (a
// reload, a link) is in the server's HTML and on screen at once. Loaded on demand, it would be
// streamed behind a loading state and swapped in a frame after the page arrived.
import { UnitsDrawer } from "./drawer-units";
import { WafersDrawer } from "./drawer-wafers";

/**
 * Whether this page was opened anew at its address, not reloaded or reached with back and
 * forward, and nothing has scrolled it yet: there is no reading position to keep.
 */
function openedAnew(): boolean {
  const entry = performance.getEntriesByType("navigation")[0] as
    PerformanceNavigationTiming | undefined;
  return entry?.type === "navigate" && window.scrollY === 0;
}

/**
 * A station's drawer, opened under the line: everything that station computed, for every unit
 * or wafer of the run. It shows only results the line has reached, so it never runs ahead of the
 * animation.
 */
export function StationDrawer({
  station,
  state,
  revealed,
  focus,
  onFocus,
  onClose,
  restored = false,
  landing = false,
}: {
  station: 1 | 2 | 3;
  state: RunState;
  revealed: ReadonlySet<StageId>;
  focus: Focus;
  onFocus: (focus: Focus) => void;
  onClose: () => void;
  /**
   * Open because the URL says so (a reload, a link, back and forward), not opened just now: it
   * is shown where it is, without fading in, and the page stays where the browser put it.
   */
  restored?: boolean;
  /** It came with the page itself: a link opened anew brings it into view at once. */
  landing?: boolean;
}) {
  const name = STATION_NAME[stationAt(station)!];
  const heading = useRef<HTMLHeadingElement>(null);
  const shown = (stage: StageId) => revealed.has(stage);
  // The drawer fades in when it opens, never later (a restored one is already there).
  const [quiet] = useState(restored);

  // Opening a station moves the reading position to its drawer: the heading comes to the top,
  // under the site bar (the page's scroll padding), so the drawer's contents are in view.
  useEffect(() => {
    if (restored) {
      // A reload and back and forward keep the scroll position the browser restores; a link
      // opened anew (on another device, say) has none, so the drawer is brought into view.
      if (landing && openedAnew()) {
        heading.current?.focus({ preventScroll: true });
        heading.current?.scrollIntoView({ block: "start" });
      }
      return;
    }
    heading.current?.focus({ preventScroll: true });
    heading.current?.scrollIntoView({
      block: "start",
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
    });
    // Only a station opened anew moves the page, once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [station]);

  return (
    <section
      id="station-drawer"
      aria-labelledby="station-drawer-title"
      className={cn(
        "panel relative mt-8 px-5 pt-5 pb-7 sm:px-7 sm:pt-6 sm:pb-8",
        !quiet && "grow-in",
      )}
    >
      {/* The film's light along the top edge, as on the station that opened it */}
      <span
        aria-hidden="true"
        className="film-light absolute inset-x-7 top-0 h-[2px] rounded-b-full opacity-80"
      />
      <header className="mb-7 flex items-start justify-between gap-4">
        <h2
          id="station-drawer-title"
          ref={heading}
          tabIndex={-1}
          className="text-[26px] leading-8 font-[640] tracking-[-0.02em] text-ink [font-stretch:108%] outline-none sm:text-[30px] sm:leading-9"
        >
          <span className="tnum text-ink-3">{station}</span> {`${name} in detail`}
        </h2>
        <button
          type="button"
          onClick={onClose}
          className="press inline-flex h-9 shrink-0 cursor-pointer items-center gap-1.5 rounded-full pr-3.5 pl-3 text-[13.5px] font-[560] text-ink-2 shadow-[inset_0_0_0_1px_var(--hairline-strong)] hover:bg-surface-2 hover:text-ink"
        >
          <XIcon aria-hidden="true" className="size-4" strokeWidth={2} />
          Close
        </button>
      </header>
      {station === 1 ? <IntakeDrawer state={state} shown={shown("intake")} /> : null}
      {station === 2 ? (
        state.stages.sensor_risk.status === "skipped" &&
        state.stages.control_charts.status === "skipped" ? (
          <NotYet stage={state.stages.sensor_risk} what="Monitoring" />
        ) : (
          <UnitsDrawer
            state={state}
            shown={shown}
            unit={focus?.kind === "unit" ? focus.index : null}
            onUnit={(index) => onFocus({ kind: "unit", index })}
          />
        )
      ) : null}
      {station === 3 ? (
        <WafersDrawer
          state={state}
          shown={shown}
          wafer={focus?.kind === "wafer" ? focus.index : null}
          onWafer={(index) => onFocus({ kind: "wafer", index })}
        />
      ) : null}
    </section>
  );
}

export function IntakeDrawer({ state, shown }: { state: RunState; shown: boolean }) {
  const intake = shown ? stageResult(state, "intake") : null;
  if (!intake) return <NotYet stage={state.stages.intake} what="The intake" />;
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-10 lg:grid-cols-2">
      <DrawerSection
        title="What came in"
        description={state.origin ? `${state.origin.title}. ${state.origin.rule}` : undefined}
      >
        <dl className="tnum grid grid-cols-2 gap-x-6 gap-y-4 rounded-[16px] bg-surface-2 p-4 sm:p-5">
          <Fact label="Sensor units">{formatInt(intake.units)}</Fact>
          <Fact label="Sensors per unit">{formatInt(intake.sensors)}</Fact>
          <Fact label="Missing readings">{`${formatInt(intake.missing_readings)} (${formatPercent(intake.missing_share)})`}</Fact>
          <Fact label="In time order">
            {intake.units
              ? intake.in_time_order
                ? "Yes"
                : "No: drift is not charted"
              : "No units"}
          </Fact>
          <Fact label="First unit">
            {intake.first_timestamp ? formatPlantTime(intake.first_timestamp) : "no time"}
          </Fact>
          <Fact label="Last unit">
            {intake.last_timestamp ? formatPlantTime(intake.last_timestamp) : "no time"}
          </Fact>
          <Fact label="Wafer maps">{formatInt(intake.wafers)}</Fact>
          <Fact label="Lots">{formatInt(intake.lots)}</Fact>
        </dl>
      </DrawerSection>
      <DrawerSection
        title="Sensors the models do not use"
        description={`${plural(intake.unmonitored_sensors.length, "sensor")} were constant or empty in training, so no model reads them. Their lamps on the sensor bank stay dark.`}
      >
        <p className="tnum rounded-[16px] bg-surface-2 p-4 text-[13px] leading-6 text-ink-2 sm:p-5">
          {intake.unmonitored_sensors.join(", ") || "None."}
        </p>
      </DrawerSection>
    </div>
  );
}
