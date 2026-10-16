import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import type { Metadata } from "next";

import { AdminView } from "@/components/models/models-view";
import { AdminSessions } from "@/components/workspace/admin-sessions";
import { q } from "@/lib/api/queries";
import { serverApi, serverQueryClient } from "@/lib/api/server";

/**
 * Model role settings, moved off the main menu in v2, and the device sessions (admins only).
 * Not linked from the navigation and not indexed; the access rules are the API's: anyone may
 * read the roles, only an admin session may change them or see the sessions.
 */
export const metadata: Metadata = {
  title: "Model roles",
  description: "Model roles, evaluations, today's usage and the model catalog.",
  robots: { index: false, follow: false },
};

export default async function AdminPage() {
  const api = await serverApi();
  const client = serverQueryClient();
  await Promise.all([
    client.prefetchQuery(q.llmRoles(api)),
    client.prefetchQuery(q.llmCatalog(api)),
  ]);
  return (
    <HydrationBoundary state={dehydrate(client)}>
      <AdminView />
      <AdminSessions />
    </HydrationBoundary>
  );
}
