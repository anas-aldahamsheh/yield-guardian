/**
 * Types of the Yield Guardian API, generated from openapi.json (see README.md).
 * Every schema is exported by name, for example `RunEvent` or `InvestigationEvent`.
 */
export type * from "./schema";
export type { components, operations, paths } from "./schema";

import type { WaferMap } from "./schema";

export const API_PREFIX = "/api/v1";
export const LINE_SOCKET_PATH = "/ws/line";
export const CSRF_HEADER = "X-CSRF-Token";
/** The HttpOnly cookie that holds this device's session (and so its workspace). */
export const SESSION_COOKIE = "yg_session";
export const PROBLEM_MEDIA_TYPE = "application/problem+json";

/** Values of a decoded wafer-map cell. */
export const WAFER_CELL = { noDie: 0, pass: 1, fail: 2 } as const;

/** Decode `WaferMap.cells` (base64, row-major, one byte per die position). */
export function decodeWaferCells(map: WaferMap): Uint8Array {
  const binary = atob(map.cells);
  if (binary.length !== map.height * map.width) {
    throw new Error(
      `Wafer map has ${binary.length} cells, expected ${map.height} x ${map.width}`,
    );
  }
  const cells = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    const value = binary.charCodeAt(i);
    if (value > WAFER_CELL.fail) throw new Error(`Invalid wafer cell value ${value} at ${i}`);
    cells[i] = value;
  }
  return cells;
}
