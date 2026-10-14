import { test } from "@playwright/test";

import { expectAccessible, SCHEMES, settle, VIEWPORTS } from "./axe";

/**
 * axe on every route at 1440 and 375 px, light and dark, on the production build behind the
 * mock gateway. Fails on serious or critical violations; every finding is logged.
 */
const ROUTES = [
  "/",
  "/line",
  "/investigations",
  "/investigations/inv_01jae5x9k3m2q7r8s0t1v2w3x4",
  "/units/1062",
  "/wafers",
  "/wafers?wafer=lot47542-1",
  "/lots",
  "/lots/lot47542",
  "/sensors?sensor=S060",
  "/work-orders",
  "/work-orders/WO-000012",
  "/models",
  "/methods",
  "/guide",
];

for (const viewport of VIEWPORTS) {
  for (const scheme of SCHEMES) {
    test.describe(`${viewport.name} px, ${scheme}`, () => {
      test.use({ viewport: { width: viewport.width, height: viewport.height }, colorScheme: scheme });

      for (const route of ROUTES) {
        test(`axe ${route}`, async ({ page }) => {
          await settle(page, route);
          await expectAccessible(page, `${viewport.name} ${scheme} ${route}`);
        });
      }

      test("axe the chat sheet", async ({ page }) => {
        await settle(page, "/units/1062");
        await page.getByRole("button", { name: "Ask", exact: true }).click();
        await page.getByRole("dialog").waitFor();
        await page.waitForTimeout(500);
        await expectAccessible(page, `${viewport.name} ${scheme} chat sheet`);
      });

      test("axe the navigation menu", async ({ page }) => {
        test.skip(viewport.width >= 1280, "the menu button shows below 1280 px only");
        await settle(page, "/");
        await page.getByRole("button", { name: "Open the menu" }).click();
        await page.getByRole("dialog").waitFor();
        await page.waitForTimeout(500);
        await expectAccessible(page, `${viewport.name} ${scheme} navigation menu`);
      });
    });
  }
}
