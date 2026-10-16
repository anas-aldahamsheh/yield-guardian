import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import type { Metadata } from "next";

import { InvestigationView } from "@/components/investigation/investigation-view";
import { DirectionalPage } from "@/components/page-transition";
import { q } from "@/lib/api/queries";
import { serverApi, serverQueryClient } from "@/lib/api/server";

export const metadata: Metadata = { title: "Investigation" };

export default async function InvestigationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const api = await serverApi();
  const client = serverQueryClient();
  await client.prefetchQuery(q.investigation(api, id));
  return (
    <DirectionalPage>
      <HydrationBoundary state={dehydrate(client)}>
        <InvestigationView id={id} />
      </HydrationBoundary>
    </DirectionalPage>
  );
}
