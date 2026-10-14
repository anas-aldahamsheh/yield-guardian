import path from "node:path";
import type { NextConfig } from "next";

import { STATIC_SECURITY_HEADERS } from "./src/lib/security";

/**
 * Dev-only pages (the component playground) are named `page.dev.tsx`. They are routes only in
 * `next dev`; `next build` always runs with NODE_ENV=production, never compiles them, and so
 * cannot ship development fixtures to a user. There is deliberately no switch to include them.
 */
const devPages = process.env.NODE_ENV === "development";

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.join(import.meta.dirname, "../.."),
  reactStrictMode: true,
  poweredByHeader: false,
  agentRules: false,
  devIndicators: false,
  pageExtensions: devPages ? ["dev.tsx", "tsx", "ts"] : ["tsx", "ts"],
  transpilePackages: ["@yield-guardian/contracts"],
  experimental: {
    optimizePackageImports: ["lucide-react", "d3"],
    // The stylesheet (16 KB compressed) goes into the HTML: no render-blocking request before the
    // first paint. style-src already allows inline styles.
    inlineCss: false,
  },
  async headers() {
    return [{ source: "/:path*", headers: [...STATIC_SECURITY_HEADERS] }];
  },
};

export default nextConfig;
