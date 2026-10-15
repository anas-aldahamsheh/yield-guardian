import type { PickRunCreate } from "@yield-guardian/contracts";

/**
 * What the Line page keeps in its URL, so a link opens the same view:
 * `/?run=<id>&station=<n>&unit=<index>` (or `wafer=<index>`, or `lot=<name>`), and
 * `alarm=<RA-n>` for the alarm chosen in the rail (the chat reads it, lib/chat/chat.ts).
 * Old links to a unit, wafer or lot page arrive as `/?pick=unit:<id>` (or `wafer:<id>`,
 * `lot:<name>`) and start a run of that item; old station links arrive as `/?station=<n>`
 * without a run, and the station opens once a run has started.
 */

export const STATIONS = [
  "manufacturing",
  "monitoring",
  "wafer_test",
  "investigation",
  "decision",
] as const;
export type Station = (typeof STATIONS)[number];

export type Focus =
  | { kind: "unit"; index: number }
  | { kind: "wafer"; index: number }
  | { kind: "lot"; name: string }
  | null;

export interface LineUrlState {
  runId: string | null;
  /** 1 to 5, the station whose drawer is open (or opens once there is a run). */
  station: number | null;
  focus: Focus;
  /** The alarm chosen in the rail (RunAlarmId). */
  alarm: string | null;
}

const RUN_ID = /^run_[0-9a-z]{8,40}$/;
const RUN_ALARM = /^RA-\d{1,6}$/;
const LOT = /^[A-Za-z0-9_.:\- ]{1,64}$/;
const WAFER_ID = /^[A-Za-z0-9_.]+-\d+$/;
const LOT_ID = /^[A-Za-z0-9_.]{1,64}$/;

function index(value: string | null): number | null {
  if (value == null || !/^\d{1,6}$/.test(value)) return null;
  return Number.parseInt(value, 10);
}

export function parseLineUrl(params: URLSearchParams): LineUrlState {
  const run = params.get("run");
  const runId = run && RUN_ID.test(run) ? run : null;
  const n = index(params.get("station"));
  const station = n != null && n >= 1 && n <= STATIONS.length ? n : null;
  const unit = index(params.get("unit"));
  const wafer = index(params.get("wafer"));
  const lot = params.get("lot");
  const focus: Focus =
    unit != null
      ? { kind: "unit", index: unit }
      : wafer != null
        ? { kind: "wafer", index: wafer }
        : lot && LOT.test(lot)
          ? { kind: "lot", name: lot }
          : null;
  const alarm = params.get("alarm");
  return {
    runId,
    station,
    focus: runId ? focus : null,
    alarm: runId && alarm && RUN_ALARM.test(alarm) ? alarm : null,
  };
}

/** The query string for a state (without "?"): the run's view, or a station waiting for one. */
export function lineQuery(state: LineUrlState): string {
  if (!state.runId) return state.station != null ? `station=${state.station}` : "";
  const params = new URLSearchParams({ run: state.runId });
  if (state.station != null) params.set("station", String(state.station));
  if (state.focus?.kind === "unit") params.set("unit", String(state.focus.index));
  if (state.focus?.kind === "wafer") params.set("wafer", String(state.focus.index));
  if (state.focus?.kind === "lot") params.set("lot", state.focus.name);
  if (state.alarm) params.set("alarm", state.alarm);
  return params.toString();
}

export function stationNumber(station: Station): number {
  return STATIONS.indexOf(station) + 1;
}

export function stationAt(n: number | null): Station | null {
  return n != null && n >= 1 && n <= STATIONS.length ? STATIONS[n - 1]! : null;
}

/** `?pick=` from an old link, as the run it asks for; null when the value is not one. */
export function parsePick(params: URLSearchParams): PickRunCreate | null {
  const pick = params.get("pick");
  if (!pick) return null;
  const colon = pick.indexOf(":");
  if (colon === -1) return null;
  const kind = pick.slice(0, colon);
  const value = pick.slice(colon + 1);
  if (kind === "unit") {
    const id = index(value);
    return id == null ? null : { source: "pick", unit_ids: [id], wafer_ids: [], lot: null };
  }
  if (kind === "wafer") {
    return WAFER_ID.test(value) && value.length <= 80
      ? { source: "pick", unit_ids: [], wafer_ids: [value], lot: null }
      : null;
  }
  if (kind === "lot") {
    return LOT_ID.test(value) ? { source: "pick", unit_ids: [], wafer_ids: [], lot: value } : null;
  }
  return null;
}
