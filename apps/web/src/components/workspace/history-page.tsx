"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { PageFrame, PageHeader } from "@/components/page";
import { DRAFT_KEYS, writeDraft } from "@/lib/live/drafts";
import { lineQuery, type LineUrlState } from "@/lib/live/url-state";

import { YourWork } from "./your-work";

export function HistoryPage() {
  const router = useRouter();
  const queryClient = useQueryClient();

  useEffect(() => {
    void queryClient.invalidateQueries({ queryKey: ["workspace", "runs"] });
  }, [queryClient]);

  const handleOpen = (view: LineUrlState) => {
    if (view.runId) {
      writeDraft(DRAFT_KEYS.activeRun, view.runId);
    }
    writeDraft(DRAFT_KEYS.way, null);
    const query = lineQuery(view);
    const url = query ? `/?${query}` : "/";
    router.push(url);
  };

  return (
    <PageFrame>
      <PageHeader
        title="Run History &amp; Workspace"
        description="Inspect previous fab production runs, compare sensor excursions, and revisit ongoing root-cause investigations."
      />
      <div className="mt-6">
        <YourWork
          current={{ runId: null, station: null, focus: null, alarm: null }}
          onOpen={handleOpen}
          vertical
        />
      </div>
    </PageFrame>
  );
}
