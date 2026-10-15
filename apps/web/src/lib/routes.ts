/**
 * Where things live in v2: three pages (Line at `/`, Investigations, How it works) and the
 * redirects that keep every v1 address working. Links in the product use these helpers, so a
 * page never links to an address that only a redirect resolves.
 */

/** The Line page's stations, numbered as the page draws them (PLAN_V2 §3.2). */
export const STATIONS = [
  "manufacturing",
  "monitoring",
  "wafer_test",
  "investigation",
  "decision",
] as const;
export type StationName = (typeof STATIONS)[number];
export type StationNumber = 1 | 2 | 3 | 4 | 5;

/** A real dataset item to open on the Line: a SECOM unit, a WM-811K wafer or a lot. */
export type Pick =
  { kind: "unit"; id: number } | { kind: "wafer"; id: string } | { kind: "lot"; id: string };

const WAFER_ID = /^[A-Za-z0-9_.]+-\d+$/;
const LOT_ID = /^[A-Za-z0-9_.]{1,64}$/;
const UNIT_ID = /^\d{1,6}$/;
const WORK_ORDER_ID = /^WO-\d{6}$/;

/** `unit:<unit id>`, `wafer:<lot>-<wafer index>`, `lot:<lot>`; null for anything else. */
export function parsePick(value: string | null | undefined): Pick | null {
  const m = /^(unit|wafer|lot):(.+)$/.exec(value ?? "");
  if (!m) return null;
  const [, kind, id] = m as unknown as [string, Pick["kind"], string];
  if (kind === "unit") return UNIT_ID.test(id) ? { kind, id: Number(id) } : null;
  if (kind === "wafer") return WAFER_ID.test(id) ? { kind, id } : null;
  return LOT_ID.test(id) ? { kind, id } : null;
}

export function pickValue(pick: Pick): string {
  return `${pick.kind}:${pick.id}`;
}

/** A path with its query; colons stay as written (RFC 3986 allows them), so picks read plainly. */
function withQuery(path: string, params: URLSearchParams): string {
  const query = params.toString().replaceAll("%3A", ":");
  return query ? `${path}?${query}` : path;
}

/** The Line, optionally at a station or with a real item picked. */
export function lineHref({ station, pick }: { station?: StationNumber; pick?: Pick } = {}): string {
  const params = new URLSearchParams();
  if (pick) params.set("pick", pickValue(pick));
  if (station) params.set("station", String(station));
  return withQuery("/", params);
}

/** A live run on the Line (the investigator's run alarms point here). */
export const runHref = (runId: string) => withQuery("/", new URLSearchParams({ run: runId }));

export const unitHref = (unitId: number) => lineHref({ pick: { kind: "unit", id: unitId } });
export const waferHref = (waferId: string) => lineHref({ pick: { kind: "wafer", id: waferId } });
export const lotHref = (lot: string) => lineHref({ pick: { kind: "lot", id: lot } });

/** A SECOM sensor on the Line's monitoring station. */
export function sensorHref(sensor: string): string {
  return withQuery("/", new URLSearchParams({ station: "2", sensor }));
}

export const investigationHref = (id: string) => `/investigations/${encodeURIComponent(id)}`;

/** The anchor of the work order section on an investigation page. */
export const WORK_ORDER_ANCHOR = "work-order";

/**
 * A work order: inside the investigation that owns it when that is known, otherwise in the
 * Work orders tab with the order opened.
 */
export function workOrderHref(workOrderId: string, investigationId?: string | null): string {
  if (investigationId) return `${investigationHref(investigationId)}#${WORK_ORDER_ANCHOR}`;
  return withQuery(
    "/investigations",
    new URLSearchParams({ tab: "work-orders", order: workOrderId }),
  );
}

export const workOrdersHref = () => "/investigations?tab=work-orders";

/** The sections of How it works: the plain Arabic part, then the expert part, then the guide. */
export const HOW_ANCHORS = [
  "what",
  "sources",
  "limits",
  "experts",
  "results",
  "models",
  "methods",
  "data",
  "calculator",
  "guide",
] as const;
export type HowAnchor = (typeof HOW_ANCHORS)[number];

export const howHref = (anchor?: HowAnchor) => (anchor ? `/how#${anchor}` : "/how");

/**
 * The v2 address of a v1 page, or null when the path is not a v1 page. Query strings are kept;
 * a v1 parameter that names an item (`?wafer=<id>` on the wafer lab) becomes a pick.
 * `/work-orders/<id>` is resolved by its route handler, which looks the order up first; this
 * function gives its fallback.
 */
export function legacyRedirect(pathname: string, search: URLSearchParams): string | null {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  const params = new URLSearchParams(search);
  // Next.js adds _rsc to client navigations as a cache key; it is not part of the address.
  params.delete("_rsc");
  const at = (target: string, extra: Record<string, string>, drop: string[] = []) => {
    const next = new URLSearchParams(extra);
    for (const [key, value] of params)
      if (!drop.includes(key) && !(key in extra)) next.append(key, value);
    return withQuery(target, next);
  };
  const segment = (prefix: string) => {
    const m = new RegExp(`^${prefix}/([^/]+)$`).exec(path);
    if (!m) return null;
    try {
      return decodeURIComponent(m[1]!);
    } catch {
      return null;
    }
  };

  if (path === "/line") return at("/", {});
  if (path === "/wafers") {
    const wafer = params.get("wafer");
    if (wafer && WAFER_ID.test(wafer)) return at("/", { pick: `wafer:${wafer}` }, ["wafer"]);
    return at("/", { station: "3" });
  }
  if (path === "/lots") return at("/", { station: "3" });
  if (path === "/sensors") return at("/", { station: "2" });
  if (path === "/work-orders") return at("/investigations", { tab: "work-orders" });
  if (path === "/models") return withQuery("/how", params) + "#models";
  if (path === "/methods") return withQuery("/how", params) + "#methods";
  if (path === "/guide") return withQuery("/how", params) + "#guide";

  const wafer = segment("/wafers");
  if (wafer != null) return at("/", { pick: `wafer:${wafer}` });
  const lot = segment("/lots");
  if (lot != null) return at("/", { pick: `lot:${lot}` });
  const unit = segment("/units");
  if (unit != null) return at("/", { pick: `unit:${unit}` });
  const order = segment("/work-orders");
  if (order != null) return at("/investigations", { tab: "work-orders", order });
  return null;
}

/**
 * Where an investigation's trigger lives on the Line: the run of a run alarm (`<run_id>:<alarm_id>`),
 * or the real unit, wafer or lot.
 */
export function triggerHref(trigger: { kind: string; ref: string }): string | null {
  const { kind, ref } = trigger;
  if (kind === "run_alarm") {
    const run = /^(run_[0-9a-z]{8,40}):/.exec(ref)?.[1];
    return run ? runHref(run) : null;
  }
  const unit = kind === "alarm" ? ref.match(/^AL-(\d+)-/)?.[1] : kind === "unit" ? ref : null;
  if (unit && /^\d+$/.test(unit)) return unitHref(Number(unit));
  if (kind === "wafer") return waferHref(ref);
  if (kind === "lot") return lotHref(ref);
  return null;
}

export function isWorkOrderId(value: string): boolean {
  return WORK_ORDER_ID.test(value);
}
