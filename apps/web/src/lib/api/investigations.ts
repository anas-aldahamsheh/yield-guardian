"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { DecisionCreate, Investigation, InvestigationTrigger } from "@yield-guardian/contracts";
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

/** Approves (some of) a report's actions, which opens a work order, or rejects the report. */
export function useDecideInvestigation(investigationId: string) {
  const api = useApi();
  const client = useQueryClient();
  const { csrf } = useSession();
  return useMutation({
    mutationFn: (body: DecisionCreate) =>
      unwrap(
        api.POST("/api/v1/investigations/{investigation_id}/decision", {
          params: { path: { investigation_id: investigationId } },
          body,
          headers: csrf,
        }),
      ),
    onSuccess: (investigation) => {
      client.setQueryData<Investigation>(["investigations", investigationId], investigation);
      void client.invalidateQueries({ queryKey: ["investigations", "list"] });
      void client.invalidateQueries({ queryKey: ["work-orders"] });
      void client.invalidateQueries({ queryKey: ["audit"] });
      if (investigation.decision?.verdict === "approve") {
        toast.success("Approved", {
          description: investigation.work_order_id
            ? `Work order ${investigation.work_order_id} is open.`
            : "The approved actions are recorded.",
        });
      } else {
        toast("Rejected", { description: "The report is kept, marked as rejected." });
      }
    },
    onError: (error) => {
      const copy = describeError(error);
      toast.error(copy.title, { description: copy.detail });
    },
  });
}
