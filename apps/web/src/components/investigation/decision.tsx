"use client";

import type { Investigation, Report } from "@yield-guardian/contracts";
import Link from "next/link";
import { useId, useState } from "react";

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
import { formatDateTime, plural } from "@/lib/format";
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
  const open = investigation.status === "awaiting_decision" && canAct;
  const decision = investigation.decision;

  const toggle = (i: number) =>
    setChosen((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });

  return (
    <div className="mt-2">
      <ol className="grid grid-cols-[minmax(0,1fr)] gap-4">
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
                  className="mt-[7px] size-4 cursor-pointer accent-[var(--ink)]"
                />
              ) : (
                <span className="tnum pt-[5px] text-[13px] leading-5 text-ink-3">{i + 1}.</span>
              )}
              <div className="min-w-0">
                <ActionBody action={action} index={i} {...shared} />
                {decision ? (
                  <p className="mt-1 text-[13px] leading-5 text-ink-3">{approved ? "Approved" : "Not approved"}</p>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>

      {decision ? (
        <div className={cn("swap-in mt-6 rounded-sm border-l-2 px-4 py-3", decision.verdict === "approve" ? "border-pass bg-pass-wash" : "border-ink bg-die-2")}>
          <p className="text-[15px] leading-6 text-ink">
            {decision.verdict === "approve"
              ? `Approved ${plural(decision.actions.length, "action")}`
              : "Rejected"}{" "}
            by {decision.decided_by}, {formatDateTime(decision.decided_at)}.
          </p>
          {decision.note ? <p className="mt-1 text-[14px] leading-5 text-ink-2">{decision.note}</p> : null}
          {investigation.work_order_id ? (
            <Link
              href={`/work-orders/${investigation.work_order_id}`}
              className="mt-2 inline-block text-[14px] text-ink underline decoration-hairline-strong underline-offset-4 hover:decoration-ink"
            >
              Work order {investigation.work_order_id}
            </Link>
          ) : null}
        </div>
      ) : investigation.status === "awaiting_decision" && !canAct ? (
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-sm bg-die-2 px-4 py-3">
          <p className="text-[14px] leading-5 text-ink-2">Approving or rejecting a report needs an engineer session.</p>
          <Button size="sm" variant="outline" onClick={() => guest.mutate()} disabled={guest.isPending}>
            {guest.isPending ? "Signing in…" : "Try as engineer"}
          </Button>
        </div>
      ) : open ? (
        <div className="mt-6 grid grid-cols-[minmax(0,1fr)] gap-3 rounded-sm bg-die-2 px-4 py-4">
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
              className="bg-die"
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              disabled={chosen.size === 0 || decide.isPending}
              onClick={() =>
                decide.mutate({ verdict: "approve", actions: [...chosen].sort((a, b) => a - b), note: note.trim() || null })
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
                    No work order is opened. The report and its evidence stay on record, marked as rejected.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Keep it open</AlertDialogCancel>
                  <AlertDialogAction onClick={() => decide.mutate({ verdict: "reject", actions: [], note: note.trim() || null })}>
                    Reject report
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
            <p className="text-[13px] leading-5 text-ink-3">Approving opens one work order with the chosen actions.</p>
          </div>
        </div>
      ) : null}
    </div>
  );
}
