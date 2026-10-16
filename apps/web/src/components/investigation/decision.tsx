"use client";

import { LocalDateTime } from "@/components/local-date-time";
import type { Investigation, Report } from "@yield-guardian/contracts";
import { HistoryIcon } from "lucide-react";
import Link from "next/link";
import { useId, useState } from "react";

import { useEntrance } from "@/components/motion/entrance";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useDecideInvestigation } from "@/lib/api/investigations";
import { useSession, useStartGuestSession } from "@/lib/api/session";
import { plural } from "@/lib/format";
import { lineHref, workOrderHref } from "@/lib/routes";
import { cn } from "@/lib/utils";

import { ActionBody, type Shared } from "./report";

/**
 * The engineer's decision. Each proposed action can be approved on its own; approving opens one
 * work order with the chosen actions. Rejecting keeps the report, marked as rejected.
 */
export function DecisionActions({
  investigation,
  report,
  shared,
}: {
  investigation: Investigation;
  report: Report;
  shared: Shared;
}) {
  const { canAct } = useSession();
  const guest = useStartGuestSession();
  const decide = useDecideInvestigation(investigation.investigation_id);
  const [chosen, setChosen] = useState<Set<number>>(() => new Set(report.actions.map((_, i) => i)));
  const [note, setNote] = useState("");
  const noteId = useId();
  // The recorded example is the same for every visitor, so nobody decides it (the API refuses).
  const example = investigation.recorded;
  const open = investigation.status === "awaiting_decision" && canAct && !example;
  const decision = investigation.decision;
  // A decision made here comes in; one the page arrived with is simply there.
  const entrance = useEntrance();

  const toggle = (i: number) =>
    setChosen((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });

  return (
    <div className="mt-4">
      <ol className="grid grid-cols-[minmax(0,1fr)] gap-6">
        {report.actions.map((action, i) => {
          const approved = decision?.verdict === "approve" && decision.actions.includes(i);
          return (
            <li key={i} className="grid grid-cols-[1.75rem_minmax(0,1fr)] gap-x-2">
              {open ? (
                <input
                  type="checkbox"
                  checked={chosen.has(i)}
                  onChange={() => toggle(i)}
                  aria-label={`Approve action ${i + 1}`}
                  className="mt-[7px] size-[18px] cursor-pointer accent-[var(--ink)]"
                />
              ) : (
                <span className="tnum pt-[6px] text-[13px] leading-5 font-[560] text-ink-3">
                  {i + 1}.
                </span>
              )}
              <div className="min-w-0">
                <ActionBody action={action} index={i} {...shared} />
                {decision ? (
                  <p
                    className={cn(
                      "mt-2 inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-[12.5px] leading-4 font-[560]",
                      approved ? "bg-pass-wash text-ink" : "bg-surface-2 text-ink-2",
                    )}
                  >
                    <span
                      aria-hidden="true"
                      className={cn(
                        "size-1.5 rounded-full",
                        approved ? "bg-pass" : "bg-mark-muted",
                      )}
                    />
                    {approved ? "Approved" : "Not approved"}
                  </p>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>

      {decision ? (
        <div
          className={cn(
            entrance && "swap-in",
            "mt-8 rounded-[16px] px-4 py-4 sm:px-5",
            decision.verdict === "approve"
              ? "bg-pass-wash shadow-[inset_0_0_0_1px_color-mix(in_oklab,var(--pass)_28%,transparent)]"
              : "bg-surface-2 shadow-[inset_0_0_0_1px_var(--hairline-strong)]",
          )}
        >
          <p className="text-[15.5px] leading-6 font-[560] text-ink">
            {decision.verdict === "approve"
              ? `Approved ${plural(decision.actions.length, "action")}`
              : "Rejected"}{" "}
            by {decision.decided_by}, <LocalDateTime iso={decision.decided_at} />.
          </p>
          {decision.note ? (
            <p className="mt-1 text-[14px] leading-5 text-ink-2">{decision.note}</p>
          ) : null}
          {investigation.work_order_id ? (
            <Link
              href={workOrderHref(investigation.work_order_id, investigation.investigation_id)}
              className="press mt-3 inline-flex h-9 items-center rounded-full bg-ink px-4 text-[14px] font-[560] text-canvas no-underline hover:bg-ink/92"
            >
              Work order {investigation.work_order_id}
            </Link>
          ) : null}
        </div>
      ) : investigation.status === "awaiting_decision" && example ? (
        <div
          role="note"
          data-example-note
          className="mt-8 flex flex-wrap items-center justify-between gap-x-5 gap-y-3 rounded-[16px] bg-surface-2 py-3.5 pr-3.5 pl-4 sm:pl-5"
        >
          <p className="flex max-w-[64ch] items-start gap-3 text-[14px] leading-5 text-ink-2">
            <HistoryIcon
              aria-hidden="true"
              className="mt-px size-[18px] shrink-0 text-ink-3"
              strokeWidth={1.8}
            />
            <span>
              This recorded example is the same for every visitor, so nobody decides it. To decide a
              report of your own, run a sample on the line and investigate one of its alarms.
            </span>
          </p>
          <Button asChild size="sm" variant="outline">
            <Link href={lineHref()}>Open the line</Link>
          </Button>
        </div>
      ) : investigation.status === "awaiting_decision" && !canAct ? (
        <div className="mt-8 flex flex-wrap items-center justify-between gap-3 rounded-[16px] bg-surface-2 py-3 pr-3 pl-4 sm:pl-5">
          <p className="text-[14px] leading-5 text-ink-2">
            Approving or rejecting a report needs an engineer session.
          </p>
          <Button
            size="sm"
            variant="outline"
            onClick={() => guest.mutate()}
            disabled={guest.isPending}
          >
            {guest.isPending ? "Signing in…" : "Try as engineer"}
          </Button>
        </div>
      ) : open ? (
        <div className="mt-8 grid grid-cols-[minmax(0,1fr)] gap-4 rounded-[16px] bg-surface-2 p-4 sm:p-5">
          <div className="grid grid-cols-[minmax(0,1fr)] gap-1.5">
            <Label htmlFor={noteId} className="text-[13px] text-ink-2">
              Note for the work order (optional)
            </Label>
            <Textarea
              id={noteId}
              value={note}
              maxLength={2000}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              className="bg-surface"
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              disabled={chosen.size === 0 || decide.isPending}
              onClick={() =>
                decide.mutate({
                  verdict: "approve",
                  actions: [...chosen].sort((a, b) => a - b),
                  note: note.trim() || null,
                })
              }
            >
              {decide.isPending && decide.variables?.verdict === "approve"
                ? "Approving…"
                : `Approve ${plural(chosen.size, "action")}`}
            </Button>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="outline" disabled={decide.isPending}>
                  Reject report
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Reject this report?</AlertDialogTitle>
                  <AlertDialogDescription>
                    No work order is opened. The report and its evidence stay on record, marked as
                    rejected.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Keep it open</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={() =>
                      decide.mutate({ verdict: "reject", actions: [], note: note.trim() || null })
                    }
                  >
                    Reject report
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
            <p className="text-[13px] leading-5 text-ink-3">
              Approving opens one work order with the chosen actions.
            </p>
          </div>
        </div>
      ) : null}
    </div>
  );
}
