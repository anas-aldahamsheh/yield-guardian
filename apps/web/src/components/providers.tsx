"use client";

import { QueryClient, QueryClientProvider, isServer } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import type { ReactNode } from "react";

import { LazyToaster } from "@/components/ui/lazy-toaster";
import { ApiProvider } from "@/lib/api/context";
import { retryDelay, shouldRetry } from "@/lib/api/retry";

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        // One policy for every read: wait while the API wakes (no answer, 5xx, 503 with
        // Retry-After), never ask again after a 4xx (lib/api/retry.ts).
        retry: shouldRetry,
        retryDelay,
      },
    },
  });
}

let browserClient: QueryClient | undefined;

/**
 * One query client for the page's life in the browser, so a remount of the providers (a
 * recovered render error, a layout that mounts again) keeps every cached answer instead of
 * asking the API again. The server makes one per request: answers never cross visitors.
 */
export function getQueryClient(): QueryClient {
  if (isServer) return makeQueryClient();
  browserClient ??= makeQueryClient();
  return browserClient;
}

export function Providers({ children, nonce }: { children: ReactNode; nonce?: string }) {
  const client = getQueryClient();
  return (
    <ThemeProvider
      attribute="data-theme"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
      nonce={nonce}
    >
      <ApiProvider>
        <QueryClientProvider client={client}>
          {children}
          <LazyToaster />
        </QueryClientProvider>
      </ApiProvider>
    </ThemeProvider>
  );
}
