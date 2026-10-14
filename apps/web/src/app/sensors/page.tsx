import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import type { Metadata } from "next";
import { Suspense } from "react";

import { SensorHealthView } from "@/components/sensors/sensor-health-view";
import { Placeholder } from "@/components/states";
import { q } from "@/lib/api/queries";
import { serverApi, serverQueryClient } from "@/lib/api/server";

export const metadata: Metadata = {
  title: "Sensor health",
  description: "Health of every SECOM sensor by written rules, and the sensor groups associated with failure.",
};

export default async function SensorsPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const params = await searchParams;
  const api = await serverApi();
  const client = serverQueryClient();
  const sensor = params.sensor && /^S\d{3}$/.test(params.sensor) ? params.sensor : null;
  await Promise.all([
    client.prefetchQuery(q.sensorHealth(api)),
    client.prefetchQuery(q.sensorGroups(api, { significant_only: false, limit: 50 })),
    sensor ? client.prefetchQuery(q.sensorSeries(api, sensor)) : null,
  ]);
  return (
    <HydrationBoundary state={dehydrate(client)}>
      <Suspense fallback={<Placeholder className="m-8 h-96" label="Loading sensor health" />}>
        <SensorHealthView />
      </Suspense>
    </HydrationBoundary>
  );
}
