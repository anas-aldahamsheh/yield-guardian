import { test } from "@playwright/test";

import { TEST_DOUBLE } from "../src/mocks/test-doubles";

import { expectAccessible, SCHEMES, settle, VIEWPORTS } from "./axe";

/**
 * axe on every route at 1440 and 375 px, light and dark, on the production build behind the
 * mock gateway. Fails on serious or critical violations, and on any violation at all for How it
 * works and Investigations (`strict`); every finding is logged.
 */
const ROUTES: { path: string; strict?: true }[] = [
  { path: "/" },
  { path: "/how", strict: true },
  { path: "/investigations", strict: true },
  { path: "/investigations?tab=work-orders", strict: true },
  { path: "/investigations?tab=work-orders&order=WO-000012", strict: true },
  { path: "/investigations/inv_01jae5x9k3m2q7r8s0t1v2w3x4", strict: true },
  { path: "/investigations/inv_01jadz4r8c0q2m6t9v1x3b5d7f", strict: true },
  { path: `/investigations/${TEST_DOUBLE.investigationId}`, strict: true },
  { path: "/admin" },
  { path: "/join", strict: true },
];

for (const viewport of VIEWPORTS) {
  for (const scheme of SCHEMES) {
    test.describe(`${viewport.name} px, ${scheme}`, () => {
      test.use({
        viewport: { width: viewport.width, height: viewport.height },
        colorScheme: scheme,
      });

      for (const route of ROUTES) {
        test(`axe ${route.path}`, async ({ page }) => {
          await settle(page, route.path);
          await expectAccessible(
            page,
            `${viewport.name} ${scheme} ${route.path}`,
            undefined,
            route.strict,
          );
        });
      }

      test("axe How it works with every section open and numbers typed", async ({ page }) => {
        await settle(page, "/how");
        for (const summary of await page.locator("#experts details > summary").all())
          await summary.click();
        await page.getByLabel("Wafers per day").fill("100");
        await page.getByLabel("Downtime hour cost").fill("2000");
        await page.getByRole("button", { name: "افتح الكل" }).click();
        await page.waitForLoadState("networkidle").catch(() => undefined);
        await page.waitForTimeout(800);
        await expectAccessible(page, `${viewport.name} ${scheme} /how opened`, undefined, true);
      });

      test("axe the chat sheet", async ({ page }) => {
        await settle(page, "/investigations/inv_01jae5x9k3m2q7r8s0t1v2w3x4");
        await page.getByRole("button", { name: "Ask", exact: true }).click();
        await page.getByRole("dialog").waitFor();
        await page.waitForTimeout(500);
        await expectAccessible(page, `${viewport.name} ${scheme} chat sheet`);
      });

      test("axe the handoff to another device", async ({ page }) => {
        await settle(page, "/");
        await page.getByRole("button", { name: "Continue on another device" }).click();
        await page.getByRole("dialog").locator("[data-handoff-code]").waitFor();
        await page.waitForTimeout(500);
        await expectAccessible(page, `${viewport.name} ${scheme} handoff dialog`);
      });

      test("axe the navigation menu", async ({ page }) => {
        test.skip(viewport.width >= 768, "the menu button shows below 768 px only");
        await settle(page, "/");
        await page.getByRole("button", { name: "Open the menu" }).click();
        await page.getByRole("dialog").waitFor();
        await page.waitForTimeout(500);
        await expectAccessible(page, `${viewport.name} ${scheme} navigation menu`);
      });
    });
  }
}
