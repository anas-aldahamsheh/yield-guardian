import type { APIRequestContext } from "@playwright/test";

/** Reads the real API through the gateway, so the tests pick IDs that exist in the loaded bundles. */
export async function getJson<T>(request: APIRequestContext, path: string): Promise<T> {
  const response = await request.get(`/api/v1${path}`);
  if (!response.ok()) throw new Error(`GET ${path}: ${response.status()} ${await response.text()}`);
  return (await response.json()) as T;
}

type Page<T> = { items: T[]; total: number };

export async function discover(request: APIRequestContext) {
  const alarms = await getJson<Page<{ unit_id: number; alarm_id: string }>>(
    request,
    "/alarms?limit=1",
  );
  const units = await getJson<Page<{ unit_id: number }>>(request, "/units?limit=1");
  const lots = await getJson<Page<{ lot: string; wafers: number }>>(request, "/lots?limit=1");
  const wafers = await getJson<Page<{ wafer_id: string }>>(request, "/wafers?limit=1");
  const workOrders = await getJson<Page<{ work_order_id: string }>>(
    request,
    "/work-orders?limit=1",
  );
  // Every visitor lists its own investigations (none for this new one) and, apart from them,
  // the product's example: the recorded investigation the API seeds at startup.
  const investigations = await getJson<
    Page<{ investigation_id: string }> & { examples: { investigation_id: string }[] }
  >(request, "/investigations?limit=1");
  return {
    unit: alarms.items[0]?.unit_id ?? units.items[0]!.unit_id,
    lot: lots.items[0]!.lot,
    wafer: wafers.items[0]!.wafer_id,
    workOrder: workOrders.items[0]?.work_order_id ?? null,
    investigation:
      investigations.items[0]?.investigation_id ??
      investigations.examples[0]?.investigation_id ??
      null,
  };
}
