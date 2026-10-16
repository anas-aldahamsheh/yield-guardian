"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import type { AdminSession } from "@yield-guardian/contracts";
import { LockKeyholeIcon } from "lucide-react";
import { useState } from "react";

import { LocalDateTime } from "@/components/local-date-time";
import { PageFrame, Panel } from "@/components/page";
import { ScrollRegion } from "@/components/scroll-region";
import { EmptyState, Placeholder, QueryView } from "@/components/states";
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
import { useApi } from "@/lib/api/context";
import { useSession } from "@/lib/api/session";
import { useRevokeSession, wq } from "@/lib/api/workspace";
import { formatInt, plural } from "@/lib/format";
import { ACTOR_ROLE } from "@/lib/labels";

/** What a session's workspace holds, in words. */
function holds(s: AdminSession): string[] {
  return [
    s.runs ? plural(s.runs, "run") : null,
    s.uploads ? plural(s.uploads, "upload") : null,
    s.investigations ? plural(s.investigations, "investigation") : null,
  ].filter((x): x is string => x != null);
}

/**
 * Device sessions, for the admin: each one's role, when it began and was last used, what its
 * workspace holds (counts only: an admin never sees another visitor's runs or files), and a way
 * to end it. No cookie value or token is ever shown; the API does not send them.
 */
