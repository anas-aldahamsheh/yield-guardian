import { type NextRequest, NextResponse } from "next/server";

import {
  STATIC_SECURITY_HEADERS,
  contentSecurityPolicy,
  createNonce,
  forwardedHttps,
} from "@/lib/security";
import { legacyRedirect } from "@/lib/routes";

/** v1 work order addresses are resolved by their route handler, which looks the order up. */
const WORK_ORDER_PAGE = /^\/work-orders\/[^/]+\/?$/;

/**
 * Sets a Content-Security-Policy with a fresh nonce on every page request. Next.js reads the
 * nonce from the request's CSP header and adds it to its own scripts; the root layout passes it
 * to the theme script. A v1 address is redirected permanently to its v2 place first
 * (lib/routes.ts).
 */
export function proxy(request: NextRequest) {
  const { pathname, searchParams } = request.nextUrl;
  const moved = WORK_ORDER_PAGE.test(pathname) ? null : legacyRedirect(pathname, searchParams);
  // Next needs an absolute URL here, and makes it relative again when it is on the request's
  // own host, so the Location the browser sees is right behind any gateway.
  if (moved) return NextResponse.redirect(new URL(moved, request.url), 308);

  const nonce = createNonce();
  const csp = contentSecurityPolicy({
    nonce,
    host: request.headers.get("x-forwarded-host") ?? request.headers.get("host"),
    dev: process.env.NODE_ENV === "development",
    https: forwardedHttps(request.headers.get("x-forwarded-proto")),
  });

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  for (const { key, value } of STATIC_SECURITY_HEADERS) response.headers.set(key, value);
  return response;
}

export const config = {
  matcher: [
    {
      source: "/((?!_next/static|_next/image|favicon.ico|healthz).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
    // v1 addresses, also when the router prefetches a link to one: the prefetch then follows
    // the redirect instead of getting a 404 whose request never settles in the browser.
    { source: "/line" },
    { source: "/wafers/:path*" },
    { source: "/lots/:path*" },
    { source: "/units/:path*" },
    { source: "/sensors" },
    { source: "/work-orders" },
    { source: "/models" },
    { source: "/methods" },
    { source: "/guide" },
  ],
};
