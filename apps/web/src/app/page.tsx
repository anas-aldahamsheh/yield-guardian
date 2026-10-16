import type { Metadata } from "next";

import { LinePage } from "@/components/story/line-page";
import { readStoredRun } from "@/lib/live/server-run";
import { parseLineUrl } from "@/lib/live/url-state";

export const metadata: Metadata = {
  title: { absolute: "Line – Yield Guardian" },
  description:
    "Run real SECOM sensor units and WM-811K wafer maps, or your own data, through the line and watch each station compute its result.",
};

/** The URL keys the Line page reads; anything else in the query is ignored. */
const KEYS = ["run", "station", "unit", "wafer", "lot", "alarm", "pick"] as const;

/**
 * The Line page. With a run in the address (a reload, a link, back and forward), the server reads
 * the run's stored state first, so the page arrives showing every result as it stands, with the
 * open station, the item in view and the chosen alarm: nothing replays and nothing is lost.
 */
export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const query = new URLSearchParams();
  for (const key of KEYS) {
    const value = params[key];
    const first = Array.isArray(value) ? value[0] : value;
    if (first != null) query.set(key, first);
  }
  const view = parseLineUrl(query);
  const stored = view.runId ? await readStoredRun(view.runId, view) : null;
  return <LinePage initialQuery={query.toString()} stored={stored} />;
}
