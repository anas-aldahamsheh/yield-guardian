import type {
  ControlChartsResult,
  DriftHealthResult,
  FinalTestResult,
  IntakeResult,
  LotResult,
  Problem,
  Run,
  RunAlarm,
  RunEvent,
  RunOrigin,
  SensorRiskResult,
  StageState,
  WaferPatternResult,
  WaferSimilarResult,
} from "@yield-guardian/contracts";

/**
 * The state of one live run, built from its events (SSE) and, after a reload, from GET /runs/{id}.
 *
 * Pure and order-tolerant: the same events in any order, delivered any number of times, give the
 * same state. Statuses only move forward (pending, then running, then done, skipped or failed),
 * so a snapshot followed by a replay of the stream from its start cannot undo a result.
 * Duplicates are recognised by `seq`; alarms by `alarm_id`. A snapshot says which events it
 * includes (`last_seq`), so the stream is followed from right after it and nothing is replayed.
 */

export type StageId = StageState["stage"];
export type StationId = StageState["station"];
export type StageStatus = StageState["status"];

/** Stage results by stage, as the contract discriminates them. */
export interface StageResults {
  intake: IntakeResult;
  sensor_risk: SensorRiskResult;
  control_charts: ControlChartsResult;
  drift_health: DriftHealthResult;
  wafer_pattern: WaferPatternResult;
  wafer_similar: WaferSimilarResult;
  lot: LotResult;
  final_test: FinalTestResult;
}

export const STAGES = [
  "intake",
  "sensor_risk",
  "control_charts",
  "drift_health",
  "wafer_pattern",
  "wafer_similar",
  "lot",
  "final_test",
] as const satisfies readonly StageId[];

/** The station that draws each stage (contracts/runs.py STAGE_STATION). */
export const STAGE_STATION: Record<StageId, StationId> = {
  intake: "manufacturing",
  sensor_risk: "monitoring",
  control_charts: "monitoring",
  drift_health: "monitoring",
  wafer_pattern: "wafer_test",
  wafer_similar: "wafer_test",
  lot: "wafer_test",
  final_test: "monitoring",
};

export interface StageView<S extends StageId = StageId> {
  stage: S;
  station: StationId;
  status: StageStatus;
  needs: string | null;
  result: StageResults[S] | null;
  problem: Problem | null;
  /** Server compute time, once the result has arrived. */
  elapsedMs: number | null;
  /** Server time the stage started (ISO), from its stage_started event or the snapshot. */
  startedAt: string | null;
}

export type Stages = { [S in StageId]: StageView<S> };

/** Something the line can show, in the order it reached the browser. */
export type Arrival =
  | { kind: "result"; stage: StageId; seq: number }
  | { kind: "skipped"; stage: StageId; seq: number }
  | { kind: "failed"; stage: StageId; seq: number }
  | { kind: "alarm"; alarmId: string; seq: number }
  | { kind: "done"; seq: number };

export interface RunState {
  runId: string;
  origin: RunOrigin | null;
  /** "connecting" until the run's first event or snapshot is known. */
  status: Run["status"] | "connecting";
  stages: Stages;
  /** In the order raised (RA-1, RA-2, ...). */
  alarms: RunAlarm[];
  /** Alarms the server's per-run cap left out. */
  alarmsNotListed: number;
  units: number | null;
  wafers: number | null;
  /**
   * When the server deletes the run (ISO); null while an investigation uses it, so it is kept;
   * undefined until GET /runs/{id} has answered.
   */
  expiresAt: string | null | undefined;
  /** Every seq applied, so a repeat is ignored. */
  seen: ReadonlySet<number>;
  /** Seq of run_started: the first event of the stream. */
  firstSeq: number | null;
  /**
   * Highest seq up to which every event has been applied, from the stream or a snapshot (null
   * until the first): the stream resumes after it.
   */
  contiguousSeq: number | null;
  /** Server time of the newest snapshot applied (ISO), null before one. */
  readAt: string | null;
  /** New things to show, in arrival order (the animation consumes this). */
  arrivals: Arrival[];
}

const RANK: Record<StageStatus, number> = {
  pending: 0,
  running: 1,
  done: 2,
  skipped: 2,
  failed: 2,
};

function emptyStage<S extends StageId>(stage: S): StageView<S> {
  return {
    stage,
    station: STAGE_STATION[stage],
    status: "pending",
    needs: null,
    result: null,
    problem: null,
    elapsedMs: null,
    startedAt: null,
  };
}

function emptyStages(): Stages {
  const stages = {} as Record<StageId, StageView>;
  for (const stage of STAGES) stages[stage] = emptyStage(stage);
  return stages as Stages;
}

export function emptyRunState(runId: string): RunState {
  return {
    runId,
    origin: null,
    status: "connecting",
    stages: emptyStages(),
    alarms: [],
    alarmsNotListed: 0,
    units: null,
    wafers: null,
    expiresAt: undefined,
    seen: new Set(),
    firstSeq: null,
    contiguousSeq: null,
    readAt: null,
    arrivals: [],
  };
}

