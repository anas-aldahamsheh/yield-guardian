import "server-only";

import { QueryClient } from "@tanstack/react-query";
import { connection } from "next/server";

import { createApi } from "./client";
import { serverApiOrigin } from "./config";

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
