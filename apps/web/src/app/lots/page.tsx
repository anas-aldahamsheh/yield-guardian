import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import type { Metadata } from "next";

import { LotsList } from "@/components/lot/lots-list";
import { q } from "@/lib/api/queries";
import { serverApi, serverQueryClient } from "@/lib/api/server";

export const metadata: Metadata = { title: "Lots", description: "Wafer lots tested for patterns above their expected rate." };

export default async function LotsPage() {
  const api = await serverApi();
  const client = serverQueryClient();
  await client.prefetchQuery(q.lots(api, {}));
  return (
    <HydrationBoundary state={dehydrate(client)}>
      <LotsList />
    </HydrationBoundary>
  );
}
