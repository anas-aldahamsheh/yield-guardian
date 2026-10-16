import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";
import type { paths } from "@yield-guardian/contracts";

import { type Api, unwrap } from "./client";

/**
 * Query definitions for every read of the API, shared by server prefetching and client hooks so
 * both use the same keys. Pass the API client of the side that runs the query.
 */

const MINUTE = 60_000;

type Range = { from_seq?: number | null; to_seq?: number | null };

/** Query parameters of a GET operation, straight from the contract. */
export type QueryOf<P extends keyof paths> = paths[P] extends {
  get: { parameters: { query?: infer Q } };
}
  ? NonNullable<Q>
  : never;

export const q = {
  /** What the API serves (bundles, features): read once and kept for the page's life. */
  meta: (api: Api) =>
    queryOptions({
      queryKey: ["meta"],
      queryFn: ({ signal }) => unwrap(api.GET("/api/v1/meta", { signal })),
      staleTime: Infinity,
      gcTime: Infinity,
    }),

  results: (api: Api) =>
    queryOptions({
      queryKey: ["results"],
      queryFn: ({ signal }) => unwrap(api.GET("/api/v1/results", { signal })),
      staleTime: 5 * MINUTE,
    }),

  heroWafer: (api: Api) =>
    queryOptions({
      queryKey: ["wafers", "hero"],
      queryFn: ({ signal }) => unwrap(api.GET("/api/v1/wafers/hero", { signal })),
      staleTime: 30 * MINUTE,
    }),

  /**
   * Who this browser is: read once, then kept until something changes it (starting a session,
   * signing in or out sets or reloads it: lib/api/session.ts).
   */
  session: (api: Api) =>
    queryOptions({
      queryKey: ["session"],
      queryFn: ({ signal }) => unwrap(api.GET("/api/v1/session", { signal })),
      staleTime: Infinity,
      gcTime: Infinity,
    }),

  fdcSeries: (api: Api, range: Range = {}) =>
    queryOptions({
      queryKey: ["fdc", "series", range.from_seq ?? null, range.to_seq ?? null],
      queryFn: ({ signal }) =>
        unwrap(api.GET("/api/v1/fdc/series", { params: { query: range }, signal })),
    }),

  /** Control limits and method of the FDC model: the series of its first unit, which carries them. */
  fdcModel: (api: Api) =>
    queryOptions({
      queryKey: ["fdc", "model"],
      queryFn: ({ signal }) =>
        unwrap(
          api.GET("/api/v1/fdc/series", { params: { query: { from_seq: 0, to_seq: 0 } }, signal }),
        ),
      staleTime: 30 * MINUTE,
    }),

  alarms: (api: Api, query: QueryOf<"/api/v1/alarms"> = {}) =>
    queryOptions({
      queryKey: ["alarms", query],
      queryFn: ({ signal }) => unwrap(api.GET("/api/v1/alarms", { params: { query }, signal })),
    }),

  units: (api: Api, query: QueryOf<"/api/v1/units"> = {}) =>
    queryOptions({
      queryKey: ["units", query],
      queryFn: ({ signal }) => unwrap(api.GET("/api/v1/units", { params: { query }, signal })),
    }),

  unit: (api: Api, unitId: number) =>
    queryOptions({
      queryKey: ["units", unitId],
      queryFn: ({ signal }) =>
        unwrap(
          api.GET("/api/v1/units/{unit_id}", { params: { path: { unit_id: unitId } }, signal }),
        ),
    }),

  explanation: (api: Api, unitId: number, top = 15) =>
    queryOptions({
      queryKey: ["units", unitId, "explanation", top],
      queryFn: ({ signal }) =>
        unwrap(
          api.GET("/api/v1/units/{unit_id}/explanation", {
            params: { path: { unit_id: unitId }, query: { top } },
            signal,
          }),
        ),
      staleTime: 30 * MINUTE,
    }),

  contributions: (api: Api, unitId: number, statistic: "t2" | "spe", top = 15) =>
    queryOptions({
      queryKey: ["units", unitId, "contributions", statistic, top],
      queryFn: ({ signal }) =>
        unwrap(
          api.GET("/api/v1/units/{unit_id}/contributions", {
            params: { path: { unit_id: unitId }, query: { statistic, top } },
            signal,
          }),
        ),
      staleTime: 30 * MINUTE,
    }),

  sensorGroups: (api: Api, query: { significant_only?: boolean; limit?: number } = {}) =>
    queryOptions({
      queryKey: ["sensors", "groups", query],
      queryFn: ({ signal }) =>
        unwrap(api.GET("/api/v1/sensors/groups", { params: { query }, signal })),
      staleTime: 30 * MINUTE,
    }),

  sensorHealth: (api: Api) =>
    queryOptions({
      queryKey: ["sensors", "health"],
      queryFn: ({ signal }) => unwrap(api.GET("/api/v1/sensors/health", { signal })),
      staleTime: 5 * MINUTE,
    }),

  sensorSeries: (api: Api, sensor: string, range: Range = {}) =>
    queryOptions({
      queryKey: ["sensors", sensor, "series", range.from_seq ?? null, range.to_seq ?? null],
      queryFn: ({ signal }) =>
        unwrap(
          api.GET("/api/v1/sensors/{sensor}/series", {
            params: { path: { sensor }, query: range },
            signal,
          }),
        ),
    }),

  operatingPoints: (api: Api) =>
    queryOptions({
      queryKey: ["secom", "operating-points"],
      queryFn: ({ signal }) => unwrap(api.GET("/api/v1/secom/operating-points", { signal })),
      staleTime: 30 * MINUTE,
    }),

  investigations: (api: Api, query: QueryOf<"/api/v1/investigations"> = {}) =>
    queryOptions({
      queryKey: ["investigations", "list", query],
      queryFn: ({ signal }) =>
        unwrap(api.GET("/api/v1/investigations", { params: { query }, signal })),
    }),

  /** Every investigation, newest first, a page at a time (the grouped list on Investigations). */
  investigationPages: (api: Api, limit = 100) =>
    infiniteQueryOptions({
      queryKey: ["investigations", "list", "pages", limit],
      initialPageParam: null as string | null,
      queryFn: ({ pageParam, signal }) =>
        unwrap(
          api.GET("/api/v1/investigations", {
            params: { query: { limit, ...(pageParam ? { cursor: pageParam } : {}) } },
            signal,
          }),
        ),
      getNextPageParam: (last) => last.next_cursor ?? undefined,
    }),

  investigation: (api: Api, investigationId: string) =>
    queryOptions({
      queryKey: ["investigations", investigationId],
      queryFn: ({ signal }) =>
        unwrap(
          api.GET("/api/v1/investigations/{investigation_id}", {
            params: { path: { investigation_id: investigationId } },
            signal,
          }),
        ),
    }),

  evidence: (api: Api, investigationId: string, evidenceId: string) =>
    queryOptions({
      queryKey: ["investigations", investigationId, "evidence", evidenceId],
      queryFn: ({ signal }) =>
        unwrap(
          api.GET("/api/v1/investigations/{investigation_id}/evidence/{evidence_id}", {
            params: { path: { investigation_id: investigationId, evidence_id: evidenceId } },
            signal,
          }),
        ),
      staleTime: Infinity,
    }),

  workOrders: (api: Api, query: { cursor?: string | null; limit?: number } = {}) =>
    queryOptions({
      queryKey: ["work-orders", "list", query],
      queryFn: ({ signal }) =>
        unwrap(api.GET("/api/v1/work-orders", { params: { query }, signal })),
    }),

  /** Every work order, newest first, a page at a time (the Work orders tab). */
  workOrderPages: (api: Api, limit = 50) =>
    infiniteQueryOptions({
      queryKey: ["work-orders", "list", "pages", limit],
      initialPageParam: null as string | null,
      queryFn: ({ pageParam, signal }) =>
        unwrap(
          api.GET("/api/v1/work-orders", {
            params: { query: { limit, ...(pageParam ? { cursor: pageParam } : {}) } },
            signal,
          }),
        ),
      getNextPageParam: (last) => last.next_cursor ?? undefined,
    }),

  workOrder: (api: Api, workOrderId: string) =>
    queryOptions({
      queryKey: ["work-orders", workOrderId],
      queryFn: ({ signal }) =>
        unwrap(
          api.GET("/api/v1/work-orders/{work_order_id}", {
            params: { path: { work_order_id: workOrderId } },
            signal,
          }),
        ),
    }),

  audit: (api: Api, query: QueryOf<"/api/v1/audit"> = {}) =>
    queryOptions({
      queryKey: ["audit", query],
      queryFn: ({ signal }) => unwrap(api.GET("/api/v1/audit", { params: { query }, signal })),
    }),

  wafers: (api: Api, query: QueryOf<"/api/v1/wafers"> = {}) =>
    queryOptions({
      queryKey: ["wafers", "list", query],
      queryFn: ({ signal }) => unwrap(api.GET("/api/v1/wafers", { params: { query }, signal })),
      staleTime: 30 * MINUTE,
    }),

  wafer: (api: Api, waferId: string) =>
    queryOptions({
      queryKey: ["wafers", waferId],
      queryFn: ({ signal }) =>
        unwrap(
          api.GET("/api/v1/wafers/{wafer_id}", { params: { path: { wafer_id: waferId } }, signal }),
        ),
      staleTime: 30 * MINUTE,
    }),

  similarWafers: (api: Api, waferId: string, k = 10) =>
    queryOptions({
      queryKey: ["wafers", waferId, "similar", k],
      queryFn: ({ signal }) =>
        unwrap(
          api.GET("/api/v1/wafers/{wafer_id}/similar", {
            params: { path: { wafer_id: waferId }, query: { k } },
            signal,
          }),
        ),
      staleTime: 30 * MINUTE,
    }),

  lots: (
    api: Api,
    query: { flagged_only?: boolean; cursor?: string | null; limit?: number } = {},
  ) =>
    queryOptions({
      queryKey: ["lots", "list", query],
      queryFn: ({ signal }) => unwrap(api.GET("/api/v1/lots", { params: { query }, signal })),
      staleTime: 30 * MINUTE,
    }),

  lot: (api: Api, lot: string) =>
    queryOptions({
      queryKey: ["lots", lot],
      queryFn: ({ signal }) =>
        unwrap(api.GET("/api/v1/lots/{lot}", { params: { path: { lot } }, signal })),
      staleTime: 30 * MINUTE,
    }),

  knowledgeSearch: (api: Api, text: string, limit = 5) =>
    queryOptions({
      queryKey: ["knowledge", "search", text, limit],
      queryFn: ({ signal }) =>
        unwrap(
          api.GET("/api/v1/knowledge/search", { params: { query: { q: text, limit } }, signal }),
        ),
      staleTime: 30 * MINUTE,
    }),

  patternCauses: (api: Api, label?: QueryOf<"/api/v1/knowledge/patterns">["label"]) =>
    queryOptions({
      queryKey: ["knowledge", "patterns", label ?? null],
      queryFn: ({ signal }) =>
        unwrap(api.GET("/api/v1/knowledge/patterns", { params: { query: { label } }, signal })),
      staleTime: 30 * MINUTE,
    }),

  llmCatalog: (api: Api) =>
    queryOptions({
      queryKey: ["llm", "catalog"],
      queryFn: ({ signal }) => unwrap(api.GET("/api/v1/llm/catalog", { signal })),
      staleTime: 5 * MINUTE,
    }),

  llmRoles: (api: Api) =>
    queryOptions({
      queryKey: ["llm", "roles"],
      queryFn: ({ signal }) => unwrap(api.GET("/api/v1/llm/roles", { signal })),
    }),

  llmUsage: (api: Api) =>
    queryOptions({
      queryKey: ["llm", "usage"],
      queryFn: ({ signal }) => unwrap(api.GET("/api/v1/llm/usage", { signal })),
    }),

  llmEvaluations: (api: Api) =>
    queryOptions({
      queryKey: ["llm", "evaluations"],
      queryFn: ({ signal }) => unwrap(api.GET("/api/v1/llm/evaluations", { signal })),
      staleTime: 5 * MINUTE,
    }),

  methods: (api: Api) =>
    queryOptions({
      queryKey: ["methods"],
      queryFn: ({ signal }) => unwrap(api.GET("/api/v1/methods", { signal })),
      staleTime: 30 * MINUTE,
    }),

  secomMetrics: (api: Api) =>
    queryOptions({
      queryKey: ["methods", "secom"],
      queryFn: ({ signal }) => unwrap(api.GET("/api/v1/methods/secom", { signal })),
      staleTime: 30 * MINUTE,
    }),

  waferMetrics: (api: Api) =>
    queryOptions({
      queryKey: ["methods", "wafermap"],
      queryFn: ({ signal }) => unwrap(api.GET("/api/v1/methods/wafermap", { signal })),
      staleTime: 30 * MINUTE,
    }),

  modelCard: (api: Api, name: "secom" | "wafermap") =>
    queryOptions({
      queryKey: ["methods", "model-card", name],
      queryFn: ({ signal }) =>
        unwrap(
          api.GET("/api/v1/methods/model-cards/{name}", { params: { path: { name } }, signal }),
        ),
      staleTime: 30 * MINUTE,
    }),
};
