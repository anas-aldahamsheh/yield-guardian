/**
 * Security headers the app sets itself, so they hold behind any proxy (status item P7).
 *
 * Scripts run only with the per-request nonce ('strict-dynamic' lets those scripts load the
 * app's chunks). Styles allow inline attributes because React renders `style` props as
 * attributes; style attributes cannot run code. Fonts are self-hosted by next/font, the 3D
 * wafer compiles its shaders in WebGL (no eval, no workers), and the API and the line socket are
 * on the page's own origin.
 */

export interface CspOptions {
  nonce: string;
  /** Host the page was served from, for the WebSocket sources. */
  host?: string | null;
  /** next dev needs eval for React's debugging and a socket for hot reload. */
  dev?: boolean;
  /**
   * The browser reached the site over HTTPS (the gateway's X-Forwarded-Proto). Only then are
   * insecure subresource requests upgraded; a plain-HTTP deployment (for example :8080) must work.
   */
  https?: boolean;
}

/** Host names as they appear in a Host header: letters, digits, dots, dashes and a port. */
const HOST = /^[A-Za-z0-9.-]+(:\d{1,5})?$/;

export function contentSecurityPolicy({
  nonce,
  host,
  dev = false,
  https = false,
}: CspOptions): string {
  const sockets = host && HOST.test(host) ? ` ws://${host} wss://${host}` : "";
  const directives = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    `connect-src 'self'${sockets}`,
    "worker-src 'self' blob:",
    "media-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "manifest-src 'self'",
  ];
  if (https && !dev) directives.push("upgrade-insecure-requests");
  return directives.join("; ");
}

/** Headers for every response, pages and static files alike. */
export const STATIC_SECURITY_HEADERS: readonly { key: string; value: string }[] = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Frame-Options", value: "DENY" },
  {
    key: "Permissions-Policy",
    value: [
      "accelerometer=()",
      "autoplay=()",
      "camera=()",
      "display-capture=()",
      "geolocation=()",
      "gyroscope=()",
      "magnetometer=()",
      "microphone=()",
      "midi=()",
      "payment=()",
      "usb=()",
      "browsing-topics=()",
    ].join(", "),
  },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
];

/** Whether the original request was HTTPS, from the first X-Forwarded-Proto value. */
export function forwardedHttps(forwardedProto: string | null | undefined): boolean {
  return forwardedProto?.split(",")[0]?.trim().toLowerCase() === "https";
}

/** A fresh nonce: 128 random bits, base64. */
export function createNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes));
}
