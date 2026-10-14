import { API_PREFIX, LINE_SOCKET_PATH } from "@yield-guardian/contracts";

/** Default API base for local development (the brief's contract). */
export const DEFAULT_API_URL = "http://localhost:8000/api/v1";

/**
 * The API base the browser uses: NEXT_PUBLIC_API_URL, inlined at build time.
 * It may be absolute (http://localhost:8000/api/v1) or relative (/api/v1) when a reverse proxy
 * serves the web app and the API on one origin.
 */
export function publicApiUrl(): string {
  return (process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL).replace(/\/+$/, "");
}

/**
 * The API base the Next.js server uses. API_INTERNAL_URL lets a container reach the API by its
 * service name; otherwise the public URL is used when it is absolute.
 */
export function serverApiUrl(): string {
  const internal = process.env.API_INTERNAL_URL?.replace(/\/+$/, "");
  if (internal) return internal;
  const pub = publicApiUrl();
  return /^https?:\/\//.test(pub) ? pub : DEFAULT_API_URL;
}

/** Strip the API prefix: the generated `paths` already start with /api/v1. */
export function originOf(apiUrl: string): string {
  return apiUrl.endsWith(API_PREFIX) ? apiUrl.slice(0, -API_PREFIX.length) : apiUrl;
}

/** WebSocket URL of the live line, derived from the API base the browser uses. */
export function lineSocketUrl(location?: Pick<Location, "protocol" | "host">): string {
  const origin = originOf(publicApiUrl());
  if (/^https?:\/\//.test(origin)) {
    return origin.replace(/^http/, "ws") + LINE_SOCKET_PATH;
  }
  if (!location) throw new Error("A relative API URL needs the page location");
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${location.host}${origin}${LINE_SOCKET_PATH}`;
}
