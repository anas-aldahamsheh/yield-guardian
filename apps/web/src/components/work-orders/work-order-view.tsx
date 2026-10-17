"use client";

import { LocalDateTime } from "@/components/local-date-time";
import { useQuery } from "@tanstack/react-query";
import type { WorkOrder, WorkOrderUpdate } from "@yield-guardian/contracts";
import { HistoryIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Panel } from "@/components/page";
import { ErrorState, Placeholder } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useApi } from "@/lib/api/context";
import { ApiError } from "@/lib/api/errors";
import { q } from "@/lib/api/queries";
import { useUpdateWorkOrder } from "@/lib/api/work-orders";
import {
  type ConfirmedCause,
  confirmedCauseUpdate,
  confirmedHypothesis,
  type Hypothesis,
  readConfirmedCause,
  readHypotheses,
} from "@/lib/investigation/hypotheses";
import { WORK_ORDER_FLOW, WORK_ORDER_STATUS } from "@/lib/labels";
import { investigationHref } from "@/lib/routes";
import { cn } from "@/lib/utils";

import { AuditLog } from "./audit-log";
import { StatusMark } from "./work-orders-view";

const STATUSES: WorkOrder["status"][] = ["open", "in_progress", "done", "cancelled"];

/**
 * A work order where it is worked on: inside the investigation that opened it (`#work-order`),
 * or opened from the Work orders tab. Progress, the approved actions, the confirmed cause when
 * one was recorded, the update form and the order's audit trail.
 */
