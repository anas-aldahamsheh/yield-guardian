"use client";

import { useQuery } from "@tanstack/react-query";
import type { WorkOrder, WorkOrderUpdate } from "@yield-guardian/contracts";
import Link from "next/link";
import { useState } from "react";

import { PageFrame, PageHeader, Panel } from "@/components/page";
import { ErrorState, Placeholder } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useApi } from "@/lib/api/context";
import { ApiError } from "@/lib/api/errors";
import { q } from "@/lib/api/queries";
import { useSession, useStartGuestSession } from "@/lib/api/session";
import { useUpdateWorkOrder } from "@/lib/api/work-orders";
import { formatDateTime } from "@/lib/format";
import { WORK_ORDER_FLOW, WORK_ORDER_STATUS } from "@/lib/labels";
import { cn } from "@/lib/utils";

import { AuditLog } from "./audit-log";
import { StatusMark } from "./work-orders-view";

const STATUSES: WorkOrder["status"][] = ["open", "in_progress", "done", "cancelled"];

export function WorkOrderView({ id }: { id: string }) {
  const api = useApi();
  const query = useQuery(q.workOrder(api, id));

  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    return (
      <PageFrame>
        <BackLink />
        <PageHeader title={<span className="tnum">{id}</span>} />
        <ErrorState error={query.error} onRetry={notFound ? undefined : () => void query.refetch()} />
      </PageFrame>
    );
  }
  if (!query.data) {
    return (
      <PageFrame>
        <BackLink />
        <Placeholder className="h-[480px]" label="Loading the work order" />
      </PageFrame>
    );
  }
  const o = query.data;
  return (
    <PageFrame>
      <BackLink />
      <PageHeader
        title={o.title}
        description={
          <span className="tnum">
            {o.work_order_id}, opened by {o.created_by} on{" "}
            <time dateTime={o.created_at} suppressHydrationWarning>
              {formatDateTime(o.created_at)}
            </time>{" "}
            from{" "}
            <Link href={`/investigations/${o.investigation_id}`} className="text-ink underline decoration-hairline-strong underline-offset-4">
              investigation {o.investigation_id}
            </Link>
            .
          </span>
        }
        actions={<StatusMark status={o.status} className="text-[14px] text-ink" />}
      />
      <div className="grid grid-cols-[minmax(0,1fr)] gap-street xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <div className="grid grid-cols-[minmax(0,1fr)] min-w-0 content-start gap-street">
          <Panel title="Progress">
            <StatusTrack status={o.status} />
          </Panel>
          <Panel title="Approved actions" description="From the investigation report, with the evidence each one cites.">
            <ol className="grid grid-cols-[minmax(0,1fr)] gap-4">
              {o.actions.map((a, i) => (
                <li key={i} className="grid grid-cols-[1.5rem_minmax(0,1fr)] gap-x-2 border-t border-hairline pt-3 first:border-t-0 first:pt-0">
                  <span className="tnum text-[14px] leading-6 text-ink-3">{i + 1}.</span>
                  <div className="min-w-0">
                    <p className="text-[15px] leading-6 text-ink">{a.action}</p>
                    <p className="mt-0.5 text-[14px] leading-5 text-ink-2">{a.rationale}</p>
                    <p className="tnum mt-1 text-[12px] leading-4 text-ink-3">
                      Evidence {a.evidence_ids.join(", ")} in{" "}
                      <Link href={`/investigations/${o.investigation_id}`} className="underline decoration-hairline-strong underline-offset-4">
                        the report
                      </Link>
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          </Panel>
          <UpdatePanel key={o.updated_at} order={o} />
        </div>
        <AuditLog targetId={o.work_order_id} />
      </div>
    </PageFrame>
  );
}

function BackLink() {
  return (
    <Link href="/work-orders" className="mb-3 inline-block text-[13px] text-ink-2 underline decoration-hairline-strong underline-offset-4 hover:text-ink">
      All work orders
    </Link>
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
              <div className="flex items-center">
                <span
                  aria-hidden="true"
                  className={cn(
                    "relative z-10 size-3 shrink-0 rounded-full border-[1.5px]",
                    done ? "border-ink bg-ink" : "border-hairline-strong bg-die",
                    current && "ring-4 ring-safelight/35",
                  )}
                />
                {i < WORK_ORDER_FLOW.length - 1 ? (
                  <span aria-hidden="true" className={cn("h-px grow", status !== "cancelled" && i < reached ? "bg-ink" : "bg-hairline-strong")} />
                ) : null}
              </div>
              <span className={cn("mt-1.5 block text-[13px] leading-5", current ? "font-medium text-ink" : done ? "text-ink-2" : "text-ink-3")}>
                {WORK_ORDER_STATUS[s]}
              </span>
            </li>
          );
        })}
      </ol>
      {status === "cancelled" ? <p className="mt-3 text-[13px] leading-5 text-ink-2">Cancelled: the work will not be done.</p> : null}
    </div>
  );
}

