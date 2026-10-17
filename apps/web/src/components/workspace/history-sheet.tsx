"use client";

import { useQueryClient } from "@tanstack/react-query";
import { HistoryIcon } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { DRAFT_KEYS, writeDraft } from "@/lib/live/drafts";
import { lineQuery, type LineUrlState } from "@/lib/live/url-state";

import { YourWork } from "./your-work";

export function HistorySheet({
  open,
  onOpenChange,
  current = { runId: null, station: null, focus: null, alarm: null },
  onSelectRun,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  current?: LineUrlState;
  onSelectRun?: (view: LineUrlState, to?: "run" | "alarms") => void;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();

  useEffect(() => {
    if (open) {
      void queryClient.invalidateQueries({ queryKey: ["workspace", "runs"] });
    }
  }, [open, queryClient]);

  // Auto-close sheet when pathname changes (e.g., navigating to /join or /investigations)
  useEffect(() => {
    onOpenChange(false);
  }, [pathname, onOpenChange]);

  const handleOpen = (view: LineUrlState, to: "run" | "alarms" = "run") => {
    if (view.runId) {
      writeDraft(DRAFT_KEYS.activeRun, view.runId);
    }
    writeDraft(DRAFT_KEYS.way, null);
    onOpenChange(false);
    if (onSelectRun) {
      onSelectRun(view, to);
      return;
    }
    const query = lineQuery(view);
    const targetUrl = query ? `/?${query}` : "/";

    if (typeof window !== "undefined" && window.location.pathname === "/") {
      // Dispatches open event to current LinePage if mounted for immediate switch
      window.dispatchEvent(
        new CustomEvent("yg:open-run", {
          detail: { view, to },
        }),
      );
    } else {
      router.push(targetUrl);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="flex h-full w-full flex-col gap-0 p-0 sm:max-w-2xl lg:max-w-3xl"
      >
        <SheetHeader className="shrink-0 border-b border-hairline p-5">
          <SheetTitle className="flex items-center gap-2 text-[17px] font-[650] text-ink">
            <HistoryIcon className="size-4.5 text-ink-2" />
            <span>Run History &amp; Workspace</span>
          </SheetTitle>
          <SheetDescription className="text-[13px] text-ink-3">
            Quickly access and reload previous fab production runs, live computations, and investigations.
          </SheetDescription>
        </SheetHeader>
        <div
          onClick={(e) => {
            const anchor = (e.target as HTMLElement).closest("a");
            if (anchor && anchor.getAttribute("href")) {
              onOpenChange(false);
            }
          }}
          className="flex-1 min-h-0 overflow-y-auto overscroll-contain p-4 sm:p-6"
        >
          <YourWork current={current} onOpen={handleOpen} vertical />
        </div>
      </SheetContent>
    </Sheet>
  );
}
