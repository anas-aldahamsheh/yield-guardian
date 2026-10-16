"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Investigation, RunAlarm } from "@yield-guardian/contracts";
import { ChevronDownIcon } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";

import { StatusLabel } from "@/components/investigation/status-label";
import { useEntrance } from "@/components/motion/entrance";
import { csrfHeaders } from "@/lib/api/client";
import { useApi } from "@/lib/api/context";
import { describeError } from "@/lib/api/errors";
import { NOT_CONFIGURED, useFeatures } from "@/lib/api/features";
import { q } from "@/lib/api/queries";
import { useSession, useStartGuestSession } from "@/lib/api/session";
import {
  formatInt,
  formatNumber,
  formatProbability,
  formatPValue,
  formatReading,
  plural,
} from "@/lib/format";
import { investigateRunAlarm } from "@/lib/live/api";
import { arrivedLive, stageResult, type RunState } from "@/lib/live/run-state";
import { turnsRed } from "@/lib/live/stations";
import { useScrollFocus } from "@/lib/use-scroll-focus";
import { investigationHref } from "@/lib/routes";
import { cn } from "@/lib/utils";

import styles from "./story.module.css";
import { useViewportRoom } from "./use-viewport-room";

/** The rail when the run has no alarm: fades in when it comes to say so while the person is here. */
function NoAlarm({ finished }: { finished: boolean }) {
  const entrance = useEntrance();
  return (
    <p className={cn(entrance && "swap-in", "px-3.5 py-4 text-[14px] leading-5 text-ink-2")}>
      {finished ? "No station raised an alarm on this input." : "No alarm so far."}
    </p>
  );
}

/** An investigation was started from an alarm (the line records it with the run). */
export type OnLinked = (alarmId: string, investigation: Investigation) => void;
/** The rail's small actions: a pill with a hairline edge. */
const ACTION =
  "press inline-flex h-7 items-center gap-1.5 rounded-full px-3 text-[12.5px] leading-none font-[560] text-ink shadow-[inset_0_0_0_1px_var(--hairline-strong)] hover:bg-surface hover:shadow-[inset_0_0_0_1px_var(--edge)] disabled:opacity-50";

/** Warnings of one kind are folded into one row from this many on. */
const FOLD = 4;

const FOLDED_TITLE: Partial<Record<RunAlarm["kind"], (n: number) => string>> = {
  unknown_pattern: (n) =>
    `${plural(n, "wafer")} unlike the maps the model learned from, to check by eye`,
  risk: (n) => `${plural(n, "unit")} above the risk threshold`,
  ewma: (n) => `Slow drift in ${plural(n, "sensor group")}`,
  cusum: (n) => `Sustained shift in ${plural(n, "sensor group")}`,
  wafer_pattern: (n) => `${plural(n, "wafer")} with a defect pattern`,
};

type Row = { kind: "one"; alarm: RunAlarm } | { kind: "fold"; key: string; alarms: RunAlarm[] };

/**
 * Alarms that turn a station red first, then the rest, newest first within each; warnings of a
 * kind that comes often are folded into one row where the newest of them is.
 */
function rows(alarms: RunAlarm[]): Row[] {
  const latest = [...alarms].reverse();
  const newest = [...latest.filter(turnsRed), ...latest.filter((a) => !turnsRed(a))];
  const counts = new Map<string, number>();
  for (const a of newest) if (!turnsRed(a)) counts.set(a.kind, (counts.get(a.kind) ?? 0) + 1);
  const out: Row[] = [];
  const folds = new Map<string, RunAlarm[]>();
  for (const a of newest) {
    if (!turnsRed(a) && (counts.get(a.kind) ?? 0) >= FOLD) {
      const list = folds.get(a.kind);
      if (list) list.push(a);
      else {
        const fresh = [a];
        folds.set(a.kind, fresh);
        out.push({ kind: "fold", key: a.kind, alarms: fresh });
      }
    } else out.push({ kind: "one", alarm: a });
  }
  return out;
}

