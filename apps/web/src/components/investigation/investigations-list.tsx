"use client";

import { LocalDateTime } from "@/components/local-date-time";
import { useInfiniteQuery } from "@tanstack/react-query";
import type { InvestigationSummary } from "@yield-guardian/contracts";
import { HistoryIcon, InfoIcon } from "lucide-react";
import { LayoutGroup, m } from "framer-motion";
import Link from "next/link";
import { useState } from "react";

import { MotionFeatures } from "@/components/motion/motion-features";
import { SPRING } from "@/components/motion/springs";
import { NAV_FORWARD, Shared } from "@/components/page-transition";
import { ScrollRegion } from "@/components/scroll-region";
import { EmptyState, ErrorState, Placeholder } from "@/components/states";
import { Tag } from "@/components/tag";
import { Button } from "@/components/ui/button";
import { useApi } from "@/lib/api/context";
import { NOT_CONFIGURED, useFeatures } from "@/lib/api/features";
import { q } from "@/lib/api/queries";
import { LIVE_STATUSES } from "@/lib/investigation/events";
import { formatInt, formatNumber, plural } from "@/lib/format";
import { TRIGGER_KIND } from "@/lib/labels";
import { investigationHref, lineHref, workOrderHref } from "@/lib/routes";
import { cn } from "@/lib/utils";

import { Elapsed } from "./elapsed";
import { StatusLabel } from "./status-label";
import { StopInvestigationButton } from "./stop-investigation";

type Status = InvestigationSummary["status"];
type GroupId = "running" | "awaiting" | "decided" | "failed" | "example";
type GroupSpec = {
  id: GroupId;
  title: string;
  description: string;
  statuses: Status[];
  empty: string;
};

/** The product's examples: recorded runs every visitor sees, apart from their own. */
const EXAMPLES: GroupSpec = {
  id: "example",
  title: "Example",
  description:
    "Recorded once on the server and replayed without calling a model. Every visitor sees the same example, and nobody decides it.",
  statuses: [],
  empty: "",
};

const GROUPS: GroupSpec[] = [
  {
    id: "running",
    title: "Running",
    description: "Gathering evidence or writing the report now, with the real elapsed time.",
    statuses: ["queued", "running"],
    empty: "Nothing is running.",
  },
  {
    id: "awaiting",
    title: "Awaiting decision",
    description: "A checked report is ready: an engineer approves actions or rejects it.",
    statuses: ["awaiting_decision"],
    empty: "No report is waiting for a decision.",
  },
  {
    id: "decided",
    title: "Decided",
    description: "Approved (with the work order it opened) or rejected.",
    statuses: ["approved", "rejected"],
    empty: "No report has been decided yet.",
  },
  {
    id: "failed",
    title: "Failed",
    description: "Runs that stopped before a report, with the reason on their page.",
    statuses: ["failed"],
    empty: "",
  },
];

/** While something runs, the list checks for new statuses every few seconds; otherwise it is still. */
const RUNNING_REFRESH_MS = 4000;

/**
 * The visitor's own investigations, grouped by where they stand: running, awaiting a decision,
 * decided. The groups are the stages of one lifecycle on a rail; when an investigation's status
 * changes, its row moves to its new stage. The product's example (a recorded run every visitor
 * sees, read-only) comes after them, apart from the rail; attempts to record one that failed
 * stay behind a button, so the runs people open come first.
 */
