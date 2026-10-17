"use client";

import {
  infiniteQueryOptions,
  queryOptions,
  useMutation,
  useQueryClient,
  type InfiniteData,
  type QueryClient,
} from "@tanstack/react-query";
import {
  API_PREFIX,
  type HandoffCreated,
  type RunCreated,
  type SessionInfo,
  type WorkRun,
  type WorkRunPage,
  type WorkRunUpdate,
} from "@yield-guardian/contracts";

import { toast } from "@/lib/toast";

import { type Api, csrfHeaders, unwrap } from "./client";
import { useApi } from "./context";
import { describeError } from "./errors";
import { openWorkspace } from "./opening";
import { useSession } from "./session";

/**
 * This device's workspace: its runs with their live status, the handoff to another device, and
 * the admin's view of device sessions. Every visitor is a separate user without signing in: the
 * API keeps what a device makes in its workspace and shows it to that workspace only.
 *
 * Query keys start with "workspace" (or "admin"), so a change of workspace refreshes them all.
 */

const SESSION_KEY = ["session"];
const PAGE = 20;

export { openWorkspace, workspaceReady } from "./opening";

/** Puts the session the API answered with in the cache (an answer still on its way is dropped). */
export async function setSession(client: QueryClient, session: SessionInfo) {
  await client.cancelQueries({ queryKey: SESSION_KEY });
  client.setQueryData<SessionInfo>(SESSION_KEY, session);
}

/** The CSRF headers of this device's session, opening it first if the page has not yet. */
async function csrfOf(session: SessionInfo): Promise<Record<string, string>> {
  if (session.csrf_token) return csrfHeaders(session.csrf_token);
  return csrfHeaders((await openWorkspace())?.csrf_token);
}

/** The code from a join link (`/join#code=…`): after `#`, so no server ever receives it. */
export function codeFromHash(hash: string): string | null {
  const match = /(?:^#|&)code=([^&]*)/.exec(hash);
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]!).slice(0, 24);
  } catch {
    return null;
  }
}

export const resultsCsvHref = (runId: string) =>
  `${API_PREFIX}/runs/${encodeURIComponent(runId)}/results.csv`;

export const reportHref = (investigationId: string) =>
  `${API_PREFIX}/investigations/${encodeURIComponent(investigationId)}/report.md`;

/** A run is still computing, or an investigation started from it is. */
export function isLive(run: WorkRun): boolean {
  return (
    run.status === "queued" ||
    run.status === "running" ||
    run.investigations.some((i) => i.status === "queued" || i.status === "running")
  );
}

export const wq = {
  summary: (api: Api) =>
    queryOptions({
      queryKey: ["workspace", "summary"],
      queryFn: ({ signal }) => unwrap(api.GET("/api/v1/workspace", { signal })),
      staleTime: 30_000,
    }),

  /** This workspace's runs, newest first, a page at a time; `archived` lists the archived ones. */
  runs: (api: Api, archived = false) =>
    infiniteQueryOptions({
      queryKey: ["workspace", "runs", archived],
      initialPageParam: null as string | null,
      queryFn: ({ pageParam, signal }) =>
        unwrap(
          api.GET("/api/v1/workspace/runs", {
            params: {
              query: { archived, limit: PAGE, ...(pageParam ? { cursor: pageParam } : {}) },
            },
            signal,
          }),
        ),
      getNextPageParam: (last) => last.next_cursor ?? undefined,
      staleTime: 0,
    }),

  compare: (api: Api, runId: string, otherId: string) =>
    queryOptions({
      queryKey: ["workspace", "compare", runId, otherId],
      queryFn: ({ signal }) =>
        unwrap(
          api.GET("/api/v1/runs/{run_id}/compare/{other_id}", {
            params: { path: { run_id: runId, other_id: otherId } },
            signal,
          }),
        ),
    }),

  /** Active device sessions, most recently used first (admins only). */
  sessions: (api: Api) =>
    infiniteQueryOptions({
      queryKey: ["admin", "sessions"],
      initialPageParam: null as string | null,
      queryFn: ({ pageParam, signal }) =>
        unwrap(
          api.GET("/api/v1/admin/sessions", {
            params: { query: { limit: 50, ...(pageParam ? { cursor: pageParam } : {}) } },
            signal,
          }),
        ),
      getNextPageParam: (last) => last.next_cursor ?? undefined,
    }),
};

type RunPages = InfiniteData<WorkRunPage, string | null>;

