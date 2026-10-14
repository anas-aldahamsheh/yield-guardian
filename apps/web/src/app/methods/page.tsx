import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import type { Metadata } from "next";

import { MethodsView } from "@/components/methods/methods-view";
import { q } from "@/lib/api/queries";
import { serverApi, serverQueryClient } from "@/lib/api/server";

export const metadata: Metadata = {
  title: "Methods",
  description: "Every reported number with its confidence interval, data and source; datasets, bundles, model cards and limitations.",
};

export default async function MethodsPage() {
  const api = await serverApi();
  const client = serverQueryClient();
  await Promise.all([client.prefetchQuery(q.results(api)), client.prefetchQuery(q.secomMetrics(api)), client.prefetchQuery(q.waferMetrics(api))]);
  return (
    <HydrationBoundary state={dehydrate(client)}>
      <MethodsView />
    </HydrationBoundary>
  );
}
