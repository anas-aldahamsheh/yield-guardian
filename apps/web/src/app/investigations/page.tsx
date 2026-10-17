import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import type { Metadata } from "next";
import { redirect } from "next/navigation";

import {
  InvestigationsPage,
  type InvestigationsTab,
} from "@/components/investigation/investigations-page";
import { DirectionalPage } from "@/components/page-transition";
import { q } from "@/lib/api/queries";
import { serverApi, serverQueryClient } from "@/lib/api/server";
import { workOrderHref } from "@/lib/routes";

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
  // Work orders have their own page now.
  if (params.tab === "work-orders")
    redirect(typeof params.order === "string" ? workOrderHref(params.order) : "/work-orders");
  const tab: InvestigationsTab = "investigations";
  const api = await serverApi();
  const client = serverQueryClient();
  await client.prefetchInfiniteQuery(q.investigationPages(api));
  return (
    <DirectionalPage>
      <HydrationBoundary state={dehydrate(client)}>
        <InvestigationsPage tab={tab} order={null} />
      </HydrationBoundary>
    </DirectionalPage>
  );
}