export function InvestigationsIndex() {
  const api = useApi();
  const [showFailedRecordings, setShowFailedRecordings] = useState(false);
  const { liveInvestigations } = useFeatures();
  const query = useInfiniteQuery({
    ...q.investigationPages(api),
    refetchInterval: (state) =>
      state.state.data?.pages.some((p) =>
        [...p.items, ...p.examples].some((inv) => LIVE_STATUSES.has(inv.status)),
      )
        ? RUNNING_REFRESH_MS
        : false,
  });

  const items = query.data?.pages.flatMap((p) => p.items) ?? [];
  const examples = query.data?.pages[0]?.examples ?? [];
  const total = query.data?.pages[0]?.total;
  const failedRecordings = examples.filter((inv) => inv.status === "failed");
  const shownExamples = showFailedRecordings
    ? examples
    : examples.filter((inv) => inv.status !== "failed");

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-8">
      {liveInvestigations === false ? <NotConfiguredNote /> : null}
      {query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : !query.data ? (
        <Placeholder className="h-64" label="Loading investigations" />
      ) : (
        <MotionFeatures>
          <LayoutGroup id="investigations">
            {items.length === 0 ? (
              <EmptyState
                title="No investigations yet"
                className="unexposed border-solid bg-surface px-6 py-10 sm:px-10 sm:py-14"
                action={
                  <Button asChild>
                    <Link href={lineHref()}>Open the line</Link>
                  </Button>
                }
              >
                Run a sample or your own data on the line, then choose Investigate on an alarm.
              </EmptyState>
            ) : (
              <>
                <div>
                  {GROUPS.map((g) => ({
                    g,
                    rows: items.filter((inv) => g.statuses.includes(inv.status)),
                  }))
                    .filter(({ g, rows }) => g.id !== "failed" || rows.length > 0)
                    .map(({ g, rows }, i, all) => (
                      <Group key={g.id} group={g} rows={rows} last={i === all.length - 1} />
                    ))}
                </div>
                <div className="flex flex-wrap items-center gap-x-5 gap-y-3 border-t border-hairline pt-5 text-[13.5px] leading-5 text-ink-2">
                  {total != null ? (
                    <span className="tnum">
                      {formatInt(items.length)} of {formatInt(total)} shown, newest first.
                    </span>
                  ) : null}
                  {query.hasNextPage ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void query.fetchNextPage()}
                      disabled={query.isFetchingNextPage}
                    >
                      {query.isFetchingNextPage ? "Loading…" : "Show older investigations"}
                    </Button>
                  ) : null}
                </div>
              </>
            )}
            {shownExamples.length > 0 ? <ExampleGroup rows={shownExamples} /> : null}
            {failedRecordings.length > 0 ? (
              <div className="-mt-3 text-[13.5px] leading-5 text-ink-2">
                <button
                  type="button"
                  aria-pressed={showFailedRecordings}
                  onClick={() => setShowFailedRecordings((on) => !on)}
                  className="inline-block min-h-6 cursor-pointer rounded-sm py-0.5 text-left underline decoration-hairline-strong underline-offset-4 transition-colors duration-(--dur-1) hover:text-ink hover:decoration-ink"
                >
                  {showFailedRecordings
                    ? "Hide the failed recording attempts"
                    : `Show ${plural(failedRecordings.length, "failed recording attempt")}`}
                </button>
              </div>
            ) : null}
          </LayoutGroup>
        </MotionFeatures>
      )}
    </div>
  );
}

/** A group's title and its count, as one heading ("Awaiting decision 2"). */
function GroupHeading({ id, title, count }: { id: string; title: string; count: number }) {
  return (
    <h2
      id={id}
      className="flex flex-wrap items-baseline gap-x-3 text-[22px] leading-[30px] font-[640] tracking-[-0.02em] text-ink sm:text-h2"
    >
      {title}{" "}
      <span
        className={cn(
          "readout tnum text-[22px] leading-[30px] sm:text-[24px]",
          count > 0 ? "text-ink-2" : "text-ink-3",
        )}
      >
        {formatInt(count)}
      </span>
    </h2>
  );
}

/**
 * One stage of the lifecycle: its node on the rail, its title and count, and its investigations.
 * The node is lit when the stage holds something; while something runs, the film's light runs
 * down the rail from the running stage. The rail ends at the last stage (`last`, passed in
 * rather than read from :last-child, which would make every node the parser adds restyle the
 * whole list).
 */
