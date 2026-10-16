"use client";

import dynamic from "next/dynamic";

import { Placeholder } from "@/components/states";

/*
 * The two method tracks on /how, each fetched when its section first opens. Imported here, in a
 * client module, rather than by the page itself: a client component the page names is loaded
 * with the page even while its section is closed.
 */

export const SecomMethods = dynamic(
  () => import("@/components/methods/secom-methods").then((mod) => mod.SecomMethods),
  {
    loading: () => <Placeholder className="mx-4 h-72 sm:mx-5" label="Loading the SECOM methods" />,
  },
);

export const WaferMethods = dynamic(
  () => import("@/components/methods/wafer-methods").then((mod) => mod.WaferMethods),
  {
    loading: () => (
      <Placeholder className="mx-4 h-72 sm:mx-5" label="Loading the wafer-map methods" />
    ),
  },
);
