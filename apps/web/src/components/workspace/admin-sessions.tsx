"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import type { AdminSession } from "@yield-guardian/contracts";
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
          <Placeholder className="mx-4 h-40 sm:mx-5" label="Loading sessions" />
        ) : !isAdmin ? (
          <p className="px-4 text-sm text-ink-2 sm:px-5">
            Only an admin sees device sessions. Sign in as an admin from the top bar.
          </p>
        ) : (
          <QueryView
            query={sessions}
            loading={<Placeholder className="mx-4 h-56 sm:mx-5" label="Loading sessions" />}
          >
            {(data) => {
              const rows = data.pages.flatMap((page) => page.items);
              if (!rows.length)
                return (
                  <EmptyState className="mx-4 sm:mx-5" title="No active sessions">
                    No device has used the site within its session&apos;s life.
                  </EmptyState>
                );
              return (
                <>
                  <ScrollRegion label="Device sessions">
                    <table className="w-full min-w-[980px] border-collapse text-left text-[14px] leading-5">
                      <caption className="sr-only">Device sessions</caption>
                      <thead>
                        <tr className="border-y border-hairline text-[12px] text-ink-3">
                          <th scope="col" className="px-4 py-2 font-normal sm:px-5">
                            Session
                          </th>
                          <th scope="col" className="px-2 py-2 font-normal">
                            Workspace
                          </th>
                          <th scope="col" className="px-2 py-2 font-normal">
                            Began
                          </th>
                          <th scope="col" className="px-2 py-2 font-normal">
                            Last used
                          </th>
                          <th scope="col" className="px-2 py-2 font-normal">
                            Ends
                          </th>
                          <th scope="col" className="px-2 py-2 font-normal">
                            Holds
                          </th>
                          <th scope="col" className="px-4 py-2 text-right font-normal sm:px-5">
                            <span className="sr-only">Actions</span>
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((s) => (
                          <tr
                            key={s.session_id}
                            className="border-b border-hairline last:border-b-0"
                          >
                            <th scope="row" className="px-4 py-2.5 align-top font-normal sm:px-5">
                              <span className="font-medium text-ink">
                                {ACTOR_ROLE[s.role] ?? s.role}
                              </span>
                              {s.display_name ? (
                                <span className="text-ink-2">{` ${s.display_name}`}</span>
                              ) : null}
                              <span className="tnum block text-[12px] text-ink-3">
                                {s.session_id.slice(0, 8)}
                                {s.current ? " · this session" : null}
                              </span>
                            </th>
                            <td className="tnum px-2 py-2.5 align-top text-ink-2">
                              {s.workspace_id ? s.workspace_id.slice(0, 8) : "None"}
                              <span className="block text-[12px] text-ink-3">
                                {plural(s.devices, "device")}
                              </span>
                            </td>
                            <td className="tnum px-2 py-2.5 align-top text-ink-2">
                              <LocalDateTime iso={s.created_at} />
                            </td>
                            <td className="tnum px-2 py-2.5 align-top text-ink-2">
                              <LocalDateTime iso={s.last_seen_at} />
                            </td>
                            <td className="tnum px-2 py-2.5 align-top text-ink-2">
                              <LocalDateTime iso={s.expires_at} />
                              {s.role_expires_at ? (
                                <span className="block text-[12px] text-ink-3">
                                  {"Role until "}
                                  <LocalDateTime iso={s.role_expires_at} />
                                </span>
                              ) : null}
                            </td>
                            <td className="tnum px-2 py-2.5 align-top text-ink-2">
                              {holds(s).join(", ") || "Nothing yet"}
                            </td>
                            <td className="px-4 py-2.5 text-right align-top sm:px-5">
                              <Button
                                size="sm"
                                variant="outline"
                                className="border-hairline-strong"
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
                    <div className="px-4 pt-3 sm:px-5">
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
