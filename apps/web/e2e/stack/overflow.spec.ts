import { expect, test } from "@playwright/test";

import { discover } from "./api";

/**
 * At 375 px no route may scroll sideways. Three known overflows belong to the design work on
 * w1/design and are marked expected-fail here until that branch fixes them; when one is fixed
 * Playwright reports the case as "unexpectedly passed" and the mark comes off.
 */
const KNOWN: Record<string, string> = {
  "/": "w1/design bug: the home results table overflows at 375 px",
  "/line": "w1/design bug: /line overflows at 375 px",
  "/methods": "w1/design bug: /methods overflows at 375 px",
};

type Ids = Awaited<ReturnType<typeof discover>>;
const ROUTES: { name: string; path: (ids: Ids) => string | null }[] = [
  { name: "home", path: () => "/" },
  { name: "line", path: () => "/line" },
  { name: "investigations", path: () => "/investigations" },
  { name: "an investigation", path: (ids) => (ids.investigation ? `/investigations/${ids.investigation}` : null) },
  { name: "a unit", path: (ids) => `/units/${ids.unit}` },
  { name: "wafer lab", path: () => "/wafers" },
  { name: "wafer lab with a wafer", path: (ids) => `/wafers?wafer=${ids.wafer}` },
  { name: "lots", path: () => "/lots" },
  { name: "a lot", path: (ids) => `/lots/${ids.lot}` },
  { name: "sensor health", path: () => "/sensors?sensor=S060" },
  { name: "work orders", path: () => "/work-orders" },
  { name: "a work order", path: (ids) => (ids.workOrder ? `/work-orders/${ids.workOrder}` : null) },
  { name: "models", path: () => "/models" },
  { name: "methods", path: () => "/methods" },
];

test.describe("375 px, no horizontal scroll", () => {
  let ids: Ids;
  test.beforeAll(async ({ request }) => {
    ids = await discover(request);
  });

  for (const route of ROUTES) {
    test(route.name, async ({ page }, info) => {
      const path = route.path(ids);
      test.skip(path === null, "no such record in this database");
      info.annotations.push({ type: "path", description: path! });
      const bug = KNOWN[path!.split("?")[0]!];
      test.fail(bug !== undefined, bug);
      const response = await page.goto(path!);
      expect(response?.status()).toBe(200);
      await page.waitForLoadState("networkidle").catch(() => undefined);
      await expect(page.locator("h1")).toHaveCount(1);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow, `${path} scrolls sideways by ${overflow} px`).toBeLessThanOrEqual(1);
    });
  }
});
