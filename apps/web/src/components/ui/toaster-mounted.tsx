"use client";

import { useEffect } from "react";

import { toasterSlot } from "@/lib/toast";

import { Toaster } from "./sonner";

/** The Toaster, loaded on its own; it reports when it listens (its own effects run first). */
export default function MountedToaster() {
  useEffect(() => toasterSlot.mounted(), []);
  return <Toaster position="bottom-right" />;
}
