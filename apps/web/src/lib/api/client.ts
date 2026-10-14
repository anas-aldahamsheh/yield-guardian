import createClient from "openapi-fetch";
import { CSRF_HEADER, type paths } from "@yield-guardian/contracts";

import { ApiError, isProblem } from "./errors";

/**
 * A client typed by the API contracts. Every path, parameter and response body is checked
 * against packages/contracts at compile time. `origin` is "" in the browser (same origin) or
 * the API origin on the server.
 */
export function createApi(origin: string, init: Omit<RequestInit, "headers"> = {}) {
  return createClient<paths>({
    baseUrl: origin,
    credentials: "include",
    ...init,
  });
}

export type Api = ReturnType<typeof createApi>;

interface ApiResult<D> {
  data?: D;
  error?: unknown;
  response: Response;
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

/** Await an openapi-fetch call and return its data, or throw an ApiError with the problem. */
export async function unwrap<D>(request: Promise<ApiResult<D>>): Promise<D> {
  let result: ApiResult<D>;
  try {
    result = await request;
  } catch (error) {
    if (isAbort(error)) throw error;
    throw new ApiError(0, null, error instanceof Error ? error.message : "Network error");
  }
  if (result.error !== undefined || !result.response.ok) {
    throw new ApiError(result.response.status, isProblem(result.error) ? result.error : null);
  }
  return result.data as D;
}

/** Headers for a state-changing call: the CSRF token of the cookie session. */
export function csrfHeaders(csrfToken: string | null | undefined): Record<string, string> {
  return csrfToken ? { [CSRF_HEADER]: csrfToken } : {};
}
