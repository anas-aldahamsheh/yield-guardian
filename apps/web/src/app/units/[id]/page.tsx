import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { UnitView } from "@/components/unit/unit-view";
import { q } from "@/lib/api/queries";
import { serverApi, serverQueryClient } from "@/lib/api/server";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  return { title: `Unit ${id}` };
}

export default async function UnitPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^\d{1,6}$/.test(id)) notFound();
  const unitId = Number(id);
  const api = await serverApi();
  const client = serverQueryClient();
  await Promise.all([client.prefetchQuery(q.unit(api, unitId)), client.prefetchQuery(q.explanation(api, unitId))]);
  return (
    <HydrationBoundary state={dehydrate(client)}>
      <UnitView unitId={unitId} />
    </HydrationBoundary>
  );
}
