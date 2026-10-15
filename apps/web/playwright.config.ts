import { existsSync } from "node:fs";

import { defineConfig, devices } from "@playwright/test";

/**
 * Smoke tests against a production build served with the development fixture API
 * (`pnpm build` first). The fixtures stay outside the build: the gateway serves them.
 * Chromium comes from PW_CHROMIUM or the preinstalled browser; nothing is downloaded.
 */
const PORT = Number(process.env.E2E_PORT ?? 4300);
const NEXT_PORT = Number(process.env.E2E_NEXT_PORT ?? PORT + 1);
const preinstalled = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome";
const executablePath =
  process.env.PW_CHROMIUM ?? (existsSync(preinstalled) ? preinstalled : undefined);

export default defineConfig({
  testDir: "./e2e",
  // e2e/stack runs against the composed stack: playwright.stack.config.ts.
  testIgnore: ["**/stack/**"],
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://localhost:${PORT}`,
    launchOptions: {
      executablePath,
      args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
    },
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "desktop",
      testMatch: /^(?!.*a11y).*\.spec\.ts$/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "mobile",
      testMatch: /smoke\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
      },
    },
    { name: "a11y", testMatch: /a11y\.spec\.ts/, use: { ...devices["Desktop Chrome"] } },
    {
      name: "screenshots",
      testMatch: /screenshots\.shot\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: `pnpm exec tsx scripts/gateway.ts --mode start --mock --stream-delay 0 --port ${PORT} --next-port ${NEXT_PORT}`,
    url: `http://localhost:${PORT}/healthz`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
