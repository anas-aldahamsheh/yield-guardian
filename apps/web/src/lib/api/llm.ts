"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { RoleAssignment, RoleAssignmentUpdate } from "@yield-guardian/contracts";
import { toast } from "@/lib/toast";

import { unwrap } from "./client";
import { useApi } from "./context";
import { describeError } from "./errors";
import { useSession } from "./session";

type Role = RoleAssignment["role"];

/** Assigns a model to a role (admins). The API applies it from the next call. */
export function useAssignRole() {
  const api = useApi();
  const client = useQueryClient();
  const { csrf } = useSession();
  return useMutation({
    mutationFn: ({ role, body }: { role: Role; body: RoleAssignmentUpdate }) =>
      unwrap(api.PUT("/api/v1/llm/roles/{role}", { params: { path: { role } }, body, headers: csrf })),
    onSuccess: (assignment) => {
      client.setQueryData<RoleAssignment[]>(["llm", "roles"], (prev) =>
        prev?.map((a) => (a.role === assignment.role ? assignment : a)),
      );
      void client.invalidateQueries({ queryKey: ["llm", "roles"] });
      void client.invalidateQueries({ queryKey: ["audit"] });
      toast.success("Role updated", { description: `${assignment.model_id} answers from the next call.` });
    },
    onError: (error) => {
      const copy = describeError(error);
      toast.error(copy.title, { description: copy.detail });
    },
  });
}
