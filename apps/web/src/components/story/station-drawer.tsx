"use client";

import { useEffect, useRef, useState } from "react";

import { formatInt, formatPercent, formatPlantTime, plural } from "@/lib/format";
import { stageResult, type RunState, type StageId } from "@/lib/live/run-state";
import { STATION_NAME } from "@/lib/live/stations";
import { stationAt, type Focus } from "@/lib/live/url-state";
import { cn } from "@/lib/utils";

import { DrawerSection, Fact, NotYet } from "./drawer-parts";
import { UnitsDrawer } from "./drawer-units";
import { WafersDrawer } from "./drawer-wafers";

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
}) {
  const name = STATION_NAME[stationAt(station)!];
  const heading = useRef<HTMLHeadingElement>(null);
  const shown = (stage: StageId) => revealed.has(stage);
  // The drawer fades in when it opens, never later (a restored one is already there).
  const [quiet] = useState(restored);

  // Opening a station moves the reading position to its drawer: the heading comes to the top,
  // under the site bar (the page's scroll padding), so the drawer's contents are in view.
  useEffect(() => {
    if (restored) return;
    heading.current?.focus({ preventScroll: true });
    heading.current?.scrollIntoView({
      block: "start",
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
    });
    // A drawer arriving with the URL stays put; one chosen afterwards comes into view.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [station]);

  return (
    <section
      id="station-drawer"
      aria-labelledby="station-drawer-title"
      className={cn("panel mt-6 px-4 pt-4 pb-6 sm:px-6", !quiet && "swap-in")}
    >
      <header className="mb-5 flex items-start justify-between gap-4 border-b border-hairline pb-3">
        <h2
          id="station-drawer-title"
          ref={heading}
          tabIndex={-1}
          className="text-[20px] leading-7 font-semibold text-ink outline-none"
        >
          <span className="tnum text-ink-3">{station}</span> {`${name} in detail`}
        </h2>
        <button
          type="button"
          onClick={onClose}
          className="rounded-[4px] border border-hairline-strong px-2.5 py-1 text-[13px] leading-5 text-ink hover:bg-die-2"
        >
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

function IntakeDrawer({ state, shown }: { state: RunState; shown: boolean }) {
  const intake = shown ? stageResult(state, "intake") : null;
  if (!intake) return <NotYet stage={state.stages.intake} what="The intake" />;
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-8 lg:grid-cols-2">
      <DrawerSection
        title="What came in"
        description={state.origin ? `${state.origin.title}. ${state.origin.rule}` : undefined}
      >
        <dl className="tnum grid grid-cols-2 gap-x-6 gap-y-3">
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
        <p className="tnum text-[13px] leading-6 text-ink-2">
          {intake.unmonitored_sensors.join(", ") || "None."}
        </p>
      </DrawerSection>
    </div>
  );
}
