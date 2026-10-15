import type { RunAlarm } from "@yield-guardian/contracts";
import { useSyncExternalStore } from "react";

import { restUnit, restWafer } from "@/lib/live/rest";
import { STAGES, stageResult, type RunState, type StageId } from "@/lib/live/run-state";
import { STATION_STAGES } from "@/lib/live/stations";
import type { Focus } from "@/lib/live/url-state";

/**
 * What the line shows at this moment. The run state holds every result that has arrived; the
 * scene holds how far the line has got in showing them (the animation advances it, one arrived
 * result at a time). Without motion, or once the animation has caught up, the scene is at rest:
 * every arrived result shown, the instruments on the chosen unit and wafer.
 */
export interface Scene {
  revealed: ReadonlySet<StageId>;
  alarms: ReadonlySet<string>;
  /** Counts up each time a station turns red, to play its one pulse. */
  pulses: Readonly<Record<LineStation, number>>;
  /** The unit at the sensor stations (index in the run input). */
  unit: number | null;
  /** Units the line has walked through so far (for the unit strip). */
  unitsPassed: number;
  /** Sensor bank power-up after intake, 0 to 1. */
  bank: number;
  /** Needle readings of the unit at the console (tweened between units). */
  t2: number | null;
  spe: number | null;
  risk: number | null;
  /** Units drawn on the drift strip. */
  drift: number;
  /** The wafer on the prober chuck, and the dies probed on it so far. */
  wafer: number | null;
  dies: number;
  /** Wafers in the carrier. */
  carrier: number;
  /** Final test stamp, 0 to 1. */
  stamp: number;
  /** The animation still has arrived results to show. */
  playing: boolean;
}

export type LineStation = "manufacturing" | "monitoring" | "wafer_test";

export const EMPTY_SCENE: Scene = {
  revealed: new Set(),
  alarms: new Set(),
  pulses: { manufacturing: 0, monitoring: 0, wafer_test: 0 },
  unit: null,
  unitsPassed: 0,
  bank: 0,
  t2: null,
  spe: null,
  risk: null,
  drift: 0,
  wafer: null,
  dies: 0,
  carrier: 0,
  stamp: 0,
  playing: false,
};

export interface SceneStore {
  get(): Scene;
  set(patch: Partial<Scene> | ((scene: Scene) => Partial<Scene>)): void;
  subscribe(listener: () => void): () => void;
}

export function createSceneStore(initial: Scene = EMPTY_SCENE): SceneStore {
  let scene = initial;
  const listeners = new Set<() => void>();
  return {
    get: () => scene,
    set(patch) {
      const next = typeof patch === "function" ? patch(scene) : patch;
      let changed = false;
      for (const key of Object.keys(next) as (keyof Scene)[]) {
        if (!Object.is(scene[key], next[key])) changed = true;
      }
      if (!changed) return;
      scene = { ...scene, ...next };
      for (const listener of listeners) listener();
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

/** Reads one part of the scene; the component renders again only when that part changes. */
export function useScene<T>(store: SceneStore, select: (scene: Scene) => T): T {
  return useSyncExternalStore(
    store.subscribe,
    () => select(store.get()),
    () => select(store.get()),
  );
}

export function stationOfStage(stage: StageId): LineStation | null {
  for (const station of Object.keys(STATION_STAGES) as LineStation[]) {
    if (STATION_STAGES[station].includes(stage)) return station;
  }
  return null;
}

function dieCount(state: RunState, wafer: number | null): number {
  if (wafer == null) return 0;
  const map = stageResult(state, "wafer_pattern")?.wafers[wafer]?.map;
  if (!map) return 0;
  const cells = atob(map.cells);
  let n = 0;
  for (let i = 0; i < cells.length; i += 1) if (cells.charCodeAt(i) !== 0) n += 1;
  return n;
}

/** Readings of one unit, for the console's needles. */
export function unitReadings(
  state: RunState,
  index: number | null,
  revealed: ReadonlySet<StageId>,
) {
  if (index == null) return { t2: null, spe: null, risk: null };
  const charts = revealed.has("control_charts")
    ? stageResult(state, "control_charts")?.units[index]
    : undefined;
  const risk = revealed.has("sensor_risk")
    ? stageResult(state, "sensor_risk")?.units[index]
    : undefined;
  return { t2: charts?.t2 ?? null, spe: charts?.spe ?? null, risk: risk?.risk ?? null };
}

/**
 * The scene at rest for the stages given (by default every stage whose result has arrived):
 * every alarm of those stages shown, the instruments on the rest unit and wafer.
 */
export function restScene(
  state: RunState,
  focus: Focus,
  stages: ReadonlySet<StageId> = new Set(
    STAGES.filter(
      (s) => state.stages[s].status !== "pending" && state.stages[s].status !== "running",
    ),
  ),
  base: Scene = EMPTY_SCENE,
): Scene {
  const revealed = new Set(stages);
  const alarms = new Set(state.alarms.filter((a) => revealed.has(a.stage)).map((a) => a.alarm_id));
  const unit = restUnit(state, focus);
  const wafer = restWafer(state, focus);
  const units =
    stageResult(state, "control_charts")?.units.length ??
    stageResult(state, "sensor_risk")?.units.length ??
    0;
  const wafers = stageResult(state, "wafer_pattern")?.wafers.length ?? 0;
  return {
    ...base,
    revealed,
    alarms,
    unit,
    unitsPassed: revealed.has("control_charts") || revealed.has("sensor_risk") ? units : 0,
    bank: revealed.has("intake") ? 1 : 0,
    ...unitReadings(state, unit, revealed),
    drift: revealed.has("drift_health") ? units : 0,
    wafer: revealed.has("wafer_pattern") ? wafer : null,
    dies: revealed.has("wafer_pattern") ? dieCount(state, wafer) : 0,
    carrier: revealed.has("wafer_pattern") ? wafers : 0,
    stamp: revealed.has("final_test") ? 1 : 0,
    playing: false,
  };
}

export function isAlarmShown(scene: Scene, alarm: RunAlarm): boolean {
  return scene.alarms.has(alarm.alarm_id);
}
