// @vitest-environment node
import { NextRequest } from "next/server";

import { contentSecurityPolicy, createNonce } from "@/lib/security";

import { config, proxy } from "./proxy";

function directives(csp: string): Map<string, string> {
  return new Map(
    csp.split(";").map((part) => {
      const [name, ...values] = part.trim().split(/\s+/);
      return [name!, values.join(" ")];
    }),
  );
}

describe("security headers", () => {
  const response = proxy(
    new NextRequest("https://yield-guardian.example/line", {
      headers: { host: "yield-guardian.example" },
    }),
  );
  const csp = response.headers.get("Content-Security-Policy") ?? "";
  const policy = directives(csp);

  it("sets a Content-Security-Policy with a fresh nonce for scripts", () => {
    expect(policy.get("script-src")).toMatch(/^'self' 'nonce-[A-Za-z0-9+/=]{20,}' 'strict-dynamic'$/);
    const other = proxy(new NextRequest("https://yield-guardian.example/"));
    expect(other.headers.get("Content-Security-Policy")).not.toBe(csp);
  });

  it("forbids framing, plugins and base-tag hijacking", () => {
    expect(policy.get("frame-ancestors")).toBe("'none'");
    expect(policy.get("object-src")).toBe("'none'");
    expect(policy.get("base-uri")).toBe("'self'");
    expect(policy.get("default-src")).toBe("'self'");
  });

  it("lets the page reach only its own origin, including the line socket", () => {
    expect(policy.get("connect-src")).toBe(
      "'self' ws://yield-guardian.example wss://yield-guardian.example",
    );
    expect(policy.get("font-src")).toBe("'self'");
    expect(csp).not.toMatch(/https?:\/\//);
  });

  it("does not allow eval in production", () => {
    expect(policy.get("script-src")).not.toContain("unsafe-eval");
  });

  it("passes the nonce to the page render", () => {
    expect(response.headers.get("x-middleware-request-x-nonce")).toMatch(/^[A-Za-z0-9+/=]{20,}$/);
  });

  it("sets the static headers", () => {
    expect(response.headers.get("X-Content-Type-Options")).toBe("nosniff");
    expect(response.headers.get("Referrer-Policy")).toBe("strict-origin-when-cross-origin");
    expect(response.headers.get("X-Frame-Options")).toBe("DENY");
    expect(response.headers.get("Permissions-Policy")).toContain("camera=()");
    expect(response.headers.get("Permissions-Policy")).toContain("microphone=()");
  });

  it("upgrades insecure requests only when the gateway says the page came over HTTPS", () => {
    const viaHttp = proxy(
      new NextRequest("http://yield-guardian.example:8080/line", {
        headers: { host: "yield-guardian.example:8080", "x-forwarded-proto": "http" },
      }),
    );
    expect(viaHttp.headers.get("Content-Security-Policy")).not.toContain("upgrade-insecure-requests");
    expect(csp).not.toContain("upgrade-insecure-requests");
    const viaHttps = proxy(
      new NextRequest("http://web:3000/line", {
        headers: { host: "yield-guardian.example", "x-forwarded-proto": "https, http" },
      }),
    );
    expect(viaHttps.headers.get("Content-Security-Policy")).toContain("upgrade-insecure-requests");
  });

  it("ignores a Host header that is not a host name", () => {
    const value = contentSecurityPolicy({ nonce: createNonce(), host: "evil.example; script-src *" });
    expect(directives(value).get("connect-src")).toBe("'self'");
  });

  it("runs on pages but not on static assets or the healthcheck", () => {
    const source = config.matcher[0]!.source;
    const matcher = new RegExp(`^${source}$`);
    expect(matcher.test("/line")).toBe(true);
    expect(matcher.test("/_next/static/chunks/app.js")).toBe(false);
    expect(matcher.test("/healthz")).toBe(false);
  });
});
