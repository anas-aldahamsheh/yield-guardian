import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import type { Metadata } from "next";

import { HowView } from "@/components/how/how-view";
import { q } from "@/lib/api/queries";
import { serverApi, serverQueryClient } from "@/lib/api/server";

export const metadata: Metadata = {
  title: "How it works",
  description:
    "What Yield Guardian does, where its data comes from and what it cannot do, in plain Arabic; then every measured result, the models, the methods, the savings calculator and the guide.",
};

export default async function HowPage() {
  const api = await serverApi();
  const client = serverQueryClient();
  // What the page shows without a click: the plain limits, the results table, the role tables
  // and provenance. The method tracks and the model cards load when they are opened.
  await Promise.all([
    client.prefetchQuery(q.results(api)),
    client.prefetchQuery(q.secomMetrics(api)),
    client.prefetchQuery(q.operatingPoints(api)),
    client.prefetchQuery(q.methods(api)),
    client.prefetchQuery(q.llmRoles(api)),
    client.prefetchQuery(q.llmCatalog(api)),
    client.prefetchQuery(q.llmEvaluations(api)),
  ]);
  return (
    <HydrationBoundary state={dehydrate(client)}>
      <HowView />
    </HydrationBoundary>
  );
}