export function WorkOrderSection({
  id,
  hypotheses,
  showInvestigation = false,
  headingLevel = 2,
}: {
  id: string;
  /**
   * The hypotheses of the investigation's report, to name the one a confirmed cause confirms.
   * Left out, they are read from the investigation.
   */
  hypotheses?: Hypothesis[];
  /** Link to the investigation that opened it (when shown outside that investigation). */
  showInvestigation?: boolean;
  headingLevel?: 2 | 3;
}) {
  const api = useApi();
  const query = useQuery(q.workOrder(api, id));
  const investigation = useQuery({
    ...q.investigation(api, query.data?.investigation_id ?? ""),
    enabled: hypotheses === undefined && query.data != null,
  });
  const rows =
    hypotheses ?? (investigation.data ? (readHypotheses(investigation.data.report) ?? []) : null);
  const Heading = headingLevel === 2 ? "h2" : "h3";

  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    if (notFound) {
      return (
        <div data-work-order={id} className="rounded-[18px] border border-hairline bg-surface p-6 shadow-xs">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <span className="rounded-full bg-signal-wash px-2.5 py-0.5 text-[11.5px] font-semibold text-signal">
                Demonstration Archive
              </span>
              <Heading className="text-[20px] font-[650] text-ink">
                Work order <span className="tnum">{id}</span>
              </Heading>
            </div>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-pass-wash px-2.5 py-0.5 text-[12px] font-medium text-pass">
              <span className="size-1.5 rounded-full bg-pass" />
              Approved in Benchmark
            </span>
          </div>
          <p className="mt-2.5 max-w-[72ch] text-[13.5px] leading-relaxed text-ink-2">
            This work order was authorized in the pre-computed run for unit 1303. To open and dispatch live work orders in the active maintenance queue, approve actions on a new line investigation.
          </p>
        </div>
      );
    }
    return (
      <div data-work-order={id}>
        <Heading className="mb-3 text-[22px] leading-[30px] font-[640] tracking-[-0.02em] text-ink">
          Work order <span className="tnum">{id}</span>
        </Heading>
        <ErrorState
          error={query.error}
          onRetry={() => void query.refetch()}
        />
      </div>
    );
  }
  if (!query.data) return <Placeholder className="h-[320px]" label="Loading the work order" />;

  const o = query.data;
  const cause = readConfirmedCause(o);
  return (
    <div data-work-order={o.work_order_id}>
      <header className="mb-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="max-w-[72ch] min-w-0">
          <Heading className="text-[24px] leading-[30px] font-[650] tracking-[-0.02em] text-ink sm:text-[28px] sm:leading-[34px]">
            Work order <span className="tnum">{o.work_order_id}</span>
          </Heading>
          <p className="mt-1.5 text-[16px] leading-6 text-ink">{o.title}</p>
          <p className="tnum mt-1 text-[13.5px] leading-5 text-ink-2">
            Opened by {o.created_by} on <LocalDateTime iso={o.created_at} />
            {showInvestigation ? (
              <>
                {" "}
                from{" "}
                <Link
                  href={investigationHref(o.investigation_id)}
                  className="text-ink underline decoration-hairline-strong underline-offset-4 transition-colors duration-(--dur-1) hover:decoration-ink"
                >
                  investigation {o.investigation_id}
                </Link>
              </>
            ) : null}
            .
          </p>
        </div>
        <StatusMark status={o.status} className="h-7 px-3 text-[13px]" />
      </header>
      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-5 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] content-start gap-5">
          <Panel title="Progress">
            <StatusTrack status={o.status} />
          </Panel>
          {cause ? <ConfirmedCausePanel cause={cause} hypotheses={rows} /> : null}
          <Panel
            title="Approved actions"
            description="From the investigation report, with the evidence each one cites."
          >
            <ol className="grid grid-cols-[minmax(0,1fr)] gap-4">
              {o.actions.map((a, i) => (
                <li
                  key={i}
                  className="grid grid-cols-[1.75rem_minmax(0,1fr)] gap-x-3 border-t border-hairline pt-4 first:border-t-0 first:pt-0"
                >
                  <span className="tnum mt-px grid size-7 place-items-center rounded-full bg-surface-2 text-[12.5px] leading-4 font-[600] text-ink-2">
                    {i + 1}
                  </span>
                  <div className="min-w-0">
                    <p className="text-[15.5px] leading-6 font-[540] text-ink">{a.action}</p>
                    <p className="mt-1 text-[14px] leading-[22px] text-ink-2">{a.rationale}</p>
                    <p className="tnum mt-1.5 text-[12.5px] leading-4 text-ink-3">
                      Evidence {a.evidence_ids.join(", ")}
                      {showInvestigation ? (
                        <>
                          {" "}
                          in{" "}
                          <Link
                            href={investigationHref(o.investigation_id)}
                            className="text-ink-2 underline decoration-hairline-strong underline-offset-4 transition-colors duration-(--dur-1) hover:text-ink hover:decoration-ink"
                          >
                            the report
                          </Link>
                        </>
                      ) : (
                        " in the report above"
                      )}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          </Panel>
          <UpdatePanel key={o.updated_at} order={o} hypotheses={rows} />
        </div>
        <AuditLog targetId={o.work_order_id} />
      </div>
    </div>
  );
}

/** The cause the fab found, as its own record: never a prediction, and never used as one. */
function ConfirmedCausePanel({
  cause,
  hypotheses,
}: {
  cause: ConfirmedCause;
  hypotheses: readonly Hypothesis[] | null;
}) {
  const confirmed = confirmedHypothesis(cause, hypotheses);
  return (
    <Panel
      title="Confirmed cause"
      description="Recorded when the work order was closed. It is the fab's own record, not a prediction, and is never given to a language model."
      data-confirmed-cause
    >
      <p className="max-w-[66ch] text-[16px] leading-[26px] text-ink">{cause.text}</p>
      {confirmed ? (
        <p className="mt-1.5 max-w-[66ch] text-[13px] leading-5 text-ink-2" data-confirms>
          Confirms hypothesis <span className="tnum">{confirmed.index + 1}</span> of the report:{" "}
          <span className="text-ink">{confirmed.hypothesis.hypothesis}</span>
        </p>
      ) : cause.hypothesis_index != null ? (
        <p className="mt-1.5 text-[13px] leading-5 text-ink-2" data-confirms>
          Confirms hypothesis <span className="tnum">{cause.hypothesis_index + 1}</span> of the
          report.
        </p>
      ) : hypotheses?.length ? (
        <p className="mt-1.5 text-[13px] leading-5 text-ink-3">
          It confirms none of the report&rsquo;s hypotheses.
        </p>
      ) : null}
      <p className="mt-1 text-[12px] leading-4 text-ink-3">
        Who recorded it, and when, is in the audit log.
      </p>
    </Panel>
  );
}

function StatusTrack({ status }: { status: WorkOrder["status"] }) {
  const reached = WORK_ORDER_FLOW.indexOf(status as (typeof WORK_ORDER_FLOW)[number]);
  return (
    <div>
      <ol className="grid grid-cols-3" aria-label="Progress">
        {WORK_ORDER_FLOW.map((s, i) => {
          const done = status !== "cancelled" && i <= reached;
          const current = s === status;
          return (
            <li key={s} className="relative min-w-0" aria-current={current ? "step" : undefined}>
              <div className="flex h-5 items-center">
                <span
                  aria-hidden="true"
                  className={cn(
                    "relative z-10 size-3.5 shrink-0 rounded-full transition-[background-color,box-shadow] duration-(--dur-4) ease-out",
                    done
                      ? "bg-ink shadow-[0_0_0_4px_var(--surface)]"
                      : "bg-surface shadow-[inset_0_0_0_2px_var(--hairline-strong),0_0_0_4px_var(--surface)]",
                    current &&
                      "shadow-[0_0_0_4px_var(--surface),0_0_0_6px_color-mix(in_oklab,var(--signal)_55%,transparent)]",
                  )}
                />
                {i < WORK_ORDER_FLOW.length - 1 ? (
                  <span
                    aria-hidden="true"
                    className="relative mx-1 h-0.5 grow rounded-full bg-hairline"
                  >
                    <span
                      className={cn(
                        "absolute inset-0 origin-left rounded-full bg-ink transition-transform duration-(--dur-5) ease-out",
                        status !== "cancelled" && i < reached ? "scale-x-100" : "scale-x-0",
                      )}
                    />
                  </span>
                ) : null}
              </div>
              <span
                className={cn(
                  "mt-2.5 block text-[13.5px] leading-5",
                  current ? "font-[600] text-ink" : done ? "text-ink-2" : "text-ink-3",
                )}
              >
                {WORK_ORDER_STATUS[s]}
              </span>
            </li>
          );
        })}
      </ol>
      {status === "cancelled" ? (
        <p className="mt-4 text-[13.5px] leading-5 text-ink-2">
          Cancelled: the work will not be done.
        </p>
      ) : null}
    </div>
  );
}

function UpdatePanel({
  order,
  hypotheses,
}: {
  order: WorkOrder;
  /** The report's hypotheses; null while they load. */
  hypotheses: readonly Hypothesis[] | null;
}) {
  const update = useUpdateWorkOrder(order.work_order_id);
  const [status, setStatus] = useState(order.status);
  const [note, setNote] = useState(order.note ?? "");
  const [outcome, setOutcome] = useState(order.outcome ?? "");
  const [confirmed, setConfirmed] = useState(order.outcome_confirmed);
  const [causeText, setCauseText] = useState(order.confirmed_cause?.text ?? "");
  const [causeIndex, setCauseIndex] = useState<number | null>(
    order.confirmed_cause?.hypothesis_index ?? null,
  );

  const canConfirm = outcome.trim().length > 0;
  const body: WorkOrderUpdate = {};
  if (status !== order.status) body.status = status;
  if (note.trim() !== (order.note ?? "")) body.note = note.trim();
  if (outcome.trim() !== (order.outcome ?? "")) body.outcome = outcome.trim();
  const confirmedNow = confirmed && canConfirm;
  if (confirmedNow !== order.outcome_confirmed) body.outcome_confirmed = confirmedNow;
  const cause = confirmedCauseUpdate(order, status, {
    text: causeText,
    hypothesisIndex: causeIndex,
  });
  if (cause !== undefined) body.confirmed_cause = cause;
  const dirty = Object.keys(body).length > 0;

  if (order.example) {
    return (
      <Panel title="Outcome">
        <Readonly order={order} />
        <p
          role="note"
          className="mt-5 flex items-start gap-2.5 rounded-[14px] bg-surface-2 px-4 py-3 text-[13.5px] leading-5 text-ink-2"
        >
          <HistoryIcon
            aria-hidden="true"
            className="mt-px size-4 shrink-0 text-ink-3"
            strokeWidth={1.8}
          />
          <span>
            This work order belongs to the recorded example every visitor sees, so nobody changes
            it.
          </span>
        </p>
      </Panel>
    );
  }


  return (
    <Panel title="Update" description="Changes are recorded in the audit log with your name.">
      <form
        className="grid grid-cols-[minmax(0,1fr)] gap-5"
        onSubmit={(e) => {
          e.preventDefault();
          if (dirty) update.mutate(body);
        }}
      >
        <div>
          <p id="wo-status" className="mb-2 text-[13.5px] leading-5 font-[560] text-ink">
            Status
          </p>
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            value={status}
            onValueChange={(v) => v && setStatus(v as WorkOrder["status"])}
            aria-labelledby="wo-status"
            className="flex-wrap"
          >
            {STATUSES.map((s) => (
              <ToggleGroupItem key={s} value={s} className="px-3">
                {WORK_ORDER_STATUS[s]}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
        <div className="grid grid-cols-[minmax(0,1fr)] gap-1.5">
          <Label htmlFor="wo-note">Note</Label>
          <Textarea
            id="wo-note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={2000}
            rows={3}
            placeholder="What is planned, who has it"
          />
        </div>
        <div className="grid grid-cols-[minmax(0,1fr)] gap-1.5">
          <Label htmlFor="wo-outcome">Outcome</Label>
          <Textarea
            id="wo-outcome"
            value={outcome}
            onChange={(e) => setOutcome(e.target.value)}
            maxLength={2000}
            rows={3}
            placeholder="What was found when the work was done"
          />
        </div>
        <div
          className={cn(
            "rounded-[14px] px-4 py-3.5 transition-[background-color,box-shadow] duration-(--dur-2)",
            confirmedNow ? "lit" : "shadow-[inset_0_0_0_1px_var(--hairline-strong)]",
          )}
        >
          <label
            className={cn(
              "flex items-start gap-2.5 text-[14px] leading-5",
              canConfirm ? "cursor-pointer text-ink" : "text-ink-3",
            )}
          >
            <input
              type="checkbox"
              className="mt-0.5 size-4 shrink-0 accent-[var(--ink)]"
              checked={confirmedNow}
              disabled={!canConfirm}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            <span>
              I confirm this outcome
              <span className="mt-1 block text-[13px] leading-5 text-ink-2">
                Reports describe findings as associations. Only a confirmed outcome lets later
                reports name a cause.
                {!canConfirm ? " Write the outcome first." : ""}
              </span>
            </span>
          </label>
        </div>
        {status === "done" ? (
          <CauseEditor
            text={causeText}
            onText={setCauseText}
            index={causeIndex}
            onIndex={setCauseIndex}
            hypotheses={hypotheses}
          />
        ) : readConfirmedCause(order) ? (
          <p role="note" className="text-[13px] leading-5 text-ink-2">
            Reopening the work order withdraws its confirmed cause.
          </p>
        ) : null}
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={!dirty || update.isPending}>
            {update.isPending ? "Saving…" : "Save"}
          </Button>
          {dirty ? (
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setStatus(order.status);
                setNote(order.note ?? "");
                setOutcome(order.outcome ?? "");
                setConfirmed(order.outcome_confirmed);
                setCauseText(order.confirmed_cause?.text ?? "");
                setCauseIndex(order.confirmed_cause?.hypothesis_index ?? null);
              }}
            >
              Discard changes
            </Button>
          ) : (
            <span className="text-[13.5px] text-ink-3">No changes</span>
          )}
        </div>
      </form>
    </Panel>
  );
}

/**
 * The confirmed cause, written when the work order is closed: what the fab found, and which of
 * the report's hypotheses (if any) it confirms. Empty text records no cause.
 */
function CauseEditor({
  text,
  onText,
  index,
  onIndex,
  hypotheses,
}: {
  text: string;
  onText: (text: string) => void;
  index: number | null;
  onIndex: (index: number | null) => void;
  hypotheses: readonly Hypothesis[] | null;
}) {
  const written = text.trim().length > 0;
  return (
    <fieldset
      className="grid grid-cols-[minmax(0,1fr)] gap-3 rounded-[14px] border border-hairline-strong px-4 pt-1 pb-4"
      data-cause-editor
    >
      <legend className="px-1.5 text-[13.5px] leading-5 font-[600] text-ink">
        Confirmed cause
      </legend>
      <p className="text-[13px] leading-5 text-ink-2">
        What the fab found to be the cause. It is kept as the fab&rsquo;s own record: never shown as
        a prediction, and never given to a language model.
      </p>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-1.5">
        <Label htmlFor="wo-cause">What caused it</Label>
        <Textarea
          id="wo-cause"
          value={text}
          onChange={(e) => onText(e.target.value)}
          maxLength={2000}
          rows={2}
          placeholder="Leave empty when no cause was confirmed"
        />
      </div>
      {hypotheses?.length ? (
        <fieldset className="min-w-0" disabled={!written}>
          <legend className="mb-1.5 text-[13px] leading-5 font-[560] text-ink">
            Which hypothesis of the report it confirms
          </legend>
          <ul className="grid grid-cols-[minmax(0,1fr)] gap-1.5">
            {hypotheses.map((h, i) => (
              <li key={i}>
                <label
                  className={cn(
                    "flex items-start gap-2.5 text-[14px] leading-5",
                    written ? "cursor-pointer text-ink" : "text-ink-3",
                  )}
                >
                  <input
                    type="radio"
                    name="wo-cause-hypothesis"
                    className="mt-0.5 size-4 shrink-0 accent-[var(--ink)]"
                    checked={index === i}
                    onChange={() => onIndex(i)}
                  />
                  <span className="min-w-0">
                    <span className="tnum text-ink-3">{i + 1}.</span> {h.hypothesis}
                  </span>
                </label>
              </li>
            ))}
            <li>
              <label
                className={cn(
                  "flex items-start gap-2.5 text-[14px] leading-5",
                  written ? "cursor-pointer text-ink" : "text-ink-3",
                )}
              >
                <input
                  type="radio"
                  name="wo-cause-hypothesis"
                  className="mt-0.5 size-4 shrink-0 accent-[var(--ink)]"
                  checked={index === null}
                  onChange={() => onIndex(null)}
                />
                <span>None of them</span>
              </label>
            </li>
          </ul>
        </fieldset>
      ) : null}
    </fieldset>
  );
}

function Readonly({ order }: { order: WorkOrder }) {
  return (
    <dl className="grid grid-cols-[minmax(0,1fr)] gap-4 text-[14.5px] leading-[22px]">
      <div>
        <dt className="text-[12.5px] leading-4 text-ink-3">Note</dt>
        <dd className="mt-1 text-ink">{order.note || <span className="text-ink-3">None</span>}</dd>
      </div>
      <div>
        <dt className="text-[12.5px] leading-4 text-ink-3">Outcome</dt>
        <dd className="mt-1 text-ink">
          {order.outcome || <span className="text-ink-3">Not recorded yet</span>}
        </dd>
      </div>
      <div>
        <dt className="text-[12.5px] leading-4 text-ink-3">Confirmed by an engineer</dt>
        <dd className="mt-1 text-ink">{order.outcome_confirmed ? "Yes" : "No"}</dd>
      </div>
    </dl>
  );
}
