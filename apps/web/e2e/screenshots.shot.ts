import { test } from "@playwright/test";

/** Screenshots for docs/screenshots at 1440 and 390 (`pnpm screenshots`): the v2 pages. */
const PAGES = [
  "investigations",
  "investigations?tab=work-orders",
  "investigations/inv_01jae5x9k3m2q7r8s0t1v2w3x4",
  "how",
  "admin",
];
for (const width of [1440, 390]) {
  for (const p of PAGES) {
    test(`${p} at ${width}`, async ({ page }) => {
      await page.setViewportSize({ width, height: width > 600 ? 900 : 844 });
      await page.goto(`/${p}`);
      await page.waitForLoadState("networkidle").catch(() => undefined);
      await page.waitForTimeout(1500);
      const name = p.replace("?tab=", "-").replaceAll("/", "-");
      await page.screenshot({ path: `docs/screenshots/${name}-${width}.png`, fullPage: true });
    });
  }
}
