"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { InvestigationTrigger } from "@yield-guardian/contracts";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { unwrap } from "./client";
import { useApi } from "./context";
import { describeError } from "./errors";
import { useSession } from "./session";

/** Starts an investigation from an alarm, unit, wafer or lot and opens it. */
export function useStartInvestigation() {
  const api = useApi();
  const client = useQueryClient();
  const router = useRouter();
  const { csrf } = useSession();
  return useMutation({
    mutationFn: (trigger: InvestigationTrigger) =>
      unwrap(api.POST("/api/v1/investigations", { body: { trigger }, headers: csrf })),
    onSuccess: (investigation) => {
      void client.invalidateQueries({ queryKey: ["investigations"] });
      void client.invalidateQueries({ queryKey: ["alarms"] });
      router.push(`/investigations/${investigation.investigation_id}`);
    },
    onError: (error) => {
      const copy = describeError(error);
      toast.error(copy.title, { description: copy.detail });
    },
  });
}
