"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import type {
  DecisionCreate,
  Investigation,
  InvestigationTrigger,
} from "@yield-guardian/contracts";
import { useRouter } from "next/navigation";
import { toast } from "@/lib/toast";

import { unwrap } from "./client";
import { useApi } from "./context";
import { describeError } from "./errors";
import { NOT_CONFIGURED } from "./features";
import { q } from "./queries";
import { useSession } from "./session";

/** The server runs without a language model key, so it cannot run an investigation. */
class NotConfigured extends Error {}

/** Starts an investigation from an alarm, unit, wafer or lot and opens it. */
export function useStartInvestigation() {
  const api = useApi();
  const client = useQueryClient();
  const router = useRouter();
  const { csrf } = useSession();
  return useMutation({
    mutationFn: async (trigger: InvestigationTrigger) => {
      // Without a language model key the API would accept the run and fail it at once: say so
      // instead, and leave no failed run behind. When /meta is unreadable, let the API decide.
      const meta = await client.fetchQuery(q.meta(api)).catch(() => null);
      if (meta && !meta.features.live_investigations) throw new NotConfigured();
      return unwrap(api.POST("/api/v1/investigations", { body: { trigger }, headers: csrf }));
    },
    onSuccess: (investigation) => {
      void client.invalidateQueries({ queryKey: ["investigations"] });
      void client.invalidateQueries({ queryKey: ["alarms"] });
      router.push(`/investigations/${investigation.investigation_id}`);
    },
    onError: (error) => {
      const copy =
        error instanceof NotConfigured ? NOT_CONFIGURED.investigations : describeError(error);
      toast.error(copy.title, { description: copy.detail });
    },
  });
}

/**
 * Stops a queued or running investigation: no further model calls are made, its evidence so far
 * is kept and no report is written. The run ends as failed, "Stopped by the user".
 */
export function useStopInvestigation(investigationId: string) {
  const api = useApi();
  const client = useQueryClient();
  const { csrf } = useSession();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/investigations/{investigation_id}/stop", {
          params: { path: { investigation_id: investigationId } },
          headers: csrf,
        }),
      ),
    onSuccess: (investigation) => {
      client.setQueryData<Investigation>(["investigations", investigationId], investigation);
      void client.invalidateQueries({ queryKey: ["investigations"] });
      void client.invalidateQueries({ queryKey: ["alarms"] });
      toast("Investigation stopped", { description: "Its evidence so far is kept." });
    },
    onError: (error) => {
      // Already finished (409) or gone: show where it stands now.
      void client.invalidateQueries({ queryKey: ["investigations"] });
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
