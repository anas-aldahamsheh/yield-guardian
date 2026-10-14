"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { WorkOrder, WorkOrderUpdate } from "@yield-guardian/contracts";
import { toast } from "@/lib/toast";

import { unwrap } from "./client";
import { useApi } from "./context";
import { describeError } from "./errors";
import { useSession } from "./session";

/** Changes a work order's status, note, outcome or confirmation. Sends only the fields given. */
export function useUpdateWorkOrder(workOrderId: string) {
  const api = useApi();
  const client = useQueryClient();
  const { csrf } = useSession();
  return useMutation({
    mutationFn: (body: WorkOrderUpdate) =>
      unwrap(
        api.PATCH("/api/v1/work-orders/{work_order_id}", {
          params: { path: { work_order_id: workOrderId } },
          body,
          headers: csrf,
        }),
      ),
    onSuccess: (order) => {
      client.setQueryData<WorkOrder>(["work-orders", workOrderId], order);
      void client.invalidateQueries({ queryKey: ["work-orders", "list"] });
      void client.invalidateQueries({ queryKey: ["audit"] });
      toast.success("Saved", { description: `Work order ${order.work_order_id} is updated.` });
    },
    onError: (error) => {
      const copy = describeError(error);
      toast.error(copy.title, { description: copy.detail });
    },
  });
}
