import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import type { Metadata } from "next";

import { ModelsView } from "@/components/models/models-view";
import { q } from "@/lib/api/queries";
import { serverApi, serverQueryClient } from "@/lib/api/server";

export const metadata: Metadata = {
  title: "Models",
  description: "Model roles, evaluations, today's usage and the model catalog.",
};

export default async function ModelsPage() {
  const api = await serverApi();
  const client = serverQueryClient();
  await Promise.all([client.prefetchQuery(q.llmRoles(api)), client.prefetchQuery(q.llmCatalog(api))]);
  return (
    <HydrationBoundary state={dehydrate(client)}>
      <ModelsView />
    </HydrationBoundary>
  );
}
