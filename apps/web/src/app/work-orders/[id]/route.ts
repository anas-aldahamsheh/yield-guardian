import { serverApi } from "@/lib/api/server";
import { isWorkOrderId, legacyRedirect, workOrderHref } from "@/lib/routes";

/**
 * A v1 work order address. Work orders now live inside the investigation that opened them, so
 * this looks the order up and redirects there (permanently: an order never changes its
 * investigation). When the API cannot say, it redirects to the Work orders tab with the order
 * opened. The Location is relative, so it is right behind any gateway.
 */
export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const url = new URL(request.url);
  let target = legacyRedirect(url.pathname, url.searchParams) ?? "/investigations?tab=work-orders";
  if (isWorkOrderId(id)) {
    try {
      const api = await serverApi();
      const { data } = await api.GET("/api/v1/work-orders/{work_order_id}", {
        params: { path: { work_order_id: id } },
      });
      if (data) target = workOrderHref(data.work_order_id, data.investigation_id);
    } catch {
      // The API did not answer: the Work orders tab still finds the order.
    }
  }
  return new Response(null, { status: 308, headers: { Location: target, "Cache-Control": "no-store" } });
}