/** A stage moves forward only: a later, lower-ranked update (a replayed start) is ignored. */
function advance<S extends StageId>(
  current: StageView<S>,
  next: Partial<StageView<S>> & { status: StageStatus },
): StageView<S> | null {
  if (RANK[next.status] < RANK[current.status]) return null;
  // Two final statuses: keep the first (a result is never replaced by a replay of itself).
  if (RANK[current.status] === 2 && RANK[next.status] === 2) return null;
  return { ...current, ...next };
}

function withStage<S extends StageId>(
  state: RunState,
  stage: S,
  view: StageView<S> | null,
): RunState {
  if (!view) return state;
  return { ...state, stages: { ...state.stages, [stage]: view } };
}

function alarmNumber(alarmId: string): number {
  return Number.parseInt(alarmId.replace(/^RA-/, ""), 10);
}

function addAlarm(state: RunState, alarm: RunAlarm): { state: RunState; added: boolean } {
  const existing = state.alarms.findIndex((a) => a.alarm_id === alarm.alarm_id);
  if (existing !== -1) {
    // The same alarm again (snapshot then stream): keep any investigation link either carries,
    // the newer one (with its status) when both do.
    const before = state.alarms[existing]!;
    const merged: RunAlarm = { ...before, ...alarm };
    if (alarm.investigation_id != null) {
      merged.investigation_status = alarm.investigation_status ?? null;
    } else {
      merged.investigation_id = before.investigation_id ?? null;
      if (before.investigation_status != null)
        merged.investigation_status = before.investigation_status;
    }
    if (JSON.stringify(merged) === JSON.stringify(before)) return { state, added: false };
    const alarms = state.alarms.slice();
    alarms[existing] = merged;
    return { state: { ...state, alarms }, added: false };
  }
  const alarms = [...state.alarms, alarm].sort(
    (a, b) => alarmNumber(a.alarm_id) - alarmNumber(b.alarm_id),
  );
  return { state: { ...state, alarms }, added: true };
}

function contiguous(
  seen: ReadonlySet<number>,
  firstSeq: number | null,
  from: number | null,
): number | null {
  if (firstSeq == null) return null;
  let at = from ?? firstSeq - 1;
  while (seen.has(at + 1)) at += 1;
  return at >= firstSeq ? at : null;
}

/** Applies one event. Returns the same object when the event changes nothing. */
export function applyRunEvent(state: RunState, event: RunEvent): RunState {
  // Already applied, or included in a snapshot that was.
  if (state.seen.has(event.seq)) return state;
  if (state.contiguousSeq != null && event.seq <= state.contiguousSeq) return state;
  const seen = new Set(state.seen);
  seen.add(event.seq);
  const firstSeq = event.type === "run_started" ? event.seq : state.firstSeq;
  let next: RunState = {
    ...state,
    seen,
    firstSeq,
    contiguousSeq: contiguous(
      seen,
      firstSeq,
      firstSeq === state.firstSeq ? state.contiguousSeq : null,
    ),
  };
  const arrive = (arrival: Arrival) => {
    next = { ...next, arrivals: [...next.arrivals, arrival] };
  };

  switch (event.type) {
    case "run_started": {
      next = {
        ...next,
        origin: event.origin,
        status: next.status === "connecting" || next.status === "queued" ? "running" : next.status,
      };
      for (const stage of event.stages) next = mergeStageState(next, stage);
      return next;
    }
    case "stage_started": {
      const current = next.stages[event.stage];
      // A start that arrives after its result still records when the stage began.
      const view =
        advance(current, { status: "running", startedAt: event.at }) ??
        (current.startedAt == null ? { ...current, startedAt: event.at } : null);
      return withStage(next, event.stage, view);
    }
    case "stage_result": {
      const stage = event.stage;
      const view = advance(next.stages[stage], {
        status: "done",
        result: event.result as StageResults[typeof stage],
        elapsedMs: event.elapsed_ms,
      });
      if (!view) return next;
      next = withStage(next, stage, view);
      arrive({ kind: "result", stage, seq: event.seq });
      return next;
    }
    case "stage_skipped": {
      const view = advance(next.stages[event.stage], { status: "skipped", needs: event.needs });
      if (!view) return next;
      next = withStage(next, event.stage, view);
      arrive({ kind: "skipped", stage: event.stage, seq: event.seq });
      return next;
    }
    case "stage_failed": {
      const view = advance(next.stages[event.stage], { status: "failed", problem: event.problem });
      if (!view) return next;
      next = withStage(next, event.stage, view);
      arrive({ kind: "failed", stage: event.stage, seq: event.seq });
      return next;
    }
    case "alarm": {
      const added = addAlarm(next, event.alarm);
      next = added.state;
      if (added.added) arrive({ kind: "alarm", alarmId: event.alarm.alarm_id, seq: event.seq });
      return next;
    }
    case "run_done": {
      if (next.status === "done" || next.status === "failed") return next;
      next = { ...next, status: event.status, alarmsNotListed: event.alarms_not_listed ?? 0 };
      arrive({ kind: "done", seq: event.seq });
      return next;
    }
  }
}