/** Replaces one run in every cached list it is in. */
function putRun(client: QueryClient, run: WorkRun) {
  client.setQueriesData<RunPages>({ queryKey: ["workspace", "runs"] }, (data) =>
    data
      ? {
          ...data,
          pages: data.pages.map((page) => ({
            ...page,
            items: page.items.map((item) => (item.run_id === run.run_id ? run : item)),
          })),
        }
      : data,
  );
}

function failed(error: unknown) {
  const copy = describeError(error);
  toast.error(copy.title, { description: copy.detail });
}

/** Names a run, notes on it, archives or restores it, or saves the view it reopens on. */
export function useUpdateWorkRun({ quiet = false }: { quiet?: boolean } = {}) {
  const api = useApi();
  const client = useQueryClient();
  const { session } = useSession();
  return useMutation({
    mutationFn: async ({ runId, body }: { runId: string; body: WorkRunUpdate }) =>
      unwrap(
        api.PATCH("/api/v1/workspace/runs/{run_id}", {
          params: { path: { run_id: runId } },
          body,
          headers: await csrfOf(session),
        }),
      ),
    onSuccess: (run, { body }) => {
      putRun(client, run);
      if (body.archived !== undefined && body.archived !== null) {
        void client.invalidateQueries({ queryKey: ["workspace"] });
      }
    },
    onError: quiet ? undefined : failed,
  });
}

/**
 * Deletes a run for good, with its results, alarms and the investigations started from it, on
 * every device of the workspace.
 */
export function useDeleteWorkRun() {
  const api = useApi();
  const client = useQueryClient();
  const { session } = useSession();
  return useMutation({
    mutationFn: async (runId: string) =>
      unwrap(
        api.DELETE("/api/v1/workspace/runs/{run_id}", {
          params: { path: { run_id: runId } },
          headers: await csrfOf(session),
        }),
      ),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["workspace"] }),
  });
}

/** Runs the same input again as a new run; the earlier run is kept. */
export function useRunAgain() {
  const api = useApi();
  const client = useQueryClient();
  const { session } = useSession();
  return useMutation({
    mutationFn: async (runId: string): Promise<RunCreated> =>
      unwrap(
        api.POST("/api/v1/runs/{run_id}/again", {
          params: { path: { run_id: runId } },
          headers: await csrfOf(session),
        }),
      ),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["workspace"] }),
    onError: failed,
  });
}

/** A single-use code that attaches another device to this workspace for a few minutes. */
export function useCreateHandoff() {
  const api = useApi();
  const { session } = useSession();
  return useMutation({
    mutationFn: async (): Promise<HandoffCreated> =>
      unwrap(api.POST("/api/v1/workspace/handoffs", { headers: await csrfOf(session) })),
  });
}

/** After this device changed workspace: what it sees is all different, so read it all again. */
async function switched(client: QueryClient, session: SessionInfo) {
  await setSession(client, session);
  await client.invalidateQueries({ predicate: (query) => query.queryKey[0] !== "session" });
}

/** Attaches this device to the workspace that made `code`. */
export function useJoinWorkspace() {
  const api = useApi();
  const client = useQueryClient();
  const { session } = useSession();
  return useMutation({
    mutationFn: async (code: string) =>
      unwrap(
        api.POST("/api/v1/workspace/join", { body: { code }, headers: await csrfOf(session) }),
      ),
    onSuccess: (joined) => switched(client, joined),
  });
}

/** Moves this device to a new, empty workspace; other devices keep the old one. */
export function useFreshWorkspace() {
  const api = useApi();
  const client = useQueryClient();
  const { session } = useSession();
  return useMutation({
    mutationFn: async () =>
      unwrap(api.POST("/api/v1/workspace/fresh", { headers: await csrfOf(session) })),
    onSuccess: (moved) => switched(client, moved),
    onError: failed,
  });
}

/** Ends a device session now (admins only). */
export function useRevokeSession() {
  const api = useApi();
  const client = useQueryClient();
  const { csrf } = useSession();
  return useMutation({
    mutationFn: (sessionId: string) =>
      unwrap(
        api.DELETE("/api/v1/admin/sessions/{session_id}", {
          params: { path: { session_id: sessionId } },
          headers: csrf,
        }),
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["admin", "sessions"] });
      void client.invalidateQueries({ queryKey: ["audit"] });
      toast.success("Session ended", {
        description: "That device goes on as a new visitor the next time it opens a page.",
      });
    },
    onError: failed,
  });
}