/** Where an alarm is, in words: the unit, the wafer or the lot. */
export function alarmPlace(state: RunState, alarm: RunAlarm): string {
  if (alarm.unit_id != null) return `Unit ${alarm.unit_id}`;
  if (alarm.wafer_index != null) {
    const w = stageResult(state, "wafer_pattern")?.wafers[alarm.wafer_index];
    return w ? `Wafer ${w.wafer} of ${lotName(w.lot)}` : `Wafer ${alarm.wafer_index + 1}`;
  }
  if (alarm.lot) return upperFirst(lotName(alarm.lot));
  return "The run";
}

/** WM-811K lots are named "lot45647"; a lot from a file or a drawing is named as given. */
export function lotName(lot: string): string {
  return /^lot/i.test(lot) ? lot : `lot ${lot}`;
}

function upperFirst(s: string): string {
  return s ? s[0]!.toUpperCase() + s.slice(1) : s;
}

/** The alarm's value against its limit, in the statistic's own terms. */
export function alarmReading(alarm: RunAlarm): string | null {
  const { value, limit } = alarm;
  if (value == null) return null;
  switch (alarm.kind) {
    case "risk":
      return `Risk ${formatProbability(value)}${limit != null ? `, high from ${formatProbability(limit)}` : ""}`;
    case "t2":
      return `T² ${formatReading(value)}${limit != null ? ` against the 99.9% limit ${formatReading(limit)}` : ""}`;
    case "spe":
      return `SPE ${formatReading(value)}${limit != null ? ` against the 99.9% limit ${formatReading(limit)}` : ""}`;
    case "ewma":
      return `EWMA ${formatNumber(value)}${limit != null ? ` against the limit ${formatNumber(limit)}` : ""}`;
    case "cusum":
      return `CUSUM ${formatNumber(value)}${limit != null ? ` against the limit ${formatNumber(limit)}` : ""}`;
    case "unknown_pattern":
      return `Unknown score ${formatReading(value)}${limit != null ? `, unknown from ${formatReading(limit)}` : ""}`;
    case "wafer_pattern":
      return `Probability ${formatProbability(value)}${limit != null ? `, classified automatically from ${formatProbability(limit)}` : ""}`;
    case "lot_excursion":
      return `q ${formatPValue(value)}${limit != null ? ` below ${formatPValue(limit)}` : ""}`;
    default:
      return `${formatReading(value)}${limit != null ? ` against ${formatReading(limit)}` : ""}`;
  }
}

/**
 * The alarms rail: every alarm the line has shown so far, newest first, with its plain meaning.
 * "Show" opens the station on the alarm's unit, wafer or lot; "Investigate" starts the
 * investigator on it, and its progress streams in the row.
 */
