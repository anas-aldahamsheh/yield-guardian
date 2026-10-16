import "server-only";

import { QueryClient, dehydrate, type DehydratedState } from "@tanstack/react-query";
import { SESSION_COOKIE } from "@yield-guardian/contracts";
import { cookies } from "next/headers";
import { connection } from "next/server";

import { createApi } from "./client";
import { serverApiOrigin } from "./config";
import { q } from "./queries";

/**
 * The `cookie` header of a request the Next.js server makes to the API for the browser being
 * served: its session cookie and no other cookie of the browser's. Every visitor is a separate
 * user, so the API answers with that device's workspace, exactly as it answers the browser.
 */
export async function sessionCookieHeader(): Promise<{ cookie: string } | undefined> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  return token ? { cookie: `${SESSION_COOKIE}=${token}` } : undefined;
}

/**
 * The API as the Next.js server sees it. Requests are never cached and only happen at request
 * time: `connection()` keeps them out of the build, so a build never contains API data.
 *
 * The browser's session cookie goes with each request (sessionCookieHeader): lists belong to the
 * workspace of the device asking, so a page rendered on the server shows that device's own
 * investigations and work orders, as the browser will.
 */
export async function serverApi() {
  await connection();
  return createApi(serverApiOrigin(), {
    cache: "no-store",
    credentials: "omit",
    headers: await sessionCookieHeader(),
  });
}

/** A query client for prefetching on the server; its successful queries are sent to the page. */
export function serverQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
  });
}

/**
 * What the API serves (/meta), read for the page being rendered and handed to the browser's
 * query client with it: the session control, the footer and the Investigate buttons render with
 * it at once, on the server and in the browser, and the browser does not ask for it again (it
 * is kept for the page's life). A slow or waking API holds the page no longer than `waitMs`;
 * the browser asks for it then.
 */
export async function metaState(waitMs = 1_500): Promise<DehydratedState> {
  const api = await serverApi();
  const client = serverQueryClient();
  let timer: ReturnType<typeof setTimeout> | undefined;
  await Promise.race([
    client.prefetchQuery(q.meta(api)),
    new Promise<void>((resolve) => {
      timer = setTimeout(resolve, waitMs);
    }),
  ]);
  clearTimeout(timer);
  // Only an answer is sent: a read still under way is dropped, and the browser makes its own.
  const state = dehydrate(client);
  await client.cancelQueries();
  return state;
}
