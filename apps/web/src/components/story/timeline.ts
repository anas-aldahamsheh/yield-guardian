import type { RunAlarm } from "@yield-guardian/contracts";
import gsap from "gsap";

import { stageResult, type Arrival, type RunState, type StageId } from "@/lib/live/run-state";
import { turnsRed } from "@/lib/live/stations";
import type { Focus } from "@/lib/live/url-state";

import { unitsToShow } from "./scales";
import { restScene, stationOfStage, type LineStation, type Scene, type SceneStore } from "./scene";

/**
 * The line's one GSAP timeline for a run. It is advanced only by arrived results: each
 * stage_result appends a segment that shows that result (units walking through the console,
 * dies revealed on the prober), so the line never runs ahead of the data. The sensor track
 * (chamber, console) and the wafer track (prober, carrier) have their own cursors, so the two
 * play side by side; final test waits for both. Alarms appear when the walk reaches their unit
 * or wafer.
 */
export interface LineTimeline {
  push(arrival: Arrival): void;
  /** The line is at rest and the chosen unit or wafer changed: the dials glide to it. */
  refocus(): void;
  /** Jump to the end: every arrived result shown. */
  finish(): void;
  kill(): void;
}

type Track = "sensor" | "wafer";

const TRACK: Partial<Record<StageId, Track>> = {
  sensor_risk: "sensor",
  control_charts: "sensor",
  drift_health: "sensor",
  wafer_pattern: "wafer",
  wafer_similar: "wafer",
  lot: "wafer",
};

/** Seconds for the console to walk every unit, and the bounds of one unit's step. */
const UNIT_WALK = 4.2;
const UNIT_STEP: [number, number] = [0.07, 0.24];
/** Seconds to probe the first wafer die by die; later wafers go faster. */
const FIRST_WAFER = 2.4;
const LATER_WAFERS = 4.0;
const WAFER_STEP: [number, number] = [0.14, 0.5];
const CARRIER_SLOTS = 25;

const clamp = (v: number, [lo, hi]: [number, number]) => Math.min(hi, Math.max(lo, v));

function dieCount(map: { cells: string }): number {
  const cells = atob(map.cells);
  let n = 0;
  for (let i = 0; i < cells.length; i += 1) if (cells.charCodeAt(i) !== 0) n += 1;
  return n;
}

