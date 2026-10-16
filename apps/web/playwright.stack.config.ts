import { existsSync } from "node:fs";

import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against the composed stack with the real bundles: gateway, web, API and
 * PostgreSQL (deploy/compose). No mocks and no web server here: start the stack first, see
 * docs/E2E-STACK.md. E2E_BASE_URL points at the gateway (default http://localhost:8080).
 * Chromium comes from PW_CHROMIUM or the preinstalled browser; nothing is downloaded.
 */
const preinstalled = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome";
const executablePath =
  process.env.PW_CHROMIUM ?? (existsSync(preinstalled) ? preinstalled : undefined);

export default defineConfig({
  testDir: "./e2e/stack",
  timeout: 90_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: process.env.CI
    ? [["list"], ["html", { open: "never", outputFolder: "playwright-report/stack" }]]
    : "list",
  outputDir: "test-results/stack",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8080",
    launchOptions: {
      executablePath,
      args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
    },
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "desktop",
      testMatch: /(flows|reload|workspace)\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "375",
      testMatch: /overflow\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 375, height: 812 },
        isMobile: true,
        hasTouch: true,
      },
    },
    { name: "a11y", testMatch: /a11y\.spec\.ts/, use: { ...devices["Desktop Chrome"] } },
  ],
});
