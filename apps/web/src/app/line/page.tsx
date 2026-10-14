import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import type { Metadata } from "next";

import { LineView } from "@/components/line/line-view";
import { q } from "@/lib/api/queries";
import { serverApi, serverQueryClient } from "@/lib/api/server";
import { LINE_WINDOWS } from "@/lib/line/windows";

export const metadata: Metadata = {
  title: "Line",
  description: "Units leaving the line, with failure risk, control charts and open alarms.",
};

export default async function LinePage() {
  const api = await serverApi();
  const client = serverQueryClient();
  await Promise.all([
    client.prefetchQuery(q.lineState(api, LINE_WINDOWS[0])),
    client.prefetchQuery(q.fdcModel(api)),
  ]);
  return (
    <HydrationBoundary state={dehydrate(client)}>
      <LineView />
    </HydrationBoundary>
  );
}