export function AlarmsRail({
  state,
  reading = false,
  shown,
  onShow,
  onLinked,
  selected = null,
  over = false,
  className,
}: {
  state: RunState | null;
  /** The run's stored state is being read: its alarms come with it. */
  reading?: boolean;
  /** The run has ended and the line has shown every result. */
  over?: boolean;
  shown: ReadonlySet<string>;
  onShow: (alarm: RunAlarm) => void;
  onLinked: OnLinked;
  /** The alarm chosen with its Show button (the URL's `alarm`). */
  selected?: string | null;
  className?: string;
}) {
  const scroll = useScrollFocus<HTMLDivElement>("Alarms of this run");
  const root = useRef<HTMLElement>(null);
  useViewportRoom(root);
  const alarms = state ? state.alarms.filter((a) => shown.has(a.alarm_id)) : [];
  const red = alarms.filter(turnsRed).length;
  const warnings = alarms.length - red;
  // "None raised" and the count the server left out wait until the line has played every
  // result: until then more alarms may still be on their way to the screen.
  const finished = Boolean(state) && over;
  const notListed = finished ? state!.alarmsNotListed : 0;

  return (
    <section
      ref={root}
      aria-labelledby="alarms-title"
      className={cn("flex min-h-0 min-w-0 flex-col", className)}
    >
      {/* A rectangular clip, inside the rounded card: beside the line the rail can be shorter
          than what it holds, and a rounded clip would cost the compositor a pass every frame. */}
      <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
        <header className="flex items-baseline justify-between gap-3 px-5 pt-5 pb-3 shadow-[0_1px_0_var(--hairline)]">
          <h2
            id="alarms-title"
            tabIndex={-1}
            className="text-[18px] leading-6 font-[640] tracking-[-0.015em] text-ink [font-stretch:106%] outline-none"
          >
            Alarms
          </h2>
          <p className="tnum text-[13px] leading-5 text-ink-2" aria-live="polite">
            {!state
              ? ""
              : alarms.length
                ? [red ? plural(red, "alarm") : null, warnings ? plural(warnings, "warning") : null]
                    .filter(Boolean)
                    .join(", ")
                : finished
                  ? "none raised"
                  : "none yet"}
          </p>
        </header>
        {/* Under the line, room at the end so the last alarm scrolls clear of the floating Ask
          button; beside it the rail already ends above the button. The list is a plain rectangle
          held clear of the rounded corners, and its end fades under a gradient laid over it: a
          rounded or masked scroller would cost the compositor a pass on every frame. */}
        <div
          ref={scroll}
          className="mb-2.5 min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 pt-2 pb-24 xl:pb-4"
        >
          {!state ? (
            <div className="unexposed flex gap-3 rounded-[18px] px-3.5 py-4">
              <span
                aria-hidden="true"
                className="mt-[5px] size-2.5 shrink-0 rounded-full shadow-[inset_0_0_0_1.5px_var(--hairline-strong)]"
              />
              <p className="text-[14px] leading-[21px] text-ink-2">
                {reading
                  ? "Reading this run's alarms."
                  : "When a station finds something, its alarm arrives here with what it means, and you can start an investigation of it."}
              </p>
            </div>
          ) : !alarms.length ? (
            <NoAlarm key={finished ? "finished" : "so-far"} finished={finished} />
          ) : (
            <ul className="flex flex-col gap-1">
              {rows(alarms).map((row) =>
                row.kind === "one" ? (
                  <li
                    key={row.alarm.alarm_id}
                    // Only an alarm that reached this page on the stream slides in; one read
                    // with the run's stored state (a reload, a link) is already there.
                    className={
                      arrivedLive(state, { alarmId: row.alarm.alarm_id })
                        ? styles.slideIn
                        : undefined
                    }
                  >
                    <AlarmItem
                      state={state}
                      alarm={row.alarm}
                      onShow={onShow}
                      onLinked={onLinked}
                      selected={row.alarm.alarm_id === selected}
                    />
                  </li>
                ) : (
                  <li
                    key={`fold-${row.key}`}
                    className={
                      row.alarms.some((a) => arrivedLive(state, { alarmId: a.alarm_id }))
                        ? styles.slideIn
                        : undefined
                    }
                  >
                    <Fold
                      state={state}
                      alarms={row.alarms}
                      onShow={onShow}
                      onLinked={onLinked}
                      selected={selected}
                    />
                  </li>
                ),
              )}
            </ul>
          )}
          {notListed > 0 ? (
            <p className="tnum px-3.5 py-3 text-[13px] leading-5 text-ink-2">{`and ${formatInt(notListed)} more, see the station`}</p>
          ) : null}
        </div>
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-px bottom-px h-14 rounded-b-[27px] bg-[linear-gradient(to_bottom,transparent,var(--surface))]"
        />
      </div>
    </section>
  );
}

function Mark({ alarm }: { alarm: RunAlarm }) {
  return turnsRed(alarm) ? (
    <span
      aria-hidden="true"
      className="mt-[5px] size-2.5 shrink-0 rounded-full bg-fail shadow-[0_0_0_3px_var(--fail-wash)]"
    />
  ) : (
    <span
      aria-hidden="true"
      className="mt-[5px] size-2.5 shrink-0 rounded-full shadow-[inset_0_0_0_1.75px_var(--concern)]"
    />
  );
}

