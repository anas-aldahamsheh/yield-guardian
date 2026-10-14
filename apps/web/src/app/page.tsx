import { HydrationBoundary, dehydrate } from "@tanstack/react-query";

import { Hero } from "@/components/home/hero";
import { InvestigationSequence } from "@/components/home/investigation-sequence";
import { Provenance } from "@/components/home/provenance";
import { ResultsLedger } from "@/components/home/results-ledger";
import { SmoothScroll } from "@/components/home/smooth-scroll";
import { q } from "@/lib/api/queries";
import { serverApi, serverQueryClient } from "@/lib/api/server";

export default async function HomePage() {
  const api = await serverApi();
  const client = serverQueryClient();
  await Promise.all([
    client.prefetchQuery(q.heroWafer(api)),
    client.prefetchQuery(q.results(api)),
    client.prefetchQuery(q.methods(api)),
    client.prefetchQuery(q.llmRoles(api)),
  ]);

  return (
    <HydrationBoundary state={dehydrate(client)}>
      <SmoothScroll />
      <Hero />
      <ResultsLedger />
      <InvestigationSequence />
      <Provenance />
    </HydrationBoundary>
  );
}