export function AdminSessions() {
  const api = useApi();
  const { isAdmin, loading } = useSession();
  const sessions = useInfiniteQuery({
    ...wq.sessions(api),
    enabled: isAdmin,
    refetchOnWindowFocus: true,
  });
  const revoke = useRevokeSession();
  const [ending, setEnding] = useState<AdminSession | null>(null);
  const first = sessions.data?.pages[0];

  return (
    <PageFrame className="pt-0">
      <Panel
        title="Device sessions"
        description={
          first
            ? `${plural(first.total, "active session")} in ${plural(first.workspaces, "workspace")}. Every visitor is a separate user with a workspace of its own; devices joined with a code share one.`
            : "Every visitor is a separate user with a workspace of its own; devices joined with a code share one."
        }
        bodyClassName="px-0 sm:px-0"
      >
        {loading ? (
          <Placeholder className="mx-4 h-40 sm:mx-6" label="Loading sessions" />
        ) : !isAdmin ? (
          <p className="mx-4 flex items-start gap-2.5 rounded-[14px] bg-surface-2 px-4 py-3 text-[14px] leading-5 text-ink-2 sm:mx-6">
            <LockKeyholeIcon
              aria-hidden="true"
              className="mt-px size-4 shrink-0 text-ink-3"
              strokeWidth={1.8}
            />
            Only an admin sees device sessions. Sign in as an admin from the top bar.
          </p>
        ) : (
          <QueryView
            query={sessions}
            loading={<Placeholder className="mx-4 h-56 sm:mx-6" label="Loading sessions" />}
          >
            {(data) => {
              const rows = data.pages.flatMap((page) => page.items);
              if (!rows.length)
                return (
                  <EmptyState
                    className="unexposed mx-4 border-solid bg-surface sm:mx-6"
                    title="No active sessions"
                  >
                    No device has used the site within its session&apos;s life.
                  </EmptyState>
                );
              return (
                <>
                  <ScrollRegion label="Device sessions">
                    <table className="w-full min-w-[980px] border-collapse text-left text-[14px] leading-5">
                      <caption className="sr-only">Device sessions</caption>
                      <thead>
                        <tr className="border-y border-hairline text-[12.5px] leading-4 text-ink-3">
                          <th scope="col" className="py-3 pr-3 pl-4 font-[520] sm:pl-6">
                            Session
                          </th>
                          <th scope="col" className="px-3 py-3 font-[520]">
                            Workspace
                          </th>
                          <th scope="col" className="px-3 py-3 font-[520]">
                            Began
                          </th>
                          <th scope="col" className="px-3 py-3 font-[520]">
                            Last used
                          </th>
                          <th scope="col" className="px-3 py-3 font-[520]">
                            Ends
                          </th>
                          <th scope="col" className="px-3 py-3 font-[520]">
                            Holds
                          </th>
                          <th scope="col" className="py-3 pr-4 pl-3 text-right font-[520] sm:pr-6">
                            <span className="sr-only">Actions</span>
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((s) => (
                          <tr
                            key={s.session_id}
                            aria-current={s.current ? "true" : undefined}
                            className="border-b border-hairline transition-colors duration-(--dur-1) last:border-b-0 hover:bg-surface-2 aria-[current]:bg-signal-wash aria-[current]:shadow-[inset_3px_0_0_var(--signal)]"
                          >
                            <th
                              scope="row"
                              className="py-3.5 pr-3 pl-4 align-top font-[420] sm:pl-6"
                            >
                              <span className="font-[600] text-ink">
                                {ACTOR_ROLE[s.role] ?? s.role}
                              </span>
                              {s.display_name ? (
                                <span className="text-ink-2">{` ${s.display_name}`}</span>
                              ) : null}
                              <span className="tnum mt-0.5 block text-[12.5px] leading-4 text-ink-3">
                                {s.session_id.slice(0, 8)}
                                {s.current ? " · this session" : null}
                              </span>
                            </th>
                            <td className="tnum px-3 py-3.5 align-top text-ink-2">
                              {s.workspace_id ? s.workspace_id.slice(0, 8) : "None"}
                              <span className="mt-0.5 block text-[12.5px] leading-4 text-ink-3">
                                {plural(s.devices, "device")}
                              </span>
                            </td>
                            <td className="tnum px-3 py-3.5 align-top text-ink-2">
                              <LocalDateTime iso={s.created_at} />
                            </td>
                            <td className="tnum px-3 py-3.5 align-top text-ink-2">
                              <LocalDateTime iso={s.last_seen_at} />
                            </td>
                            <td className="tnum px-3 py-3.5 align-top text-ink-2">
                              <LocalDateTime iso={s.expires_at} />
                              {s.role_expires_at ? (
                                <span className="mt-0.5 block text-[12.5px] leading-4 text-ink-3">
                                  {"Role until "}
                                  <LocalDateTime iso={s.role_expires_at} />
                                </span>
                              ) : null}
                            </td>
                            <td className="tnum px-3 py-3.5 align-top text-ink-2">
                              {holds(s).join(", ") || "Nothing yet"}
                            </td>
                            <td className="py-3 pr-4 pl-3 text-right align-top sm:pr-6">
                              <Button
                                size="sm"
                                variant="outline"
                                disabled={s.current}
                                aria-label={`End session ${s.session_id.slice(0, 8)}`}
                                onClick={() => setEnding(s)}
                              >
                                End
                              </Button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </ScrollRegion>
                  {sessions.hasNextPage ? (
                    <div className="px-4 pt-4 sm:px-6">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={sessions.isFetchingNextPage}
                        onClick={() => void sessions.fetchNextPage()}
                      >
                        {sessions.isFetchingNextPage
                          ? "Reading more sessions"
                          : `Show more (${formatInt(first?.total ?? 0)} in all)`}
                      </Button>
                    </div>
                  ) : null}
                </>
              );
            }}
          </QueryView>
        )}
      </Panel>

      <AlertDialog open={ending != null} onOpenChange={(open) => !open && setEnding(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>End this device session?</AlertDialogTitle>
            <AlertDialogDescription>
              {ending
                ? `The device goes on as a new visitor, with an empty workspace, the next time it opens a page. ${
                    ending.devices > 1
                      ? `Its workspace stays with the other ${plural(ending.devices - 1, "device")}.`
                      : holds(ending).length
                        ? `No other device uses its workspace, so its ${holds(ending).join(", ")} are deleted at the next cleanup, within minutes.`
                        : "Its workspace holds nothing."
                  }`
                : null}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep it</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={revoke.isPending}
              onClick={(event) => {
                event.preventDefault();
                if (!ending) return;
                revoke.mutate(ending.session_id, { onSettled: () => setEnding(null) });
              }}
            >
              {revoke.isPending ? "Ending" : "End the session"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageFrame>
  );
}