export function createLineTimeline(
  store: SceneStore,
  run: () => RunState,
  focus: () => Focus,
): LineTimeline {
  const tl = gsap.timeline({ onComplete: settle });
  const at: Record<Track, number> = { sensor: 0, wafer: 0 };
  /** When each stage's segment reaches each unit or wafer, to place its alarms. */
  const unitTime = new Map<StageId, Map<number, number>>();
  const waferTime = new Map<StageId, Map<number, number>>();
  const segmentEnd = new Map<StageId, number>();
  const waiting = new Map<StageId, RunAlarm[]>();
  const pulsed = new Set<LineStation>();
  const needles = { t2: 0, spe: 0, risk: 0 };
  let glideTween: gsap.core.Tween | null = null;

  function reveal(stage: StageId) {
    store.set((s) => (s.revealed.has(stage) ? {} : { revealed: new Set([...s.revealed, stage]) }));
  }

  function showAlarm(alarm: RunAlarm) {
    store.set((s) => {
      if (s.alarms.has(alarm.alarm_id)) return {};
      const station = stationOfStage(alarm.stage);
      const patch: Partial<Scene> = { alarms: new Set([...s.alarms, alarm.alarm_id]) };
      if (station && turnsRed(alarm) && !pulsed.has(station)) {
        pulsed.add(station);
        patch.pulses = { ...s.pulses, [station]: s.pulses[station] + 1 };
      }
      return patch;
    });
  }

  function placeAlarm(alarm: RunAlarm) {
    const end = segmentEnd.get(alarm.stage);
    if (end == null) {
      waiting.set(alarm.stage, [...(waiting.get(alarm.stage) ?? []), alarm]);
      return;
    }
    const t =
      (alarm.unit_index != null ? unitTime.get(alarm.stage)?.get(alarm.unit_index) : undefined) ??
      (alarm.wafer_index != null
        ? waferTime.get(alarm.stage)?.get(alarm.wafer_index)
        : undefined) ??
      end;
    if (t <= tl.time()) showAlarm(alarm);
    else tl.call(showAlarm, [alarm], t);
  }

  function start(track: Track | "both"): number {
    const now = tl.time();
    if (track === "both") return Math.max(at.sensor, at.wafer, now);
    return Math.max(at[track], now);
  }

  function end(track: Track | "both", t: number) {
    if (track === "both") at.sensor = at.wafer = t;
    else at[track] = t;
  }

  /** Needles glide in log space (T², SPE span decades) and in risk units. */
  function targetOf(
    index: number,
    include: { charts: boolean; risk: boolean },
  ): Partial<typeof needles> {
    const state = run();
    const charts = include.charts ? stageResult(state, "control_charts")?.units[index] : null;
    const risk = include.risk ? stageResult(state, "sensor_risk")?.units[index] : null;
    const target: Partial<typeof needles> = {};
    if (charts) {
      target.t2 = Math.log10(Math.max(charts.t2, 1e-9));
      target.spe = Math.log10(Math.max(charts.spe, 1e-9));
    }
    if (risk) target.risk = risk.risk;
    return target;
  }

  /** Puts the tween's start where the dials are now (the first unit starts at the dial's foot). */
  function syncNeedles() {
    const s = store.get();
    if (s.t2 != null) needles.t2 = Math.log10(Math.max(s.t2, 1e-9));
    if (s.spe != null) needles.spe = Math.log10(Math.max(s.spe, 1e-9));
    if (s.risk != null) needles.risk = s.risk;
  }

  function writeNeedles(target: Partial<typeof needles>) {
    store.set({
      ...(target.t2 != null ? { t2: 10 ** needles.t2 } : {}),
      ...(target.spe != null ? { spe: 10 ** needles.spe } : {}),
      ...(target.risk != null ? { risk: needles.risk } : {}),
    });
  }

  function needlesTo(
    index: number,
    t: number,
    duration: number,
    include: { charts: boolean; risk: boolean },
  ) {
    const target = targetOf(index, include);
    if (!Object.keys(target).length) return;
    tl.call(syncNeedles, [], t);
    tl.to(
      needles,
      { ...target, duration, ease: "power3.out", onUpdate: () => writeNeedles(target) },
      t,
    );
  }

  /** Outside the run's timeline: the dials glide to a unit once the line is at rest. */
  function glide(index: number | null) {
    if (index == null) return;
    const revealed = store.get().revealed;
    const target = targetOf(index, {
      charts: revealed.has("control_charts"),
      risk: revealed.has("sensor_risk"),
    });
    if (!Object.keys(target).length) return;
    syncNeedles();
    glideTween?.kill();
    glideTween = gsap.to(needles, {
      ...target,
      duration: 0.45,
      ease: "power3.out",
      onUpdate: () => writeNeedles(target),
    });
  }

  function walkUnits(
    stage: StageId,
    total: number,
    from: number,
    include: { charts: boolean; risk: boolean },
  ): number {
    const state = run();
    const alarmUnits = new Set(
      state.alarms.filter((a) => a.unit_index != null).map((a) => a.unit_index!),
    );
    const { units } = unitsToShow(total, alarmUnits);
    const step = clamp(UNIT_WALK / Math.max(1, units.length), UNIT_STEP);
    const times = new Map<number, number>();
    units.forEach((k, i) => {
      const t = from + i * step;
      times.set(k, t);
      tl.call(
        () => store.set((s) => ({ unit: k, unitsPassed: Math.max(s.unitsPassed, k + 1) })),
        [],
        t,
      );
      needlesTo(k, t, step * 0.92, include);
    });
    // Alarms of units the walk skips (more than 120 units) appear at the next unit shown.
    for (let k = 0; k < total; k += 1) {
      if (!times.has(k)) times.set(k, times.get(units.find((u) => u > k) ?? units.at(-1)!) ?? from);
    }
    unitTime.set(stage, times);
    return from + units.length * step;
  }

  function segment(stage: StageId) {
    const state = run();
    const track: Track | "both" =
      stage === "intake" || stage === "final_test" ? "both" : TRACK[stage]!;
    const t0 = start(track);
    let t1 = t0;
    tl.call(reveal, [stage], t0);

    switch (stage) {
      case "intake": {
        const units = stageResult(state, "intake")?.units ?? 0;
        if (units > 0) {
          const bank = { v: 0 };
          tl.to(
            bank,
            {
              v: 1,
              duration: 0.8,
              ease: "power1.inOut",
              onUpdate: () => store.set({ bank: bank.v }),
            },
            t0,
          );
          t1 = t0 + 0.8;
        } else {
          t1 = t0 + 0.3;
        }
        break;
      }
      case "sensor_risk": {
        const units = stageResult(state, "sensor_risk")?.units.length ?? 0;
        const chartsComing =
          state.stages.control_charts.status === "done" ||
          state.stages.control_charts.status === "running";
        // The console walks the units once, with the control charts; on its own, risk walks them quickly.
        t1 =
          chartsComing || !units
            ? t0 + 0.4
            : walkUnits(stage, units, t0, { charts: false, risk: true }) + 0.2;
        // Charts already walked the units: the risk dial joins at the unit shown.
        if (state.stages.control_charts.status === "done" && units) {
          tl.call(() => glide(store.get().unit ?? units - 1), [], t0 + 0.05);
        }
        break;
      }
      case "control_charts": {
        const units = stageResult(state, "control_charts")?.units.length ?? 0;
        t1 =
          walkUnits(stage, units, t0, {
            charts: true,
            risk: state.stages.sensor_risk.status === "done",
          }) + 0.25;
        break;
      }
      case "drift_health": {
        const units =
          stageResult(state, "control_charts")?.units.length ??
          stageResult(state, "sensor_risk")?.units.length ??
          0;
        const groups = stageResult(state, "drift_health")?.groups ?? [];
        const drift = { v: 0 };
        const duration = 1.4;
        tl.to(
          drift,
          { v: units, duration, ease: "none", onUpdate: () => store.set({ drift: drift.v }) },
          t0,
        );
        const times = new Map<number, number>();
        for (let k = 0; k < units; k += 1)
          times.set(k, t0 + (duration * (k + 1)) / Math.max(1, units));
        unitTime.set(stage, times);
        t1 = t0 + duration + (groups.length ? 0.2 : 0);
        break;
      }
      case "wafer_pattern": {
        const wafers = stageResult(state, "wafer_pattern")?.wafers ?? [];
        // The prober takes the first lot's wafers one by one into the carrier (up to its 25 slots).
        const lot = wafers[0]?.lot;
        const walked = wafers.filter((w) => w.lot === lot).slice(0, CARRIER_SLOTS);
        const later = clamp(LATER_WAFERS / Math.max(1, walked.length - 1), WAFER_STEP);
        const times = new Map<number, number>();
        let t = t0;
        walked.forEach((w, i) => {
          const duration = i === 0 ? FIRST_WAFER : later;
          const dies = { v: 0 };
          const total = w.map ? dieCount(w.map) : 0;
          tl.call(() => store.set({ wafer: w.index, dies: 0 }), [], t);
          tl.to(
            dies,
            {
              v: total,
              duration: duration * 0.82,
              ease: "none",
              onUpdate: () => store.set({ dies: dies.v }),
            },
            t,
          );
          times.set(w.index, t + duration * 0.82);
          tl.call(
            () => store.set((s) => ({ carrier: Math.max(s.carrier, i + 1) })),
            [],
            t + duration * 0.86,
          );
          t += duration;
        });
        for (const w of wafers) if (!times.has(w.index)) times.set(w.index, t);
        waferTime.set(stage, times);
        t1 = t + 0.2;
        break;
      }
      case "wafer_similar":
        t1 = t0 + 0.3;
        break;
      case "lot":
        t1 = t0 + 0.6;
        break;
      case "final_test": {
        const stamp = { v: 0 };
        tl.to(
          stamp,
          {
            v: 1,
            duration: 0.9,
            ease: "power2.out",
            onUpdate: () => store.set({ stamp: stamp.v }),
          },
          t0,
        );
        t1 = t0 + 0.9;
        break;
      }
    }
    segmentEnd.set(stage, t1);
    end(track, t1);
    for (const alarm of waiting.get(stage) ?? []) placeAlarm(alarm);
    waiting.delete(stage);
    for (const alarm of run().alarms) if (alarm.stage === stage) placeAlarm(alarm);
  }

  /** Once everything arrived has been shown, rest the instruments on the chosen unit and wafer. */
  function settle() {
    const state = run();
    const current = store.get();
    const rest = restScene(state, focus(), current.revealed, current);
    // The dials glide from the last unit walked to the unit they rest on.
    const { t2: _t2, spe: _spe, risk: _risk, ...still } = rest;
    store.set({ ...still, alarms: new Set([...current.alarms, ...rest.alarms]), playing: false });
    glide(rest.unit);
  }

  function play() {
    glideTween?.kill();
    glideTween = null;
    store.set({ playing: true });
    if (tl.paused()) tl.play();
  }

  return {
    push(arrival) {
      const state = run();
      switch (arrival.kind) {
        case "result":
          segment(arrival.stage);
          play();
          break;
        case "skipped":
        case "failed": {
          const track: Track | "both" = TRACK[arrival.stage] ?? "both";
          tl.call(reveal, [arrival.stage], start(track));
          play();
          break;
        }
        case "alarm": {
          const alarm = state.alarms.find((a) => a.alarm_id === arrival.alarmId);
          // Alarms of a stage already scheduled are placed with it; later ones are placed now.
          if (alarm && segmentEnd.has(alarm.stage)) placeAlarm(alarm);
          // A stage the line showed before following the stream (its result came with the
          // run's stored state): the alarm has nothing to wait for.
          else if (alarm && store.get().revealed.has(alarm.stage)) showAlarm(alarm);
          else if (alarm) waiting.set(alarm.stage, [...(waiting.get(alarm.stage) ?? []), alarm]);
          break;
        }
        case "done":
          tl.call(() => {}, [], start("both"));
          play();
          break;
      }
    },
    refocus() {
      if (store.get().playing) return;
      settle();
    },
    finish() {
      tl.progress(1);
      settle();
    },
    kill() {
      glideTween?.kill();
      tl.kill();
    },
  };
}
