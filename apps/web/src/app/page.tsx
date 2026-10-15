import type { Metadata } from "next";

import { LinePage } from "@/components/story/line-page";

export const metadata: Metadata = {
  title: { absolute: "Line – Yield Guardian" },
  description:
    "Run real SECOM sensor units and WM-811K wafer maps, or your own data, through the line and watch each station compute its result.",
};

/** The URL keys the Line page reads; anything else in the query is ignored. */
const KEYS = ["run", "station", "unit", "wafer", "lot", "pick"] as const;

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
  return <LinePage initialQuery={query.toString()} />;
}
