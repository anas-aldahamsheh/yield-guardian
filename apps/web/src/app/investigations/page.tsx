import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import type { Metadata } from "next";

import {
  InvestigationsPage,
  type InvestigationsTab,
} from "@/components/investigation/investigations-page";
import { q } from "@/lib/api/queries";
import { serverApi, serverQueryClient } from "@/lib/api/server";
import { isWorkOrderId } from "@/lib/routes";

export const metadata: Metadata = {
  title: "Investigations",
  description:
    "Investigations of alarms, with checked reports, hypotheses, decisions and the work orders they opened.",
};

export default async function InvestigationsRoute({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const tab: InvestigationsTab = params.tab === "work-orders" ? "work-orders" : "investigations";
  const order =
    typeof params.order === "string" && isWorkOrderId(params.order) ? params.order : null;
  const api = await serverApi();
  const client = serverQueryClient();
  if (tab === "work-orders") {
    await Promise.all([
      client.prefetchInfiniteQuery(q.workOrderPages(api)),
      order ? client.prefetchQuery(q.workOrder(api, order)) : null,
    ]);
  } else {
    await client.prefetchInfiniteQuery(q.investigationPages(api));
  }
  return (
    <HydrationBoundary state={dehydrate(client)}>
      <InvestigationsPage tab={tab} order={tab === "work-orders" ? order : null} />
    </HydrationBoundary>
  );
}