function Group({
  group,
  rows,
  last,
}: {
  group: GroupSpec;
  rows: InvestigationSummary[];
  last: boolean;
}) {
  const titleId = `group-${group.id}`;
  const held = rows.length > 0;
  const live = group.id === "running" && held;
  return (
    <m.section
      layout="position"
      transition={SPRING.layout}
      aria-labelledby={titleId}
      data-group={group.id}
      className="relative grid grid-cols-[22px_minmax(0,1fr)] gap-x-4 sm:grid-cols-[28px_minmax(0,1fr)] sm:gap-x-7"
    >
      <div aria-hidden="true" className="relative flex justify-center">
        <span
          className={cn(
            "relative z-10 mt-[9px] size-3 rounded-full transition-[background-color,box-shadow] duration-(--dur-3)",
            live
              ? "live-dot"
              : held
                ? group.id === "failed"
                  ? "bg-fail"
                  : "bg-ink"
                : "bg-canvas shadow-[inset_0_0_0_2px_var(--hairline-strong)]",
          )}
        />
        {last ? null : (
          <span className="absolute top-[30px] -bottom-[9px] w-0.5 rounded-full bg-hairline" />
        )}
        {live && !last ? <span className="live-rail top-[30px] -bottom-[9px] w-0.5" /> : null}
      </div>
      <div className={cn("min-w-0", !last && "pb-12 sm:pb-14")}>
        <GroupHeading id={titleId} title={group.title} count={rows.length} />
        <p className="mt-1 max-w-[64ch] text-[14.5px] leading-[22px] text-ink-2">
          {group.description}
        </p>
        {held ? (
          <div className={cn("panel relative mt-5 overflow-hidden", live && "pt-0.5")}>
            {live ? <span aria-hidden className="live-edge" /> : null}
            <InvestigationTable label={group.title} rows={rows} elapsed={group.id === "running"} />
          </div>
        ) : (
          <p className="mt-3 text-[14px] leading-5 text-ink-3">{group.empty}</p>
        )}
      </div>
    </m.section>
  );
}

/**
 * The product's example, apart from the visitor's own lifecycle: off the rail, under a rule,
 * with the mark of a recording. Its rows are the same table as a stage's.
 */
function ExampleGroup({ rows }: { rows: InvestigationSummary[] }) {
  const titleId = `group-${EXAMPLES.id}`;
  const title = rows.length === 1 ? "Example" : "Examples";
  return (
    <section
      aria-labelledby={titleId}
      data-group={EXAMPLES.id}
      className="grid grid-cols-[minmax(0,1fr)] border-t border-hairline pt-8 sm:pt-10"
    >
      <div className="flex items-start gap-4 sm:gap-5">
        <span
          aria-hidden="true"
          className="mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-[12px] bg-surface-2 text-ink-2 shadow-[inset_0_0_0_1px_var(--hairline),var(--highlight)]"
        >
          <HistoryIcon className="size-[19px]" strokeWidth={1.8} />
        </span>
        <div className="min-w-0">
          <GroupHeading id={titleId} title={title} count={rows.length} />
          <p className="mt-1 max-w-[64ch] text-[14.5px] leading-[22px] text-ink-2">
            {EXAMPLES.description}
          </p>
        </div>
      </div>
      <div className="panel relative mt-5 overflow-hidden">
        <InvestigationTable label={title} rows={rows} elapsed={false} />
      </div>
    </section>
  );
}

