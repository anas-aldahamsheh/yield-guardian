import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import type { Metadata } from "next";

import { LotView } from "@/components/lot/lot-view";
import { q } from "@/lib/api/queries";
import { serverApi, serverQueryClient } from "@/lib/api/server";

export async function generateMetadata({ params }: { params: Promise<{ lot: string }> }): Promise<Metadata> {
  const { lot } = await params;
  return { title: `Lot ${decodeURIComponent(lot)}` };
}

export default async function LotPage({ params }: { params: Promise<{ lot: string }> }) {
  const lot = decodeURIComponent((await params).lot);
  const api = await serverApi();
  const client = serverQueryClient();
  await client.prefetchQuery(q.lot(api, lot));
  return (
    <HydrationBoundary state={dehydrate(client)}>
      <LotView lot={lot} />
    </HydrationBoundary>
  );
}
