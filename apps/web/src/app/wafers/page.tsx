import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import type { Metadata } from "next";
import { Suspense } from "react";

import { Placeholder } from "@/components/states";
import { WaferLab } from "@/components/wafer/wafer-lab";
import { q } from "@/lib/api/queries";
import { serverApi, serverQueryClient } from "@/lib/api/server";

export const metadata: Metadata = {
  title: "Wafer lab",
  description: "Wafer maps with their pattern, an unknown-pattern check, a clustering test and similar wafers.",
};

export default async function WaferLabPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const params = await searchParams;
  const api = await serverApi();
  const client = serverQueryClient();
  const filter = {
    ...(params.label ? { label: params.label as never } : {}),
    ...(params.unknown === "1" ? { unknown: true } : {}),
    limit: 100,
  };
  await Promise.all([
    client.prefetchQuery(q.wafers(api, filter)),
    params.wafer ? client.prefetchQuery(q.wafer(api, params.wafer)) : null,
  ]);
  return (
    <HydrationBoundary state={dehydrate(client)}>
      <Suspense fallback={<Placeholder className="m-8 h-96" label="Loading the wafer lab" />}>
        <WaferLab />
      </Suspense>
    </HydrationBoundary>
  );
}
