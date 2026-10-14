"use client";

/**
 * Toasts without loading sonner up front. The Toaster and sonner arrive in their own chunk once
 * the page is idle, or at the first toast, so neither is parsed before the first paint. A toast
 * raised before the Toaster has mounted waits for it, so it is never dropped.
 */

type Options = { description?: string };
type Kind = "message" | "success" | "error";

let wanted = false;
const listeners = new Set<() => void>();
let markMounted: () => void = () => {};
const mounted = new Promise<void>((resolve) => {
  markMounted = resolve;
});

export const toasterSlot = {
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  wanted: () => wanted,
  /** Asks for the Toaster to be mounted. */
  request() {
    if (wanted) return;
    wanted = true;
    listeners.forEach((l) => l());
  },
  /** Called by the Toaster once it listens for toasts. */
  mounted: () => markMounted(),
};

function show(kind: Kind, title: string, options?: Options) {
  toasterSlot.request();
  void Promise.all([import("sonner"), mounted]).then(([{ toast: t }]) => {
    if (kind === "message") t(title, options);
    else t[kind](title, options);
  });
}

export const toast = Object.assign((title: string, options?: Options) => show("message", title, options), {
  success: (title: string, options?: Options) => show("success", title, options),
  error: (title: string, options?: Options) => show("error", title, options),
});
