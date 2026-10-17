"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { SessionInfo } from "@yield-guardian/contracts";
import { toast } from "@/lib/toast";

import { csrfHeaders, unwrap } from "./client";
import { useApi } from "./context";
import { describeError } from "./errors";
import { readSession } from "./opening";
import { q } from "./queries";

const VISITOR: SessionInfo = {
  role: "visitor",
  display_name: null,
  expires_at: null,
  csrf_token: null,
};

/**
 * The current session; a visitor until the API says otherwise. The page's first read of it is
 * the answer of opening this device's workspace (lib/api/opening.ts): one request on a first
 * visit, and `loading` until the workspace is open.
 */
export function useSession() {
  const api = useApi();
  const query = useQuery({
    ...q.session(api),
    queryFn: ({ signal }) => readSession(() => unwrap(api.GET("/api/v1/session", { signal }))),
  });
  const session = query.data ?? VISITOR;
  return {
    session,
    loading: query.isPending,
    canAct: true,
    isAdmin: session.role === "admin",
    csrf: csrfHeaders(session.csrf_token),
  };
}

function useSetSession() {
  const client = useQueryClient();
  return (session: SessionInfo) => {
    client.setQueryData<SessionInfo>(SESSION_KEY, session);
  };
}

const SESSION_KEY = ["session"];

/** "Try as engineer": an engineer session that can approve, reject and ask. */
export function useStartGuestSession() {
  const api = useApi();
  const setSession = useSetSession();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/session/guest", { body: {} })),
    onSuccess: (session) => {
      setSession(session);
    },
    onError: (error) =>
      toast.error(describeError(error).title, { description: describeError(error).detail }),
  });
}

export function useLogin() {
  const api = useApi();
  const setSession = useSetSession();
  return useMutation({
    mutationFn: (body: { username: string; password: string }) =>
      unwrap(api.POST("/api/v1/session/login", { body })),
    onSuccess: (session) => {
      setSession(session);
      toast.success("Signed in as admin");
    },
  });
}

export function useLogout() {
  const api = useApi();
  const setSession = useSetSession();
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/session/logout")),
    onSuccess: () => {
      setSession(VISITOR);
      void client.invalidateQueries({ queryKey: ["session"] });
      toast("Signed out");
    },
    onError: (error) =>
      toast.error(describeError(error).title, { description: describeError(error).detail }),
  });
}
