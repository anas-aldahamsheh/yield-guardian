import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import type { Metadata } from "next";

import { InvestigationsPage } from "@/components/investigation/investigations-page";
import { DirectionalPage } from "@/components/page-transition";
import { q } from "@/lib/api/queries";
import { serverApi, serverQueryClient } from "@/lib/api/server";
import { isWorkOrderId } from "@/lib/routes";

export const metadata: Metadata = {
  title: "Work orders",
  description: "Work orders opened by approved investigations, with their actions, status and audit log.",
};

export default async function WorkOrdersRoute({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const order =
    typeof params.order === "string" && isWorkOrderId(params.order) ? params.order : null;
  const api = await serverApi();
  const client = serverQueryClient();
  await Promise.all([
    client.prefetchInfiniteQuery(q.workOrderPages(api)),
    order ? client.prefetchQuery(q.workOrder(api, order)) : null,
  ]);
  return (
    <DirectionalPage>
      <HydrationBoundary state={dehydrate(client)}>
        <InvestigationsPage tab="work-orders" order={order} />
      </HydrationBoundary>
    </DirectionalPage>
  );
}
