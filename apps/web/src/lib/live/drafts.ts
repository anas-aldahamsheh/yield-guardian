/**
 * What a person has begun on the Line page but not run yet: the open way in, an unsent drawing,
 * an upload the API has checked. Kept in this tab's sessionStorage, so a reload keeps it; never
 * sent to the server, and gone when the tab closes. Storage can be missing or refuse (a private
 * window, blocked site data, a full quota): every access is guarded, and the page works the
 * same without it, only forgetting the draft on a reload.
 */

const PREFIX = "yield-guardian:line:";

export const DRAFT_KEYS = {
  /** The input bar's open panel ("case", "draw" or "upload"). */
  way: "way",
  /** The drawing on the draw panel (lib/live/drafts.ts DrawingDraft). */
  drawing: "drawing",
  /** The checked upload on the upload panel (its UploadSummary). */
  upload: "upload",
  /** Uploaded sensor file draft. */
  uploadSensors: "upload_sensors",
  /** Uploaded wafer maps file draft. */
  uploadWafers: "upload_wafers",
  /** The active run currently running or viewed on the Line page. */
  activeRun: "active_run",
} as const;

export type DraftKey = (typeof DRAFT_KEYS)[keyof typeof DRAFT_KEYS];

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.sessionStorage;
  } catch {
    return null;
  }
}

export function readDraft(key: DraftKey): string | null {
  try {
    return storage()?.getItem(PREFIX + key) ?? null;
  } catch {
    return null;
  }
}

/** Keeps a draft, or forgets it with null. False when storage refused. */
export function writeDraft(key: DraftKey, value: string | null): boolean {
  try {
    const s = storage();
    if (!s) return false;
    if (value == null) s.removeItem(PREFIX + key);
    else s.setItem(PREFIX + key, value);
    return true;
  } catch {
    return false;
  }
}

/** A draft kept as JSON, or null when there is none or it is not one `valid` accepts. */
export function readJsonDraft<T>(key: DraftKey, valid: (value: unknown) => value is T): T | null {
  const text = readDraft(key);
  if (text == null) return null;
  try {
    const value: unknown = JSON.parse(text);
    return valid(value) ? value : null;
  } catch {
    return null;
  }
}

export function writeJsonDraft(key: DraftKey, value: unknown): boolean {
  if (value == null) return writeDraft(key, null);
  try {
    return writeDraft(key, JSON.stringify(value));
  } catch {
    return false;
  }
}

/**
 * An unsent drawing: the chosen die layout and, for each layout drawn on, its wafers as
 * WM-811K maps in base64 (the run input's own encoding) and the wafer being painted.
 */
export interface DrawingDraft {
  layoutId: string | null;
  edits: Record<string, { wafers: string[]; current: number }>;
}

export function isDrawingDraft(value: unknown): value is DrawingDraft {
  if (typeof value !== "object" || value === null) return false;
  const draft = value as Partial<DrawingDraft>;
  if (draft.layoutId !== null && typeof draft.layoutId !== "string") return false;
  if (typeof draft.edits !== "object" || draft.edits === null) return false;
  return Object.values(draft.edits).every(
    (edit) =>
      typeof edit === "object" &&
      edit !== null &&
      Array.isArray(edit.wafers) &&
      edit.wafers.every((w) => typeof w === "string") &&
      Number.isInteger(edit.current),
  );
}

/** Fired on window when runs this page may show are gone: detail is the run id, or null for all. */
export const RUNS_GONE = "yg:runs-gone";

/** Forgets what this tab kept for the line and tells open pages that `runId` (or every run) is gone. */
export function announceRunsGone(runId: string | null): void {
  if (runId == null) for (const key of Object.values(DRAFT_KEYS)) writeDraft(key, null);
  else if (readDraft(DRAFT_KEYS.activeRun) === runId) writeDraft(DRAFT_KEYS.activeRun, null);
  if (typeof window !== "undefined")
    window.dispatchEvent(new CustomEvent<string | null>(RUNS_GONE, { detail: runId }));
}
