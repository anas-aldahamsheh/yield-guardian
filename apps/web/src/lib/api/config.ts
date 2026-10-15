import { API_PREFIX } from "@yield-guardian/contracts";

/**
 * Where the API is.
 *
 * Browsers always call the API on their own origin (`/api/v1/...`): in every
 * deployment a gateway routes those paths to the API, and in development `scripts/gateway.ts`
 * does the same. So the browser bundle contains no API address at all.
 *
 * Server code (server components, route handlers) reads API_INTERNAL_URL at request time, for
 * example http://api:8000 in compose. It is never inlined at build time, and the build never
 * calls the API.
 */

export const DEFAULT_INTERNAL_URL = "http://localhost:8000";

type Env = Record<string, string | undefined>;

/** Base URL for openapi-fetch in the browser: the page's own origin. */
export const BROWSER_API_BASE = "";

/** Origin of the API as the Next.js server reaches it (the generated paths add /api/v1). */
export function serverApiOrigin(env: Env = process.env): string {
  return originOf(env["API_INTERNAL_URL"] || DEFAULT_INTERNAL_URL);
}

/** Accepts an origin or an API base that ends in /api/v1, and returns the origin. */
export function originOf(url: string): string {
  const trimmed = url.replace(/\/+$/, "");
  return trimmed.endsWith(API_PREFIX) ? trimmed.slice(0, -API_PREFIX.length) : trimmed;
}
