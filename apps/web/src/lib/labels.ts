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
  if (label === "none") return "Light scatter";
  if (label === "Random") return "Heavy scatter";
  return label;
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
  risk: "Failure risk (experimental)",
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

export const HEALTH_STATUS_ORDER = ["dead", "maintenance", "watch", "ok"] as const;
export type HealthStatus = (typeof HEALTH_STATUS_ORDER)[number];

export const UNIVARIATE_DIRECTION: Record<string, string> = {
  higher_in_failures: "Higher in failures",
  lower_in_failures: "Lower in failures",
  no_difference: "No difference",
  not_tested: "not tested",
};

export const WORK_ORDER_STATUS: Record<string, string> = {
  open: "Open",
  in_progress: "In progress",
  done: "Done",
  cancelled: "Cancelled",
};

export const STEP_NODE: Record<string, string> = {
  triage: "Triage",
  plan: "Plan",
  evidence: "Evidence",
  write: "Write",
  verify: "Verify",
  decision: "Decision",
};

export const STRENGTH: Record<string, string> = {
  strong: "Strong evidence",
  moderate: "Moderate evidence",
  weak: "Weak evidence",
};

export const CLAIM_VERDICT: Record<string, string> = {
  supported: "Supported",
  partially_supported: "Partly supported",
  unsupported: "Not supported",
  not_checked: "Not checked",
};

export const ISSUE_CODE: Record<string, string> = {
  schema: "Report format",
  number_not_listed: "Number not listed",
  number_mismatch: "Number does not match its evidence",
  unknown_evidence: "Unknown evidence",
  missing_citation: "Missing citation",
  causal_wording: "Causal wording",
  unsupported_claim: "Unsupported claim",
  verifier_unavailable: "Verifier unavailable",
};

export const TRIGGER_KIND: Record<string, string> = {
  run_alarm: "Run alarm",
  alarm: "Alarm",
  unit: "Unit",
  wafer: "Wafer",
  lot: "Lot",
};

export const WORK_ORDER_FLOW = ["open", "in_progress", "done"] as const;

export const AUDIT_ACTION: Record<string, string> = {
  "session.guest": "Started an engineer trial",
  "session.login": "Signed in",
  "session.login_failed": "Failed sign-in",
  "session.logout": "Signed out",
  "session.revoked": "Ended a device session",
  "workspace.handoff_created": "Made a code for another device",
  "workspace.joined": "Joined a workspace from another device",
  "workspace.fresh": "Started a fresh workspace",
  "investigation.created": "Started an investigation",
  "investigation.approved": "Approved a report",
  "investigation.rejected": "Rejected a report",
  "investigation.stopped": "Stopped an investigation",
  "work_order.created": "Opened a work order",
  "work_order.updated": "Updated a work order",
  "role.updated": "Changed a model role",
};

/** The stages of a run, as the Line page names them. */
export const RUN_STAGE: Record<string, string> = {
  intake: "Intake",
  sensor_risk: "Failure risk",
  control_charts: "Control charts",
  drift_health: "Drift and sensor health",
  wafer_pattern: "Wafer patterns",
  wafer_similar: "Similar wafers",
  lot: "Lots",
  final_test: "Actual outcome",
};

export const STAGE_STATUS: Record<string, string> = {
  pending: "Waiting",
  running: "Computing",
  done: "Done",
  skipped: "No data for it",
  failed: "Failed",
};

export const RUN_STATUS: Record<string, string> = {
  queued: "Waiting to start",
  running: "Computing",
  done: "Done",
  failed: "Stopped",
};

export const ACTOR_ROLE: Record<string, string> = {
  system: "System",
  visitor: "Visitor",
  engineer: "Engineer",
  admin: "Admin",
};
