import { type NextRequest, NextResponse } from "next/server";

import { STATIC_SECURITY_HEADERS, contentSecurityPolicy, createNonce } from "@/lib/security";

/**
 * Sets a Content-Security-Policy with a fresh nonce on every page request. Next.js reads the
 * nonce from the request's CSP header and adds it to its own scripts; the root layout passes it
 * to the theme script.
 */
export function proxy(request: NextRequest) {
  const nonce = createNonce();
  const csp = contentSecurityPolicy({
    nonce,
    host: request.headers.get("x-forwarded-host") ?? request.headers.get("host"),
    dev: process.env.NODE_ENV === "development",
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
  ],
};
