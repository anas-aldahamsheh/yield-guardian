import "server-only";

import { QueryClient, dehydrate, type DehydratedState } from "@tanstack/react-query";
import { connection } from "next/server";

import { createApi } from "./client";
import { serverApiOrigin } from "./config";
import { q } from "./queries";

/**
 * The API as the Next.js server sees it. Requests are never cached and only happen at request
 * time: `connection()` keeps them out of the build, so a build never contains API data.
 */
export async function serverApi() {
  await connection();
  return createApi(serverApiOrigin(), { cache: "no-store", credentials: "omit" });
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
