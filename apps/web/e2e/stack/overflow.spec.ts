import { expect, test } from "@playwright/test";

import { discover } from "./api";

/**
 * At 375 px no route may scroll sideways. The design work (w1/design, merged into main at
 * 06717b8) fixed the overflows on /line, /methods and the home results table, so no case is
 * marked expected-fail. If a known overflow comes back, mark that case with
 * test.fail(true, "<bug, owner>") rather than loosening the check.
 */
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
  { name: "guide", path: () => "/guide" },
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
      const response = await page.goto(path!);
      expect(response?.status()).toBe(200);
      await page.waitForLoadState("networkidle").catch(() => undefined);
      await expect(page.locator("h1")).toHaveCount(1);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow, `${path} scrolls sideways by ${overflow} px`).toBeLessThanOrEqual(1);
    });
  }
});
