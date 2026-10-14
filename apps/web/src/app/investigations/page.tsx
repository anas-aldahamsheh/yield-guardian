import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import type { Metadata } from "next";

import { InvestigationsList } from "@/components/investigation/investigations-list";
import { q } from "@/lib/api/queries";
import { serverApi, serverQueryClient } from "@/lib/api/server";

export const metadata: Metadata = {
  title: "Investigations",
  description: "Investigations of alarms, units, wafers and lots, with checked reports and decisions.",
};

export default async function InvestigationsPage() {
  const api = await serverApi();
  const client = serverQueryClient();
  await client.prefetchQuery(q.investigations(api, {}));
  return (
    <HydrationBoundary state={dehydrate(client)}>
      <InvestigationsList />
    </HydrationBoundary>
  );
}
