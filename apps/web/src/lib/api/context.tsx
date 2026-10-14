"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";

import { type Api, createApi } from "./client";
import { BROWSER_API_BASE } from "./config";

interface ApiContextValue {
  api: Api;
}

const ApiContext = createContext<ApiContextValue | null>(null);

/** Gives client components the API client; the browser always calls its own origin. */
export function ApiProvider({ children }: { children: ReactNode }) {
  const value = useMemo(() => ({ api: createApi(BROWSER_API_BASE) }), []);
  return <ApiContext.Provider value={value}>{children}</ApiContext.Provider>;
}

function useApiContext(): ApiContextValue {
  const value = useContext(ApiContext);
  if (!value) throw new Error("useApi must be used inside <ApiProvider>");
  return value;
}

export function useApi(): Api {
  return useApiContext().api;
}