function UpdatePanel({ order }: { order: WorkOrder }) {
  const { canAct } = useSession();
  const guest = useStartGuestSession();
  const update = useUpdateWorkOrder(order.work_order_id);
  const [status, setStatus] = useState(order.status);
  const [note, setNote] = useState(order.note ?? "");
  const [outcome, setOutcome] = useState(order.outcome ?? "");
  const [confirmed, setConfirmed] = useState(order.outcome_confirmed);

  const canConfirm = outcome.trim().length > 0;
  const body: WorkOrderUpdate = {};
  if (status !== order.status) body.status = status;
  if (note.trim() !== (order.note ?? "")) body.note = note.trim();
  if (outcome.trim() !== (order.outcome ?? "")) body.outcome = outcome.trim();
  const confirmedNow = confirmed && canConfirm;
  if (confirmedNow !== order.outcome_confirmed) body.outcome_confirmed = confirmedNow;
  const dirty = Object.keys(body).length > 0;

  if (!canAct) {
    return (
      <Panel title="Outcome">
        <Readonly order={order} />
        <div className="mt-4 flex flex-wrap items-center justify-between gap-2 rounded-sm bg-die-2 px-3 py-2">
          <p className="text-[13px] leading-5 text-ink-2">Updating a work order needs an engineer session.</p>
          <Button size="sm" variant="outline" onClick={() => guest.mutate()} disabled={guest.isPending}>
            {guest.isPending ? "Signing in…" : "Try as engineer"}
          </Button>
        </div>
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
          <p id="wo-status" className="mb-1.5 text-[13px] leading-5 font-medium text-ink">Status</p>
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
          <Textarea id="wo-note" value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} rows={3} placeholder="What is planned, who has it" />
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
        <div className={cn("rounded-sm border px-3 py-2.5", confirmedNow ? "border-ink" : "border-hairline")}>
          <label className={cn("flex items-start gap-2.5 text-[14px] leading-5", canConfirm ? "cursor-pointer text-ink" : "text-ink-3")}>
            <input
              type="checkbox"
              className="mt-0.5 size-4 shrink-0 accent-[var(--ink)]"
              checked={confirmedNow}
              disabled={!canConfirm}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            <span>
              I confirm this outcome
              <span className="mt-0.5 block text-[13px] text-ink-2">
                Reports describe findings as associations. Only a confirmed outcome lets later reports name a cause.
                {!canConfirm ? " Write the outcome first." : ""}
              </span>
            </span>
          </label>
        </div>
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
              }}
            >
              Discard changes
            </Button>
          ) : (
            <span className="text-[13px] text-ink-3">No changes</span>
          )}
        </div>
      </form>
    </Panel>
  );
}

function Readonly({ order }: { order: WorkOrder }) {
  return (
    <dl className="grid grid-cols-[minmax(0,1fr)] gap-3 text-[14px] leading-5">
      <div>
        <dt className="text-[12px] text-ink-3">Note</dt>
        <dd className="text-ink">{order.note || <span className="text-ink-3">None</span>}</dd>
      </div>
      <div>
        <dt className="text-[12px] text-ink-3">Outcome</dt>
        <dd className="text-ink">{order.outcome || <span className="text-ink-3">Not recorded yet</span>}</dd>
      </div>
      <div>
        <dt className="text-[12px] text-ink-3">Confirmed by an engineer</dt>
        <dd className="text-ink">{order.outcome_confirmed ? "Yes" : "No"}</dd>
      </div>
    </dl>
  );
}