function AlarmItem({
  state,
  alarm,
  onShow,
  onLinked,
  compact = false,
  selected = false,
}: {
  state: RunState;
  alarm: RunAlarm;
  onShow: (alarm: RunAlarm) => void;
  onLinked: OnLinked;
  compact?: boolean;
  selected?: boolean;
}) {
  const reading = alarmReading(alarm);
  return (
    <article
      aria-current={selected || undefined}
      className={cn(
        "flex gap-3 rounded-[16px] px-3.5 transition-colors duration-(--dur-2)",
        compact ? "py-2.5" : "py-3.5",
        turnsRed(alarm) && !compact
          ? "bg-[color-mix(in_oklab,var(--fail)_7%,transparent)] hover:bg-[color-mix(in_oklab,var(--fail)_11%,transparent)]"
          : "hover:bg-surface-2",
        selected && "lit hover:bg-signal-wash",
      )}
    >
      <Mark alarm={alarm} />
      <div className="min-w-0 flex-1">
        <h3 className="text-[14.5px] leading-5 font-[600] tracking-[-0.005em] text-ink">
          <span className="sr-only">{turnsRed(alarm) ? "Alarm: " : "Warning: "}</span>
          {compact ? alarmPlace(state, alarm) : alarm.title}
        </h3>
        {!compact ? (
          <p className="mt-0.5 text-[13px] leading-[19px] text-ink-2">{alarm.meaning}</p>
        ) : null}
        <p className="tnum mt-1.5 text-[12px] leading-4 text-ink-3">
          {[compact ? null : alarmPlace(state, alarm), reading, alarm.alarm_id]
            .filter(Boolean)
            .join(". ")}
        </p>
        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          <button type="button" onClick={() => onShow(alarm)} className={ACTION}>
            {`Show ${alarmPlace(state, alarm)
              .replace(/^The run$/, "it")
              .replace(/^(\w)/, (m) => m.toLowerCase())}`}
          </button>
          <Investigate runId={state.runId} alarm={alarm} onLinked={onLinked} />
        </div>
      </div>
    </article>
  );
}

