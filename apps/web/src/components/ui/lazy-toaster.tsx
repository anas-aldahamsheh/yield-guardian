"use client";

import dynamic from "next/dynamic";
import { useEffect, useSyncExternalStore } from "react";

import { afterLoadIdle } from "@/lib/idle";
import { toasterSlot } from "@/lib/toast";

const MountedToaster = dynamic(() => import("./toaster-mounted"), {
  ssr: false,
  loading: () => null,
});

/** Mounts the Toaster when the page is idle or at the first toast, whichever comes first. */
export function LazyToaster() {
  const wanted = useSyncExternalStore(toasterSlot.subscribe, toasterSlot.wanted, () => false);
  useEffect(() => afterLoadIdle(() => toasterSlot.request(), 4000), []);
  return wanted ? <MountedToaster /> : null;
}
