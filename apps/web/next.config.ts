import path from "node:path";
import type { NextConfig } from "next";

/**
 * Dev-only pages (the component playground) are named `page.dev.tsx`. They are routes only in
 * `next dev`, or in a build made with YG_DEV_PLAYGROUND=1 for screenshots. A normal production
 * build never sees them, so development fixtures cannot reach a user.
 */
const devPages = process.env.NODE_ENV !== "production" || process.env.YG_DEV_PLAYGROUND === "1";

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.join(import.meta.dirname, "../.."),
  reactStrictMode: true,
  poweredByHeader: false,
  pageExtensions: devPages ? ["dev.tsx", "tsx", "ts"] : ["tsx", "ts"],
  transpilePackages: ["@yield-guardian/contracts"],
  experimental: {
    optimizePackageImports: ["lucide-react", "d3"],
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), browsing-topics=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