function Fold({
  state,
  alarms,
  onShow,
  onLinked,
  selected,
}: {
  state: RunState;
  alarms: RunAlarm[];
  onShow: (alarm: RunAlarm) => void;
  onLinked: OnLinked;
  selected?: string | null;
}) {
  const holdsSelected = alarms.some((a) => a.alarm_id === selected);
  // Open or closed as the person chose; until then, open when it holds the chosen alarm.
  const [choice, setChoice] = useState<boolean | null>(null);
  const open = choice ?? holdsSelected;
  const first = alarms[0]!;
  const title =
    FOLDED_TITLE[first.kind]?.(alarms.length) ??
    `${plural(alarms.length, "warning")}: ${first.title}`;
  const id = `fold-${first.kind}`;
  return (
    <div>
      <div className="flex gap-3 rounded-[16px] px-3.5 py-3.5 transition-colors duration-(--dur-2) hover:bg-surface-2">
        <Mark alarm={first} />
        <div className="min-w-0 flex-1">
          <h3 className="text-[14.5px] leading-5 font-[600] tracking-[-0.005em] text-ink">
            <span className="sr-only">Warnings: </span>
            {title}
          </h3>
          <p className="mt-0.5 text-[13px] leading-[19px] text-ink-2">{first.meaning}</p>
          <button
            type="button"
            aria-expanded={open}
            aria-controls={id}
            onClick={() => setChoice(!open)}
            className={cn(ACTION, "group/fold mt-2.5")}
          >
            {open ? "Hide the list" : `List all ${formatInt(alarms.length)}`}
            <ChevronDownIcon
              aria-hidden="true"
              className="size-3.5 transition-transform duration-(--dur-3) ease-spring group-aria-expanded/fold:rotate-180"
              strokeWidth={2}
            />
          </button>
        </div>
      </div>
      {open ? (
        <ul
          id={id}
          className={cn(
            // It grows open when the person opens it; open as the page arrived, it is there.
            choice && "grow-in",
            "relative ml-[19px] flex flex-col gap-0.5 pl-3 before:absolute before:inset-y-1 before:left-0 before:w-px before:bg-hairline-strong",
          )}
        >
          {alarms.map((a) => (
            <li key={a.alarm_id}>
              <AlarmItem
                state={state}
                alarm={a}
                onShow={onShow}
                onLinked={onLinked}
                compact
                selected={a.alarm_id === selected}
              />
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** Investigate one alarm: sign in when there is no engineer session, then start and follow it. */
export function Investigate({
  runId,
  alarm,
  onLinked,
}: {
  runId: string;
  alarm: RunAlarm;
  onLinked: OnLinked;
}) {
  const client = useQueryClient();
  const { canAct, csrf } = useSession();
  const { liveInvestigations } = useFeatures();
  const guest = useStartGuestSession();
  const [asking, setAsking] = useState(false);
  const start = useMutation({
    mutationFn: (headers: Record<string, string>) =>
      investigateRunAlarm(runId, alarm.alarm_id, headers),
    onSuccess: (investigation: Investigation) => {
      client.setQueryData(["investigations", investigation.investigation_id], investigation);
      void client.invalidateQueries({ queryKey: ["investigations", "list"] });
      onLinked(alarm.alarm_id, investigation);
    },
  });

  if (alarm.investigation_id)
    return <Progress id={alarm.investigation_id} stored={alarm.investigation_status ?? null} />;
  if (liveInvestigations === false) {
    return (
      <span className="text-[12px] leading-4 text-ink-3">
        {NOT_CONFIGURED.investigations.title}.
      </span>
    );
  }
  if (asking && !canAct) {
    return (
      <span className="flex flex-wrap items-center gap-2 text-[13px] leading-5 text-ink-2">
        An investigation runs in an engineer session.
        <button
          type="button"
          disabled={guest.isPending}
          onClick={() =>
            guest.mutate(undefined, {
              onSuccess: (session) => {
                setAsking(false);
                start.mutate(csrfHeaders(session.csrf_token));
              },
            })
          }
          className="press inline-flex h-7 items-center rounded-full bg-ink px-3 text-[12.5px] leading-none font-[600] text-canvas hover:bg-ink/90 disabled:opacity-60"
        >
          {guest.isPending ? "Signing in" : "Sign in as engineer and investigate"}
        </button>
      </span>
    );
  }
  return (
    <>
      <button
        type="button"
        disabled={start.isPending}
        onClick={() => (canAct ? start.mutate(csrf) : setAsking(true))}
        className={ACTION}
      >
        {start.isPending ? "Starting" : "Investigate"}
      </button>
      {start.isError ? (
        <span role="alert" className="basis-full text-[12px] leading-4 text-fail">
          {`${describeError(start.error).title}. ${describeError(start.error).detail}`}
        </span>
      ) : null}
    </>
  );
}

/**
 * An investigation's progress: its status, steps so far and the latest one. Station 4 under the
 * line follows its stream, which keeps this row current. Until the investigation itself is read,
 * the status the run's stored state carries (`stored`) stands for it, so a reload shows it at once.
 */
function Progress({ id, stored }: { id: string; stored: Investigation["status"] | null }) {
  const api = useApi();
  const query = useQuery(q.investigation(api, id));
  const inv = query.data;
  const status = inv?.status ?? stored;
  const last = inv?.steps.at(-1);
  return (
    <span
      className="flex min-w-0 basis-full flex-col gap-0.5 text-[13px] leading-5"
      aria-live="polite"
    >
      <span className="flex flex-wrap items-center gap-x-3">
        {status ? (
          <StatusLabel status={status} />
        ) : (
          <span className="text-ink-3">Starting the investigation</span>
        )}
        {inv ? <span className="tnum text-ink-3">{plural(inv.steps.length, "step")}</span> : null}
        <Link
          href={investigationHref(id)}
          className="font-[560] text-ink underline decoration-hairline-strong underline-offset-4 transition-colors hover:decoration-signal"
        >
          Open the investigation
        </Link>
      </span>
      {last ? (
        <span className="truncate text-[12px] leading-4 text-ink-3">{last.title}</span>
      ) : null}
    </span>
  );
}
