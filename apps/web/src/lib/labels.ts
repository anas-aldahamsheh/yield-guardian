/** Words for API enums, in one place so every screen names things the same way. */

export type PatternLabel =
  | "Center"
  | "Donut"
  | "Edge-Loc"
  | "Edge-Ring"
  | "Loc"
  | "Near-full"
  | "Random"
  | "Scratch"
  | "none";

export function patternName(label: PatternLabel | null | undefined): string {
  if (label == null) return "Unlabelled";
  return label === "none" ? "No pattern" : label;
}

export const ROLE_NAMES: Record<string, string> = {
  investigator: "Investigator",
  writer: "Writer",
  verifier: "Verifier",
  chat: "Chat",
  router: "Router",
  ocr: "Document reading (OCR)",
  vision: "Vision",
};

export const ROLE_JOBS: Record<string, string> = {
  investigator: "Plans the investigation and calls the data tools",
  writer: "Drafts the report from the evidence",
  verifier: "Checks every claim against the evidence",
  chat: "Answers engineers' questions that need a model",
  router: "Decides whether a question can be answered by rules",
  ocr: "Reads documents",
  vision: "Reads images",
};

export const INVESTIGATION_STATUS: Record<string, string> = {
  queued: "Queued",
  running: "Running",
  awaiting_decision: "Awaiting decision",
  approved: "Approved",
  rejected: "Rejected",
  failed: "Failed",
};

export const ALARM_KIND: Record<string, string> = {
  risk: "Failure risk",
  t2: "Hotelling T²",
  spe: "SPE (Q)",
  ewma: "EWMA",
  cusum: "CUSUM",
};

export const BAND_NAME: Record<string, string> = {
  low: "Low",
  elevated: "Elevated",
  high: "High",
};

export const BLOCK_NAME: Record<string, string> = {
  train: "Training block",
  validation: "Validation block",
  test: "Test block",
};

export const TOOL_NAME: Record<string, string> = {
  get_unit: "Unit record",
  get_risk: "Failure risk",
  get_shap: "SHAP explanation",
  get_feature_groups: "Sensor groups",
  get_fdc_window: "Control-chart window",
  get_contributions: "Control-chart contributions",
  get_sensor_health: "Sensor health",
  get_wafer_prediction: "Wafer prediction",
  get_similar_wafers: "Similar wafers",
  get_lot_stats: "Lot statistics",
  search_knowledge: "Literature search",
};

export const HEALTH_STATUS: Record<string, string> = {
  ok: "OK",
  watch: "Watch",
  maintenance: "Maintenance",
  dead: "Dead",
};

export const WORK_ORDER_STATUS: Record<string, string> = {
  open: "Open",
  in_progress: "In progress",
  done: "Done",
  cancelled: "Cancelled",
};