/** A group's investigations; `elapsed` shows the running time in place of the start. */
function InvestigationTable({
  label,
  rows,
  elapsed,
}: {
  label: string;
  rows: InvestigationSummary[];
  elapsed: boolean;
}) {
  return (
    <ScrollRegion label={label}>
      <table className="w-full min-w-[780px] border-collapse text-left text-[14px] leading-5">
        <caption className="sr-only">{label}</caption>
        <thead>
          <tr className="border-b border-hairline text-[12.5px] leading-4 text-ink-3">
            <th scope="col" className="py-3 pr-3 pl-5 font-[520] sm:pl-6">
              Investigation
            </th>
            <th scope="col" className="px-3 py-3 font-[520]">
              Status
            </th>
            <th scope="col" className="px-3 py-3 font-[520]">
              From
            </th>
            <th scope="col" className="px-3 py-3 font-[520]">
              {elapsed ? "Elapsed" : "Started"}
            </th>
            <th scope="col" className="px-3 py-3 text-right font-[520]">
              Points
            </th>
            <th scope="col" className="py-3 pr-5 pl-3 font-[520] sm:pr-6">
              Work order
            </th>
            {elapsed ? (
              <th scope="col" className="py-3 pr-5 pl-3 sm:pr-6">
                <span className="sr-only">Actions</span>
              </th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((inv) => (
            <m.tr
              key={inv.investigation_id}
              layoutId={`investigation-${inv.investigation_id}`}
              transition={SPRING.layout}
              className="group/row border-b border-hairline transition-colors duration-(--dur-1) last:border-b-0 hover:bg-surface-2"
            >
              <th scope="row" className="py-3.5 pr-3 pl-5 font-[420] sm:pl-6">
                <Shared name={`investigation-title-${inv.investigation_id}`}>
                  <Link
                    href={investigationHref(inv.investigation_id)}
                    transitionTypes={NAV_FORWARD}
                    className="inline-block text-[15px] leading-[22px] font-[580] text-ink no-underline decoration-ink underline-offset-4 group-hover/row:underline focus-visible:underline"
                  >
                    {inv.title}
                  </Link>
                </Shared>
                {inv.recorded ? (
                  <Tag className="ml-2 group-hover/row:bg-surface-3">Recorded</Tag>
                ) : null}
              </th>
              <td className="px-3 py-3.5 whitespace-nowrap">
                <Shared name={`investigation-status-${inv.investigation_id}`}>
                  <StatusLabel status={inv.status} />
                </Shared>
              </td>
              <td className="tnum px-3 py-3.5 whitespace-nowrap text-ink-2">
                {TRIGGER_KIND[inv.trigger.kind] ?? inv.trigger.kind} {inv.trigger.ref}
              </td>
              <td className="tnum px-3 py-3.5 whitespace-nowrap text-ink-2">
                {LIVE_STATUSES.has(inv.status) ? (
                  <Elapsed from={inv.created_at} running />
                ) : (
                  <LocalDateTime iso={inv.created_at} />
                )}
              </td>
              <td className="tnum px-3 py-3.5 text-right text-ink-2">
                {inv.usage ? formatNumber(inv.usage.points, 5) : "–"}
              </td>
              <td className="tnum py-3.5 pr-5 pl-3 sm:pr-6">
                {inv.work_order_id ? (
                  <Link
                    href={workOrderHref(inv.work_order_id, inv.investigation_id)}
                    className="font-[560] text-ink underline decoration-hairline-strong underline-offset-4 transition-colors duration-(--dur-1) hover:decoration-ink"
                  >
                    {inv.work_order_id}
                  </Link>
                ) : (
                  <span className="text-ink-3">–</span>
                )}
              </td>
              {elapsed ? (
                <td className="py-2.5 pr-5 pl-3 text-right sm:pr-6">
                  {LIVE_STATUSES.has(inv.status) ? (
                    <StopInvestigationButton
                      investigationId={inv.investigation_id}
                      recorded={inv.recorded}
                      title={inv.title}
                      size="xs"
                    />
                  ) : null}
                </td>
              ) : null}
            </m.tr>
          ))}
        </tbody>
      </table>
    </ScrollRegion>
  );
}

function NotConfiguredNote() {
  return (
    <div
      role="note"
      className="flex items-start gap-3 rounded-[14px] bg-surface px-4 py-3.5 shadow-[inset_0_0_0_1px_var(--hairline-strong)] sm:px-5"
    >
      <InfoIcon className="mt-0.5 size-[18px] shrink-0 text-ink-2" strokeWidth={1.9} aria-hidden />
      <div className="min-w-0">
        <p className="text-[14.5px] leading-5 font-[600] text-ink">
          {NOT_CONFIGURED.investigations.title}
        </p>
        <p className="mt-1 text-[13.5px] leading-5 text-ink-2">
          {NOT_CONFIGURED.investigations.detail}
        </p>
      </div>
    </div>
  );
}
