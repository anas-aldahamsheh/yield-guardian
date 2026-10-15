"use client";

import type { Investigation, RunAlarm, RunCreate, RunCreated } from "@yield-guardian/contracts";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import { LocalDateTime } from "@/components/local-date-time";
import { usePrefersReducedMotion } from "@/components/motion";
import { ApiError, describeError } from "@/lib/api/errors";
import { withRetry } from "@/lib/api/retry";
import { useSession } from "@/lib/api/session";
import { plural } from "@/lib/format";
import { useAfterLoad } from "@/lib/idle";
import { createRun } from "@/lib/live/api";
import { DRAFT_KEYS, readDraft, writeDraft } from "@/lib/live/drafts";
import { originRule } from "@/lib/live/origin";
import { isFinished, stageResult, type RunState, type StageId } from "@/lib/live/run-state";
import {
  READING_SENTENCE,
  STATION_NAME,
  STATION_STAGES,
  lineStatus,
  needsSentence,
  readingLine,
  summarizeLine,
  turnsRed,
  type StationSummary,
  type StationTone,
} from "@/lib/live/stations";
import type { StoredRun } from "@/lib/live/stored-run";
import {
  lineQuery,
  parseLineUrl,
  parsePick,
  stationAt,
  type Focus,
  type LineUrlState,
} from "@/lib/live/url-state";
import { useRun, type RunConnection, type RunProblem } from "@/lib/live/use-run";
import { cn } from "@/lib/utils";

import { AlarmsRail } from "./alarms-rail";
import { Bay, type ClockStation } from "./bay";
import { InputBar, type Way } from "./input-bar";
import { LaterStations } from "./later-stations";
import { useScene } from "./scene";
import { StationDrawer } from "./station-drawer";
import { useLineScene } from "./use-line-scene";
import { useStationClocks } from "./use-station-clocks";

let webgl: boolean | undefined;
/** WebGL 2, probed once per page; the probe's context is released at once. */
function webgl2(): boolean {
  if (webgl !== undefined) return webgl;
  try {
    const gl = document.createElement("canvas").getContext("webgl2");
    webgl = Boolean(gl);
    gl?.getExtension("WEBGL_lose_context")?.loseContext();
  } catch {
    webgl = false;
  }
  return webgl;
}
const noSubscribe = () => () => {};

function focusKey(focus: Focus): string {
  if (!focus) return "";
  return focus.kind === "lot" ? `lot:${focus.name}` : `${focus.kind}:${focus.index}`;
}

function focusOf(key: string): Focus {
  if (!key) return null;
  const colon = key.indexOf(":");
  const kind = key.slice(0, colon);
  const value = key.slice(colon + 1);
  if (kind === "lot") return { kind: "lot", name: value };
  return { kind: kind as "unit" | "wafer", index: Number(value) };
}

/** Final test while the run's stored state is read. */
const READING_FINAL_TEST: { tone: StationTone; sentence: string } = {
  tone: "idle",
  sentence: READING_SENTENCE,
};

/** Final test is drawn by its stamp, at the end of both tracks. */
function finalTestSummary(
  state: RunState | null,
  revealed: ReadonlySet<StageId>,
): { tone: StationTone; sentence: string } {
  if (!state)
    return {
      tone: "idle",
      sentence:
        "Checks the warnings against recorded final-test results and wafer labels, when the input has them.",
    };
  const stage = state.stages.final_test;
  if (stage.status === "skipped")
    return {
      tone: "needs",
      sentence: needsSentence(stage.needs, "needs recorded final-test results or wafer labels"),
    };
  if (stage.status === "failed")
    return {
      tone: "failed",
      sentence: stage.problem?.detail ?? stage.problem?.title ?? "Final test stopped.",
    };
  const result = revealed.has("final_test") ? stageResult(state, "final_test") : null;
  if (result) return { tone: "ok", sentence: result.summary };
  if (state.status === "failed")
    return { tone: "failed", sentence: "The run stopped before final test." };
  return {
    tone: "working",
    sentence:
      stage.status === "done"
        ? "Computed; stamped when both tracks have reached it."
        : "Waiting for both tracks.",
  };
}

