"use client";

import { useEffect } from "react";

import { toasterSlot } from "@/lib/toast";

import { Toaster } from "./sonner";

/** The Toaster, loaded on its own; it reports when it listens (its own effects run first). */
export default function MountedToaster() {
  useEffect(() => toasterSlot.mounted(), []);
  // Toasts drop in under the top bar, centred: clear of the Ask button and of the chat sheet's
  // question field, which both sit at the bottom, and on a wide screen clear of the open sheet.
  return (
    <Toaster
      position="top-center"
      offset={{ top: "calc(var(--bar-height) + 12px)" }}
      mobileOffset={{ top: "calc(var(--bar-height) + 8px)", right: 16, left: 16 }}
    />
  );
}
