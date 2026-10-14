import { API_PREFIX, LINE_SOCKET_PATH } from "@yield-guardian/contracts";

/** Default API base for local development. */
export const DEFAULT_API_URL = "http://localhost:8000/api/v1";

type Env = Record<string, string | undefined>;

const trimSlash = (url: string) => url.replace(/\/+$/, "");
const isAbsolute = (url: string) => /^https?:\/\//.test(url);

/**
 * The API base the browser uses. The server resolves it for every request and hands it to the
 * client, so one build runs anywhere:
 *
 * 1. API_PUBLIC_URL, read at run time;
 * 2. NEXT_PUBLIC_API_URL, fixed at build time;
 * 3. http://localhost:8000/api/v1.
 *
 * Absolute in development (the API on its own port, which then needs CORS for the web origin);
 * relative (`/api/v1`) when a reverse proxy serves the web app and the API on one origin.
 */
export function publicApiUrl(env: Env = process.env): string {
  return trimSlash(env.API_PUBLIC_URL || process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL);
}

/**
 * The API base the Next.js server uses: API_INTERNAL_URL (for example the compose service name),
 * otherwise the public URL when it is absolute.
 */
export function serverApiUrl(env: Env = process.env): string {
  const internal = env.API_INTERNAL_URL;
  if (internal) return trimSlash(internal);
  const pub = publicApiUrl(env);
  return isAbsolute(pub) ? pub : DEFAULT_API_URL;
}

/** The base openapi-fetch needs: the generated `paths` already start with /api/v1. */
export function originOf(apiUrl: string): string {
  const url = trimSlash(apiUrl);
  return url.endsWith(API_PREFIX) ? url.slice(0, -API_PREFIX.length) : url;
}

/** WebSocket URL of the live line, derived from the browser's API base. */
export function lineSocketUrl(
  apiUrl: string,
  location?: Pick<Location, "protocol" | "host">,
): string {
  const origin = originOf(apiUrl);
  if (isAbsolute(origin)) return origin.replace(/^http/, "ws") + LINE_SOCKET_PATH;
  if (!location) throw new Error("A relative API URL needs the page location");
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${location.host}${origin}${LINE_SOCKET_PATH}`;
}
