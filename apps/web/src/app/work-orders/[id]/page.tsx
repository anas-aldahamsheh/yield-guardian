import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { WorkOrderView } from "@/components/work-orders/work-order-view";
import { q } from "@/lib/api/queries";
import { serverApi, serverQueryClient } from "@/lib/api/server";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  return { title: `Work order ${id}` };
}

export default async function WorkOrderPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^WO-\d{6}$/.test(id)) notFound();
  const api = await serverApi();
  const client = serverQueryClient();
  await client.prefetchQuery(q.workOrder(api, id));
  return (
    <HydrationBoundary state={dehydrate(client)}>
      <WorkOrderView id={id} />
    </HydrationBoundary>
  );
}
