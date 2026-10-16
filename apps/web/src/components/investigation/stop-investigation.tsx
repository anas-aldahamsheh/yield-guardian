"use client";

import { SquareIcon } from "lucide-react";
import { useState } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { useStopInvestigation } from "@/lib/api/investigations";
import { useSession } from "@/lib/api/session";

/**
 * "Stop" on a queued or running investigation of one's own, confirmed in a small dialog. The
 * recorded example is the same for every visitor, so nobody stops it; a visitor without an
 * engineer session cannot either (the API refuses both).
 */
export function StopInvestigationButton({
  investigationId,
  recorded,
  title,
  size = "sm",
}: {
  investigationId: string;
  recorded: boolean;
  title: string;
  size?: "xs" | "sm";
}) {
  const { canAct } = useSession();
  const [open, setOpen] = useState(false);
  const stop = useStopInvestigation(investigationId);
  if (!canAct || recorded) return null;
  return (
    <>
      <Button
        variant="outline"
        size={size}
        aria-label={`Stop ${title}`}
        disabled={stop.isPending}
        onClick={() => setOpen(true)}
      >
        <SquareIcon aria-hidden="true" strokeWidth={2.2} />
        {stop.isPending ? "Stopping…" : "Stop"}
      </Button>
      <AlertDialog open={open} onOpenChange={setOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Stop this investigation?</AlertDialogTitle>
            <AlertDialogDescription>
              Its evidence so far is kept; no report is written.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep running</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={stop.isPending}
              onClick={(event) => {
                event.preventDefault();
                stop.mutate(undefined, { onSettled: () => setOpen(false) });
              }}
            >
              {stop.isPending ? "Stopping…" : "Stop investigation"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
