import path from "node:path";
import type { NextConfig } from "next";

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
