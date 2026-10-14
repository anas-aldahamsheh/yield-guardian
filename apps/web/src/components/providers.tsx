"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useState, type ReactNode } from "react";

import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiProvider } from "@/lib/api/context";
import { ApiError } from "@/lib/api/errors";

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        // Retry only when the API might answer next time: no answer, or a server error.
        retry: (failures, error) =>
          failures < 2 && error instanceof ApiError && (error.status === 0 || error.status >= 500),
      },
    },
  });
}

export function Providers({ children, nonce }: { children: ReactNode; nonce?: string }) {
  const [client] = useState(makeQueryClient);
  return (
    <ThemeProvider attribute="data-theme" defaultTheme="system" enableSystem disableTransitionOnChange nonce={nonce}>
      <ApiProvider>
        <QueryClientProvider client={client}>
          <TooltipProvider delayDuration={300}>
            {children}
            <Toaster position="bottom-right" />
          </TooltipProvider>
        </QueryClientProvider>
      </ApiProvider>
    </ThemeProvider>
  );
}
