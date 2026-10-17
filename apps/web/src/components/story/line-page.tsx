"use client";

import { useQueryClient } from "@tanstack/react-query";
import type { Investigation, RunAlarm, RunCreate, RunCreated } from "@yield-guardian/contracts";
import {
  InfoIcon,
  RotateCw,
} from "lucide-react";
import {
  type CSSProperties,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

import Link from "next/link";
import { LocalDateTime } from "@/components/local-date-time";
import { usePrefersReducedMotion } from "@/components/motion";
import { useEntrance } from "@/components/motion/entrance";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { ApiError, describeError } from "@/lib/api/errors";
import { withRetry } from "@/lib/api/retry";
import { useSession } from "@/lib/api/session";
import { plural } from "@/lib/format";
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

import { Bay, type ClockStation } from "./bay";
import { InputBar, type Way } from "./input-bar";
import { LaterStations } from "./later-stations";
import { ResultSection } from "./result-section";
import { useScene } from "./scene";
import { StationDrawer } from "./station-drawer";
import { useLineScene } from "./use-line-scene";
import { useStationClocks } from "./use-station-clocks";

const noSubscribe = () => () => { };

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
  if (result) return { tone: "ok", sentence: `${result.summary} See the result below.` };
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
  const [url, setUrl] = useState<LineUrlState>(() => {
    const parsed = parseLineUrl(new URLSearchParams(initialQuery));
    if (parsed.runId) return { ...parsed, station: null };
    // Restore preserved active run if returning from an investigation or navigation
    const preserved = typeof window !== "undefined" ? readDraft(DRAFT_KEYS.activeRun) : null;
    if (preserved) return { runId: preserved, station: null, focus: null, alarm: null };
    return { ...parsed, station: null };
  });
  // The headline rises when the page opens on the line alone. A page that opens on a run (a
  // reload, a link) arrives at rest: the run is shown as it stands and nothing on it moves.
  const [arrive] = useState(() => url.runId == null);
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
  const queryClient = useQueryClient();
  const reducedMotion = usePrefersReducedMotion();
  const bayRef = useRef<HTMLDivElement>(null);
  const resultRef = useRef<HTMLDivElement>(null);
  const picked = useRef(false);
  /** A run opened from Your work, until it is on the line and has the focus. */
  const arrival = useRef<{ runId: string; to: "run" | "alarms" } | null>(null);

  const go = useCallback((next: LineUrlState, mode: "push" | "replace") => {
    setUrl(next);
    // A run left is no longer fresh: coming back to it shows it as it stands.
    setFreshId((id) => (id === next.runId ? id : null));
    if (next.runId) writeDraft(DRAFT_KEYS.activeRun, next.runId);
    const query = lineQuery(next);
    const href = query ? `/?${query}` : "/";
    if (mode === "push") window.history.pushState(null, "", href);
    else window.history.replaceState(null, "", href);
  }, []);

  useEffect(() => {
    if (url.runId) {
      setWay(null);
      writeDraft(DRAFT_KEYS.way, null);
      writeDraft(DRAFT_KEYS.activeRun, url.runId);
      const query = lineQuery(url);
      if (query && typeof window !== "undefined" && !window.location.search.includes(url.runId)) {
        window.history.replaceState(null, "", `/?${query}`);
      }
    }
  }, [url.runId, setWay]);

  useEffect(() => {
    const onPop = () => {
      const next = parseLineUrl(new URLSearchParams(window.location.search));
      setUrl(next);
      setFreshId((id) => (id === next.runId ? id : null));
      // Back and forward restore the view where it was: the browser keeps the scroll position.
      setStationBy("url");
    };
    const onOpenRun = (event: Event) => {
      const custom = event as CustomEvent<{ view: LineUrlState; to?: "run" | "alarms" }>;
      const view = custom.detail?.view;
      if (!view?.runId) return;
      setWay(null);
      writeDraft(DRAFT_KEYS.way, null);
      bayScroll.current = "smooth";
      setFreshId(null);
      setStationBy("person");
      go(view, "push");
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      window.setTimeout(() => {
        if (custom.detail?.to === "alarms") {
          resultRef.current?.scrollIntoView({ block: "start", behavior: reduce ? "auto" : "smooth" });
        } else {
          bayRef.current?.scrollIntoView({ block: "start", behavior: reduce ? "auto" : "smooth" });
        }
      }, 60);
    };
    window.addEventListener("popstate", onPop);
    window.addEventListener("yg:open-run", onOpenRun);
    return () => {
      window.removeEventListener("popstate", onPop);
      window.removeEventListener("yg:open-run", onOpenRun);
    };
  }, [go, setWay]);

  /** A scroll to the bay asked for when a run comes onto the line, made after it renders. */
  const bayScroll = useRef<"smooth" | "auto" | null>(null);
  useEffect(() => {
    const how = bayScroll.current;
    if (!how || !url.runId) return;
    bayScroll.current = null;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    bayRef.current?.scrollIntoView({ block: "start", behavior: reduce ? "auto" : how });
  }, [url.runId]);

  const created = useCallback(
    (run: RunCreated, mode: "push" | "replace") => {
      setFreshId(run.run_id);
      setStationBy("person");
      setWay(null);
      writeDraft(DRAFT_KEYS.way, null);
      setStarting(false);
      setWaking(false);
      void queryClient.invalidateQueries({ queryKey: ["workspace"] });
      go(
        { runId: run.run_id, station: null, focus: null, alarm: null },
        mode,
      );
      // Scrolled once the run is on the line: Your work then moves below the bay, so a scroll
      // made now would land where Your work comes to be.
      bayScroll.current = "smooth";
    },
    [go, setWay, queryClient],
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

  useEffect(() => {
    if (over) {
      void queryClient.invalidateQueries({ queryKey: ["workspace"] });
    }
  }, [over, queryClient]);

  const setStation = (n: number | null) => {
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
  // A unit in the result opens the Failure risk station on it.
  const showUnit = (index: number) => {
    if (!url.runId) return;
    setStationBy("person");
    go({ ...url, station: 2, focus: { kind: "unit", index }, alarm: null }, "replace");
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
  // The input's size for the run's one-line summary: from the run, or from the intake once the
  // line shows it.
  const intake = state && revealed.has("intake") ? stageResult(state, "intake") : null;
  const size = {
    units: state?.units ?? intake?.units ?? null,
    wafers: state?.wafers ?? intake?.wafers ?? null,
  };
  const twoSources = Boolean(
    state &&
    ((revealed.has("intake") && stageResult(state, "intake")?.two_sources) ||
      (state.origin?.datasets.includes("secom") && state.origin.datasets.includes("wm811k"))),
  );
  // A run opened from Your work takes the focus once it is on the line, so a keyboard user goes
  // on from the run: its heading, the station drawer it was left on (which comes into view by
  // itself, as one chosen here does), its alarms when those were asked for, or what stops it.
  useEffect(() => {
    const next = arrival.current;
    if (!next) return;
    if (next.runId !== url.runId) {
      arrival.current = null;
      return;
    }
    if (reading || (!state && !run.problem)) return;
    arrival.current = null;
    const target = document.getElementById(
      run.problem
        ? "run-problem"
        : next.to === "alarms"
          ? "alarms-title"
          : drawer != null
            ? "station-drawer-title"
            : "run-title",
    );
    if (!target) return;
    if (next.to === "alarms" && !run.problem) target.scrollIntoView({ block: "center" });
    target.focus({ preventScroll: true });
  }, [url.runId, reading, state, run.problem, drawer]);

  return (
    <div>
      <section aria-labelledby="line-title">
        <div className="mx-auto w-full max-w-[1600px] px-gutter pt-10 pb-10 sm:pt-16">
          {/* On a page that opens on the line alone, the headline's lines rise out of their
              masks on the first paint (CSS, before hydration); the space between them keeps the
              heading's name one sentence. */}
          <h1 id="line-title" className="text-hero font-[680] text-ink">
            <span className={arrive ? "hero-line" : "block"} style={{ "--i": 0 } as CSSProperties}>
              <span className="block">Live Semiconductor</span>
            </span>{" "}
            <span className={arrive ? "hero-line" : "block"} style={{ "--i": 1 } as CSSProperties}>
              <span className="block">Production Line</span>
            </span>
          </h1>
          <div className="mt-8 grid grid-cols-[minmax(0,1fr)] gap-x-12 gap-y-7 sm:mt-10 xl:grid-cols-[minmax(0,5fr)_minmax(0,8fr)] xl:items-start">
            <p
              className={cn(
                arrive && "settle-in",
                "max-w-[46ch] text-[17px] leading-7 text-ink-2 sm:text-lede",
              )}
              style={{ "--d": "120ms" } as CSSProperties}
            >
              Stream physical chamber telemetry and optical wafer maps through in-line inspection stations. Detect equipment drift, classify defect morphology, and verify probe test outcomes in real time.
            </p>
            <InputBar
              open={way}
              kept={wayKept}
              arrive={arrive}
              onOpen={setWay}
              onStart={start}
              starting={starting}
              error={startError}
              waitingFor={
                !url.runId && url.station != null ? STATION_NAME[stationAt(url.station)!] : null
              }
            />
          </div>
          {url.runId ? null : (
            <div className="mt-8 flex flex-wrap items-center justify-between gap-3 rounded-[18px] border border-hairline bg-surface-2/40 px-5 py-3 text-[13.5px] text-ink-2 shadow-2xs">
              <span className="flex items-center gap-2.5">
                <span className="size-2 rounded-full bg-signal/60" />
                <span>Revisit previous production runs and ongoing investigations anytime.</span>
              </span>
              <Link
                href="/history"
                className="font-[600] text-ink underline underline-offset-2 hover:text-signal transition-colors"
              >
                Open Workspace History &rarr;
              </Link>
            </div>
          )}

          <div ref={bayRef} className="mt-12 scroll-mt-[calc(var(--bar-height)+16px)] sm:mt-16">
            {run.problem ? (
              <RunProblemNotice problem={run.problem} onNew={newRun} />
            ) : reading ? (
              <ReadingStrip waking={run.connection === "waking"} />
            ) : state ? (
              <RunStrip
                state={state}
                size={size}
                connection={run.connection}
                playing={playing}
                onFinish={finish}
                onRepeat={start}
              />
            ) : waking && starting ? (
              <WakingNote />
            ) : null}
            {state ? (
              <PipelineDataBanner
                twoSources={twoSources}
                hasUnits={Boolean(size.units && size.units > 0)}
                hasWafers={Boolean(size.wafers && size.wafers > 0)}
              />
            ) : null}
            <div className="mt-6 flex flex-col gap-6">
              <div className="w-full min-w-0">
                <Bay
                  state={state}
                  store={store}
                  summaries={summaries}
                  finalTest={finalTest}
                  clocks={clocks}
                  onOpen={(n) => setStation(n)}
                  openStation={url.station}
                  focus={focus}
                  onFocus={setFocus}
                  revealed={revealed}
                />
                {state ? <LineStatus state={state} over={over} /> : null}
              </div>
            </div>
          </div>
          {/* Note: In-depth station inspection is rendered directly inside Bay in Focused Mode,
              keeping the clicked box on the left with its diagnostics under it, and detailed telemetry near it.
              The old bottom StationDrawer is no longer rendered here, preventing downward page scrolling. */}
          {/* The result, under the line: it comes once final test is stamped (or the line is
              over without it), and each part fills as its stage is shown. */}
          {state && (over || revealed.has("final_test")) ? (
            <div ref={resultRef} className="w-full min-w-0">
              <ResultSection
                state={state}
                revealed={revealed}
                alarmsShown={alarmsShown}
                selectedAlarm={url.alarm}
                over={over}
                onLinked={linked}
                onShowUnit={showUnit}
                onShowAlarm={showAlarm}
              />
            </div>
          ) : null}
        </div>
      </section>

      <div className="mx-auto w-full max-w-[1600px] px-gutter pb-20">
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

/** The stored run is being read: the server did not have it in time (the API is waking, or down). */
function ReadingStrip({ waking }: { waking: boolean }) {
  return (
    <div className="border-t border-hairline pt-8">
      <h2 className="text-[26px] leading-8 font-[640] tracking-[-0.02em] text-ink [font-stretch:108%] sm:text-[30px] sm:leading-9">
        Reading the run
      </h2>
      <p
        className="mt-2 flex max-w-[72ch] items-start gap-2.5 text-[15px] leading-6 text-ink-2"
        aria-live="polite"
      >
        <span aria-hidden="true" className="live-dot mt-[9px] size-1.5 shrink-0" />
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
      className="flex max-w-[72ch] items-start gap-2.5 border-t border-hairline pt-8 text-[15px] leading-6 text-ink-2"
      role="status"
    >
      <span aria-hidden="true" className="live-dot mt-[9px] size-1.5 shrink-0" />
      The service is starting after a quiet spell; the run starts as soon as it answers.
    </p>
  );
}

/** The input in one line: how many units and wafer maps, and where they come from. */
function inputLine(
  state: RunState,
  size: { units: number | null; wafers: number | null },
): string | null {
  const origin = state.origin;
  if (!origin) return null;
  const parts: string[] = [];
  if (size.units) {
    parts.push(
      `${plural(size.units, "unit")}${origin.datasets.includes("secom") ? " from SECOM" : ""}`,
    );
  }
  if (size.wafers) {
    parts.push(
      `${plural(size.wafers, "wafer map")}${origin.datasets.includes("wm811k") ? " from WM-811K" : ""}`,
    );
  }
  if (!parts.length) return null;
  return `${parts.join(" and ")}${origin.filename ? ` in ${origin.filename}` : ""}.`;
}

function RunStrip({
  state,
  size,
  connection,
  playing,
  onFinish,
  onRepeat,
}: {
  state: RunState;
  size: { units: number | null; wafers: number | null };
  connection: RunConnection;
  playing: boolean;
  onFinish: () => void;
  onRepeat: (body: RunCreate) => Promise<void>;
}) {
  const origin = state.origin;
  const rule = origin ? originRule(origin.rule, origin.seed) : null;
  const note = connectionNote(connection, state);
  const line = inputLine(state, size);
  const entrance = useEntrance();

  const shortRunId = state.runId ? (state.runId.length > 14 ? `${state.runId.slice(0, 8)}…` : state.runId) : null;
  const countsSummary = [
    size.units ? `${size.units} Units` : null,
    size.wafers ? `${size.wafers} Wafers` : null,
  ].filter(Boolean).join(" & ");

  return (
    <div
      className={cn(
        entrance && "swap-in",
        "flex flex-wrap items-center justify-between gap-3 border-t border-hairline pt-4 pb-1",
      )}
    >
      <div className="flex flex-wrap items-center gap-2.5 min-w-0">
        {/* Minimal compact run status pill */}
        <div className="inline-flex items-center gap-2 rounded-full border border-hairline bg-surface px-3.5 py-1.5 text-[13px] font-[550] text-ink shadow-2xs">
          <span
            aria-hidden="true"
            className={cn(
              "size-2 shrink-0 rounded-full",
              playing ? "bg-signal animate-pulse" : isFinished(state) ? "bg-pass" : "bg-signal",
            )}
          />
          <span className="font-[650] text-ink">
            {playing ? "Live Run" : "Completed Run"}
            {shortRunId ? <span className="font-normal text-ink-3 ml-1.5 tnum">#{shortRunId}</span> : null}
          </span>
          {countsSummary ? (
            <>
              <span className="text-hairline-strong">&bull;</span>
              <span className="text-[12.5px] font-medium text-ink-2 tnum">{countsSummary}</span>
            </>
          ) : null}
        </div>

        {/* Optional Data Source Provenance & Expiration Popover */}
        {rule || state.expiresAt || note || line ? (
          <Popover>
            <PopoverTrigger asChild>
              <button
                type="button"
                aria-label="Input provenance and retention details"
                className="press inline-flex h-8 items-center gap-1.5 rounded-full border border-hairline bg-surface-2/60 px-3 text-[12px] font-[520] text-ink-3 hover:bg-surface-2 hover:text-ink transition-colors cursor-pointer"
              >
                <InfoIcon className="size-3.5" />
                <span>Dataset Info</span>
              </button>
            </PopoverTrigger>
            <PopoverContent align="start" className="w-80 p-4 text-[13px] leading-5 text-ink-2 shadow-float border border-hairline bg-surface">
              <p className="font-[650] text-ink mb-1">
                {origin?.title ?? "Dataset Information"}
              </p>
              {line ? <p className="text-[12.5px] text-ink-2 mb-2">{line}</p> : null}
              {rule ? (
                <div className="rounded-lg bg-surface-2 p-2.5 text-[12px] leading-relaxed text-ink-2 mb-2.5">
                  <span className="font-medium text-ink block mb-0.5">Origin Rule:</span>
                  {rule.rule}
                  {rule.seed ? <span className="tnum text-ink-3 block mt-0.5">{`Seed: ${rule.seed}`}</span> : null}
                </div>
              ) : null}
              <div className="border-t border-hairline pt-2 text-[11.5px] text-ink-3">
                {state.expiresAt === null ? (
                  "Retained while active investigation is open."
                ) : state.expiresAt ? (
                  <>
                    {"Stored until "}
                    <LocalDateTime iso={state.expiresAt} />
                    {", then automatically purged."}
                  </>
                ) : null}
                {note ? <p className="mt-0.5">{`${note}.`}</p> : null}
              </div>
            </PopoverContent>
          </Popover>
        ) : null}
      </div>

      {/* Fast forward or rerun actions */}
      <div className="flex shrink-0 items-center gap-2">
        {playing ? (
          <Button type="button" variant="outline" size="sm" onClick={onFinish} className="h-8 text-[12.5px]">
            Show every result now
          </Button>
        ) : null}
        {origin?.source === "sample" && origin.seed != null && isFinished(state) ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void onRepeat({ source: "sample", seed: origin.seed })}
            className="h-8 gap-1.5 text-[12.5px]"
          >
            <RotateCw className="size-3.5" />
            <span>Run sample again</span>
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function RunProblemNotice({ problem, onNew }: { problem: RunProblem; onNew: () => void }) {
  const entrance = useEntrance();
  return (
    <div
      id="run-problem"
      role="alert"
      tabIndex={-1}
      className={cn(
        entrance && "swap-in",
        "unexposed flex flex-wrap items-center justify-between gap-4 rounded-[20px] bg-surface px-5 py-4 shadow-[inset_0_0_0_1px_var(--hairline-strong)] outline-none",
      )}
    >
      <p className="text-[16px] leading-6 font-[520] text-ink">{problem.message}</p>
      {problem.kind === "other" ? (
        <Button type="button" onClick={() => window.location.reload()}>
          Reload
        </Button>
      ) : (
        <Button type="button" onClick={onNew}>
          Start a new one
        </Button>
      )}
    </div>
  );
}

/** Explains the data streams active in the current run: dual-track benchmark or single stream. */
function PipelineDataBanner({
  twoSources,
  hasUnits,
  hasWafers,
}: {
  twoSources: boolean;
  hasUnits: boolean;
  hasWafers: boolean;
}) {
  if (twoSources) {
    return (
      <div className="relative mt-4 flex items-start gap-3 rounded-[16px] border border-hairline bg-surface-2/60 px-4 py-3 text-[13.5px] leading-[21px] text-ink-2">
        <span
          aria-hidden="true"
          className="film-light absolute top-2 bottom-2 left-0 w-[3px] rounded-full"
        />
        <div>
          <span className="font-[650] text-ink">Concurrent Multi-Track Inspection: </span>
          <span>
            This benchmark run evaluates two complementary fab data streams simultaneously —{" "}
            <strong className="font-semibold text-ink">Chamber Process Telemetry</strong> (590 sensor channels &rarr; Stations 1 &amp; 2)
            and <strong className="font-semibold text-ink">Optical Wafer Defect Maps</strong> (die spatial patterns &rarr; Station 3).
            Each track evaluates independently along the line to catch equipment drift and physical die defects.
          </span>
        </div>
      </div>
    );
  }

  if (hasUnits && !hasWafers) {
    return (
      <div className="relative mt-4 flex items-start gap-3 rounded-[16px] border border-hairline bg-surface-2/60 px-4 py-3 text-[13.5px] leading-[21px] text-ink-2">
        <span
          aria-hidden="true"
          className="bg-signal absolute top-2 bottom-2 left-0 w-[3px] rounded-full"
        />
        <div>
          <span className="font-[650] text-ink">Chamber Process Telemetry Stream: </span>
          <span>
            Monitoring 590 sensor channels across Stations 1 &amp; 2. Optical wafer defect inspection (Station 3) is bypassed for this dataset.
          </span>
        </div>
      </div>
    );
  }

  if (!hasUnits && hasWafers) {
    return (
      <div className="relative mt-4 flex items-start gap-3 rounded-[16px] border border-hairline bg-surface-2/60 px-4 py-3 text-[13.5px] leading-[21px] text-ink-2">
        <span
          aria-hidden="true"
          className="bg-signal absolute top-2 bottom-2 left-0 w-[3px] rounded-full"
        />
        <div>
          <span className="font-[650] text-ink">Optical Wafer Defect Stream: </span>
          <span>
            Classifying spatial die defect clusters across Station 3. Chamber sensor monitoring (Station 2) is bypassed for this dataset.
          </span>
        </div>
      </div>
    );
  }

  return null;
}


/**
 * Results announced as the line shows them: each station's sentence once it is settled, and the
 * end of the run. A polite live region reads out only what is added or changed.
 */
function LineStatus({ state, over }: { state: RunState; over: boolean }) {
  return (
    <p className="mt-4 flex items-start gap-2.5 px-2 text-[14px] leading-5 text-ink-2">
      <span
        aria-hidden="true"
        className={cn(
          "mt-[7px] inline-block size-1.5 shrink-0 rounded-full",
          over ? "bg-ink-3" : "bg-signal",
        )}
      />
      <span>{lineStatus(state, over)}</span>
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
        <p>{`Actual outcome: ${finalTest.sentence}`}</p>
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