/**
 * The Line page: choose an input, and watch each station compute its result from it. The URL
 * holds the run, the open station, the unit, wafer or lot in view and the chosen alarm, so a
 * reload or a link opens the same view; `?pick=` from an old unit, wafer or lot link starts a
 * run of that item. `stored` is the run's state as the server read it to render the page, so a
 * reload shows every result at once, as it stands, with nothing replayed.
 */
export function LinePage({
  initialQuery,
  stored = null,
}: {
  initialQuery: string;
  stored?: StoredRun | null;
}) {
  const [url, setUrl] = useState<LineUrlState>(() =>
    parseLineUrl(new URLSearchParams(initialQuery)),
  );
  /** The run this page has just started: its results arrive on the stream and play as they come. */
  const [freshId, setFreshId] = useState<string | null>(null);
  /**
   * Where the open station comes from: the page's own address, an address reached with back or
   * forward, or the person choosing it here (only then does its drawer fade in and scroll).
   */
  const [stationBy, setStationBy] = useState<"document" | "url" | "person">("document");
  const { way, kept: wayKept, setWay } = useWay();
  const [starting, setStarting] = useState(
    () => parsePick(new URLSearchParams(initialQuery)) != null,
  );
  const [waking, setWaking] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const { csrf } = useSession();
  const reducedMotion = usePrefersReducedMotion();
  const idle = useAfterLoad();
  const gl = useSyncExternalStore(noSubscribe, webgl2, () => false);
  const use3d = idle && gl && !reducedMotion;
  const bayRef = useRef<HTMLDivElement>(null);
  const picked = useRef(false);

  const go = useCallback((next: LineUrlState, mode: "push" | "replace") => {
    setUrl(next);
    // A run left is no longer fresh: coming back to it shows it as it stands.
    setFreshId((id) => (id === next.runId ? id : null));
    const query = lineQuery(next);
    const href = query ? `/?${query}` : "/";
    if (mode === "push") window.history.pushState(null, "", href);
    else window.history.replaceState(null, "", href);
  }, []);

  useEffect(() => {
    const onPop = () => {
      const next = parseLineUrl(new URLSearchParams(window.location.search));
      setUrl(next);
      setFreshId((id) => (id === next.runId ? id : null));
      // Back and forward restore the view where it was: the browser keeps the scroll position.
      setStationBy("url");
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const created = useCallback(
    (run: RunCreated, mode: "push" | "replace") => {
      setFreshId(run.run_id);
      setStationBy("person");
      setWay(null);
      setStarting(false);
      setWaking(false);
      // A station asked for before there was a run (an old station link) opens on the new run.
      go(
        { runId: run.run_id, station: url.runId ? null : url.station, focus: null, alarm: null },
        mode,
      );
      bayRef.current?.scrollIntoView({
        block: "start",
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
      });
    },
    [go, setWay, url.runId, url.station],
  );
  const refused = useCallback((error: unknown) => {
    const copy = describeError(error);
    setStartError(`${copy.title}. ${copy.detail}`);
    setStarting(false);
    setWaking(false);
  }, []);

  /** POST /runs; while the API wakes (503), the page says so and asks again. */
  const begin = useCallback(
    (body: RunCreate) =>
      withRetry(() => createRun(body, csrf), {
        retryIf: (error) => error instanceof ApiError && error.status === 503,
        onWaiting: () => setWaking(true),
      }),
    [csrf],
  );

  const start = useCallback(
    async (body: RunCreate) => {
      setStarting(true);
      setStartError(null);
      await begin(body).then((run) => created(run, "push"), refused);
    },
    [begin, created, refused],
  );

  // An old link to a unit, wafer or lot page arrives as ?pick= and runs that item.
  useEffect(() => {
    if (picked.current) return;
    picked.current = true;
    const pick = parsePick(new URLSearchParams(initialQuery));
    if (pick) void begin(pick).then((run) => created(run, "replace"), refused);
  }, [initialQuery, begin, created, refused]);

  const run = useRun(url.runId, { fresh: url.runId != null && url.runId === freshId, stored });
  const key = focusKey(url.focus);
  const focus = useMemo(() => focusOf(key), [key]);
  // Reading the run's stored state (it was not in the page): nothing of it is shown until it is in.
  const reading = run.connection === "loading" || run.connection === "waking";
  const state = run.problem || reading ? null : run.state;
  const { store, finish } = useLineScene(state, focus, reducedMotion);
  const revealed = useScene(store, (s) => s.revealed);
  const alarmsShown = useScene(store, (s) => s.alarms);
  const playing = useScene(store, (s) => s.playing);

  const summaries = useMemo(
    () =>
      reading
        ? readingLine()
        : summarizeLine(state, {
            shown: (s) => revealed.has(s),
            alarmShown: (a) => alarmsShown.has(a.alarm_id),
          }),
    [reading, state, revealed, alarmsShown],
  );
  const finalTest = useMemo(
    () => (reading ? READING_FINAL_TEST : finalTestSummary(state, revealed)),
    [reading, state, revealed],
  );
  // Over when the run has ended and the line has played every result: nothing more will arrive.
  const over = state != null && isFinished(state) && !playing && finalTest.tone !== "working";
  const tones = useMemo(
    () =>
      ({
        manufacturing: summaries[0]!.tone,
        monitoring: summaries[1]!.tone,
        wafer_test: summaries[2]!.tone,
        final_test: finalTest.tone,
      }) satisfies Record<ClockStation, StationTone>,
    [summaries, finalTest],
  );
  const clocks = useStationClocks(state, tones);

  const setStation = (n: number | null) => {
    if (!url.runId) return;
    setStationBy("person");
    go({ ...url, station: n }, "replace");
  };
  const setFocus = (next: Focus) => {
    if (!url.runId) return;
    // Another unit, wafer or lot is no longer the chosen alarm's.
    go({ ...url, focus: next, alarm: null }, "replace");
  };
  const showAlarm = (alarm: RunAlarm) => {
    if (!url.runId) return;
    const station = STATION_STAGES.monitoring.includes(alarm.stage)
      ? 2
      : STATION_STAGES.wafer_test.includes(alarm.stage)
        ? 3
        : 1;
    const next: Focus =
      alarm.unit_index != null
        ? { kind: "unit", index: alarm.unit_index }
        : alarm.wafer_index != null
          ? { kind: "wafer", index: alarm.wafer_index }
          : alarm.lot
            ? { kind: "lot", name: alarm.lot }
            : null;
    setStationBy("person");
    go({ ...url, station, focus: next, alarm: alarm.alarm_id }, "replace");
  };
  // The server keeps the link too (the investigation's trigger names the alarm), so a reload or
  // another device shows it; the URL keeps the alarm it was started from.
  const linked = (alarmId: string, investigation: Investigation) => {
    run.linkInvestigation(alarmId, investigation.investigation_id, investigation.status);
    if (url.runId) go({ ...url, alarm: alarmId }, "replace");
  };
  const newRun = () => {
    go({ runId: null, station: null, focus: null, alarm: null }, "push");
    document.getElementById("line-title")?.scrollIntoView({ block: "start" });
  };

  const drawer =
    url.station != null && url.station <= 3 && state ? (url.station as 1 | 2 | 3) : null;
  const twoSources = Boolean(
    state &&
    ((revealed.has("intake") && stageResult(state, "intake")?.two_sources) ||
      (state.origin?.datasets.includes("secom") && state.origin.datasets.includes("wm811k"))),
  );

  return (
    <div>
      <section data-theme="dark" aria-labelledby="line-title" className="bg-room text-ink">
        <div className="mx-auto w-full max-w-[1600px] px-gutter pt-8 pb-8 sm:pt-10">
          <div className="mb-6 max-w-[64ch]">
            <h1
              id="line-title"
              className="text-[30px] leading-9 font-medium tracking-[-0.03em] sm:text-[40px] sm:leading-[46px]"
            >
              Run real fab data down the line
            </h1>
            <p className="mt-3 text-[16px] leading-6 text-ink-2">
              Choose an input. Each station computes its result from it while you watch, and the
              line moves only as results arrive. Nothing here is a recording.
            </p>
          </div>
          <InputBar
            open={way}
            kept={wayKept}
            onOpen={setWay}
            onStart={start}
            starting={starting}
            error={startError}
            waitingFor={
              !url.runId && url.station != null ? STATION_NAME[stationAt(url.station)!] : null
            }
          />

          <div ref={bayRef} className="scroll-mt-[calc(var(--bar-height)+12px)]">
            {run.problem ? (
              <RunProblemNotice problem={run.problem} onNew={newRun} />
            ) : reading ? (
              <ReadingStrip waking={run.connection === "waking"} />
            ) : state ? (
              <RunStrip
                state={state}
                connection={run.connection}
                playing={playing}
                onFinish={finish}
                onRepeat={start}
              />
            ) : waking && starting ? (
              <WakingNote />
            ) : null}
            {twoSources ? <TwoSources /> : null}
            <div className="mt-4 grid grid-cols-[minmax(0,1fr)] gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(280px,320px)]">
              <div className="min-w-0">
                <Bay
                  state={state}
                  store={store}
                  summaries={summaries}
                  finalTest={finalTest}
                  clocks={clocks}
                  use3d={use3d}
                  onOpen={(n) => setStation(url.station === n ? null : n)}
                  openStation={url.station}
                />
                {state ? <LineStatus state={state} over={over} /> : null}
              </div>
              <div className="relative">
                <AlarmsRail
                  state={state}
                  reading={reading}
                  shown={alarmsShown}
                  onShow={showAlarm}
                  onLinked={linked}
                  selected={url.alarm}
                  over={over}
                  // Under the line the rail scrolls within a screen's height less the bar above and the
                  // Ask button's band below, so in view it clears both; beside the line it takes the
                  // line's height, down to the Ask button's band wherever the page is scrolled.
                  className="max-h-[min(640px,calc(100dvh-var(--bar-height)-112px))] min-h-[200px] rounded-[2px] bg-die xl:absolute xl:inset-x-0 xl:top-0 xl:h-[min(100%,max(240px,var(--viewport-room,100%)))] xl:max-h-none xl:min-h-0"
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="mx-auto w-full max-w-[1600px] px-gutter pb-16">
        {drawer && state ? (
          <StationDrawer
            station={drawer}
            state={state}
            revealed={revealed}
            focus={focus}
            onFocus={setFocus}
            onClose={() => setStation(null)}
            // A drawer open in the URL (a reload, a link, back and forward) is already where the
            // person left it: it neither fades in nor moves the page.
            restored={stationBy !== "person"}
            landing={stationBy === "document"}
          />
        ) : null}
        {state ? (
          <LaterStations
            state={state}
            focused={url.station === 4 || url.station === 5 ? url.station : null}
          />
        ) : null}
      </div>

      <Announcer
        state={state}
        summaries={summaries}
        finalTest={finalTest}
        alarms={alarmsShown}
        over={over}
      />
    </div>
  );
}

/**
 * The open way in (a panel of the input bar), kept for this tab with its draft (an unsent
 * drawing, a checked upload: lib/live/drafts.ts), so a reload keeps it open as it was. A panel
 * closed, or run, takes its draft with it, as it does without a reload.
 */
function useWay(): { way: Way | null; kept: boolean; setWay: (way: Way | null) => void } {
  // After hydration: the server renders the bar closed, and so does the first browser render.
  const keptWay = useSyncExternalStore(noSubscribe, keptWayIn, () => null);
  const [chosen, setChosen] = useState<{ way: Way | null } | null>(null);
  const setWay = useCallback((next: Way | null) => {
    setChosen({ way: next });
    writeDraft(DRAFT_KEYS.way, next);
    if (next !== "draw") writeDraft(DRAFT_KEYS.drawing, null);
    if (next !== "upload") writeDraft(DRAFT_KEYS.upload, null);
  }, []);
  return chosen
    ? { way: chosen.way, kept: false, setWay }
    : { way: keptWay, kept: keptWay != null, setWay };
}

function keptWayIn(): Way | null {
  const kept = readDraft(DRAFT_KEYS.way);
  return kept === "case" || kept === "draw" || kept === "upload" ? kept : null;
}

/**
 * What the strip says about the connection. Nothing while the run is shown as it stands: a run
 * known up to an event (a reload, a link) is shown at once, and following it on is silent.
 */
function connectionNote(connection: RunConnection, state: RunState): string | null {
  switch (connection) {
    case "connecting":
      return state.contiguousSeq == null ? "Connecting to the run" : null;
    case "reconnecting":
      return "The connection dropped; reconnecting, results so far are kept";
    default:
      return null;
  }
}

/** The stored run is being read (it was too large to come with the page, or the API is waking). */
function ReadingStrip({ waking }: { waking: boolean }) {
  return (
    <div className="mt-6 border-t border-hairline pt-4">
      <h2 className="text-[17px] leading-6 font-semibold text-ink">Reading the run</h2>
      <p className="mt-1 text-[12px] leading-4 text-ink-3" aria-live="polite">
        {waking
          ? "The service is starting after a quiet spell; the run shows as soon as it answers."
          : "Its results show as they stand once they are in."}
      </p>
    </div>
  );
}

/** A run was asked for while the API wakes: it starts as soon as the API answers. */
function WakingNote() {
  return (
    <p
      className="mt-6 border-t border-hairline pt-4 text-[13px] leading-5 text-ink-2"
      role="status"
    >
      The service is starting after a quiet spell; the run starts as soon as it answers.
    </p>
  );
}

function RunStrip({
  state,
  connection,
  playing,
  onFinish,
  onRepeat,
}: {
  state: RunState;
  connection: RunConnection;
  playing: boolean;
  onFinish: () => void;
  onRepeat: (body: RunCreate) => Promise<void>;
}) {
  const origin = state.origin;
  const rule = origin ? originRule(origin.rule, origin.seed) : null;
  const note = connectionNote(connection, state);
  return (
    <div className="mt-6 flex flex-col gap-3 border-t border-hairline pt-4 lg:flex-row lg:items-start lg:justify-between">
      <div className="max-w-[96ch] min-w-0">
        <h2 className="text-[17px] leading-6 font-semibold text-ink">
          {origin?.title ?? "Starting the run"}
        </h2>
        {rule ? (
          <p className="mt-0.5 text-[13px] leading-5 text-ink-2">
            {rule.rule}
            {rule.seed ? <span className="tnum text-ink-3">{` ${rule.seed}`}</span> : null}
          </p>
        ) : null}
        <p className="mt-1 text-[12px] leading-4 text-ink-3">
          {state.expiresAt === null ? (
            "Kept while an investigation uses it."
          ) : state.expiresAt ? (
            <>
              {"Kept until "}
              <LocalDateTime iso={state.expiresAt} />
              {", then deleted."}
            </>
          ) : null}
          {note ? (
            <span className={cn(state.expiresAt !== undefined && "ml-2")}>{`${note}.`}</span>
          ) : null}
        </p>
      </div>
      <div className="flex shrink-0 flex-wrap gap-2">
        {playing ? (
          <button
            type="button"
            onClick={onFinish}
            className="rounded-[4px] border border-hairline-strong px-3 py-1.5 text-[13px] leading-5 text-ink hover:bg-die-2"
          >
            Show every result now
          </button>
        ) : null}
        {origin?.source === "sample" && origin.seed != null && isFinished(state) ? (
          <button
            type="button"
            onClick={() => void onRepeat({ source: "sample", seed: origin.seed })}
            className="rounded-[4px] border border-hairline-strong px-3 py-1.5 text-[13px] leading-5 text-ink hover:bg-die-2"
          >
            Run the same sample again
          </button>
        ) : null}
      </div>
    </div>
  );
}

function RunProblemNotice({ problem, onNew }: { problem: RunProblem; onNew: () => void }) {
  return (
    <div
      role="alert"
      className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-[2px] border border-hairline-strong bg-die px-4 py-3"
    >
      <p className="text-[15px] leading-6 text-ink">{problem.message}</p>
      {problem.kind === "other" ? (
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="rounded-[4px] bg-ink px-3 py-1.5 text-[14px] font-medium text-room hover:bg-ink/90"
        >
          Reload
        </button>
      ) : (
        <button
          type="button"
          onClick={onNew}
          className="rounded-[4px] bg-ink px-3 py-1.5 text-[14px] font-medium text-room hover:bg-ink/90"
        >
          Start a new one
        </button>
      )}
    </div>
  );
}

/** Both tracks in one run: say that they are separate real datasets, never one chip. */
function TwoSources() {
  return (
    <p className="mt-3 max-w-[96ch] border-l-2 border-safelight-lamp pl-3 text-[14px] leading-5 text-ink-2">
      <span className="font-medium text-ink">Two separate datasets. </span>
      The sensor units are SECOM and the wafer maps are WM-811K: they come from different fabs, so
      no wafer here belongs to any unit. The two tracks run side by side and are never joined.
    </p>
  );
}

/**
 * Results announced as the line shows them: each station's sentence once it is settled, and the
 * end of the run. A polite live region reads out only what is added or changed.
 */
function LineStatus({ state, over }: { state: RunState; over: boolean }) {
  return (
    <p className={cn("mt-3 text-[13px] leading-5", over ? "text-ink-2" : "text-ink-3")}>
      <span
        aria-hidden="true"
        className={cn(
          "mr-2 inline-block size-1.5 rounded-full align-middle",
          over ? "bg-ink-2" : "bg-safelight-lamp",
        )}
      />
      {lineStatus(state, over)}
    </p>
  );
}

function Announcer({
  state,
  summaries,
  finalTest,
  alarms,
  over,
}: {
  state: RunState | null;
  summaries: StationSummary[];
  finalTest: { tone: StationTone; sentence: string };
  alarms: ReadonlySet<string>;
  over: boolean;
}) {
  if (!state) return <div aria-live="polite" className="sr-only" />;
  const settled = summaries.filter(
    (s) => s.tone === "ok" || s.tone === "alarm" || s.tone === "needs" || s.tone === "failed",
  );
  const shown = state.alarms.filter((a) => alarms.has(a.alarm_id));
  const red = shown.filter(turnsRed).length;
  const count = shown.length
    ? `${red ? plural(red, "alarm") : "no alarm"} and ${plural(shown.length - red, "warning")}`
    : "no alarm";
  return (
    <div aria-live="polite" className="sr-only">
      {settled.map((s) => (
        <p key={s.station}>{`${s.name}${s.tone === "alarm" ? ", alarm" : ""}: ${s.sentence}`}</p>
      ))}
      {finalTest.tone === "ok" || finalTest.tone === "needs" ? (
        <p>{`Final test: ${finalTest.sentence}`}</p>
      ) : null}
      {over ? (
        <p>
          {state.status === "failed"
            ? lineStatus(state, over)
            : `The run is finished: ${count}. Nothing more will arrive.`}
        </p>
      ) : null}
    </div>
  );
}