function mergeStageState(state: RunState, stage: StageState): RunState {
  const current = state.stages[stage.stage];
  const startedAt = current.startedAt ?? stage.started_at ?? null;
  const view =
    advance(current, {
      status: stage.status,
      needs: stage.needs ?? current.needs,
      result: (stage.result ?? current.result) as never,
      problem: stage.problem ?? current.problem,
      elapsedMs: stage.elapsed_ms ?? current.elapsedMs,
      startedAt,
    }) ?? (startedAt !== current.startedAt ? { ...current, startedAt } : null);
  return withStage(state, stage.stage, view);
}

/**
 * Applies GET /runs/{id}: the full state, after a reload or a lost stream. Stages and alarms
 * already known keep what they have; the snapshot adds the rest. Nothing is queued for the
 * animation: a reloaded run shows its results as they stand. The events the snapshot includes
 * (up to `last_seq`) count as applied, so the stream resumes after them.
 */
export function applyRunSnapshot(state: RunState, run: Run): RunState {
  const included = run.last_seq ?? 0;
  const firstSeq = included > 0 ? (state.firstSeq ?? 1) : state.firstSeq;
  let next: RunState = {
    ...state,
    origin: run.origin,
    units: run.units,
    wafers: run.wafers,
    expiresAt: run.expires_at,
    alarmsNotListed: Math.max(state.alarmsNotListed, run.alarms_not_listed ?? 0),
    status:
      state.status === "done" || state.status === "failed"
        ? state.status
        : run.status === "queued" && state.status !== "connecting"
          ? state.status
          : run.status,
    firstSeq,
    contiguousSeq:
      included > 0
        ? contiguous(state.seen, firstSeq, Math.max(state.contiguousSeq ?? 0, included))
        : state.contiguousSeq,
    readAt: run.read_at ?? state.readAt,
  };
  for (const stage of run.stages) next = mergeStageState(next, stage);
  for (const alarm of run.alarms) next = addAlarm(next, alarm).state;
  return next;
}

/** A run known only from GET /runs/{id} (a reload, a link, another device of the workspace). */
export function runStateFrom(run: Run): RunState {
  return applyRunSnapshot(emptyRunState(run.run_id), run);
}

/** Replays a list of events from an empty state, in the order given. */
export function reduceRunEvents(runId: string, events: readonly RunEvent[]): RunState {
  return events.reduce(applyRunEvent, emptyRunState(runId));
}

/** The run is finished: no more events will come. */
export function isFinished(state: RunState): boolean {
  return state.status === "done" || state.status === "failed";
}

export function stageResult<S extends StageId>(state: RunState, stage: S): StageResults[S] | null {
  return state.stages[stage].result as StageResults[S] | null;
}

/**
 * Records the investigation started from an alarm on this page, until the next snapshot reads it
 * back from the server (which keeps the link: the investigation's trigger names the alarm).
 */
export function linkInvestigation(
  state: RunState,
  alarmId: string,
  investigationId: string,
  status: RunAlarm["investigation_status"] = null,
): RunState {
  const i = state.alarms.findIndex((a) => a.alarm_id === alarmId);
  if (i === -1) return state;
  const before = state.alarms[i]!;
  if (
    before.investigation_id === investigationId &&
    (status == null || before.investigation_status === status)
  )
    return state;
  const alarms = state.alarms.slice();
  alarms[i] = {
    ...before,
    investigation_id: investigationId,
    investigation_status: status ?? before.investigation_status ?? null,
  };
  return { ...state, alarms };
}

/** Stages finished before this page followed the stream (read from a snapshot): shown at once. */
export function knownBefore(state: RunState): Set<StageId> {
  const streamed = new Set(
    state.arrivals.flatMap((a) => (a.kind === "alarm" || a.kind === "done" ? [] : [a.stage])),
  );
  return new Set(
    STAGES.filter((s) => {
      const status = state.stages[s].status;
      return (status === "done" || status === "skipped" || status === "failed") && !streamed.has(s);
    }),
  );
}

/** Whether something reached this page on the stream, so the line shows it arriving. */
export function arrivedLive(
  state: RunState,
  what: { alarmId: string } | { stage: StageId },
): boolean {
  return state.arrivals.some((a) =>
    "alarmId" in what
      ? a.kind === "alarm" && a.alarmId === what.alarmId
      : a.kind !== "alarm" && a.kind !== "done" && a.stage === what.stage,
  );
}
