import { test } from "@playwright/test";

/** Screenshots for docs/screenshots at 1440 and 390 (`pnpm screenshots`). */
const PAGES = ["line", "investigations", "units/1062", "wafers", "lots/lot47542", "sensors?sensor=S060", "work-orders", "models", "methods"];
for (const width of [1440, 390]) {
  for (const p of PAGES) {
    test(`${p} at ${width}`, async ({ page }) => {
      await page.setViewportSize({ width, height: width > 600 ? 900 : 844 });
      await page.goto(`/${p}`);
      await page.waitForLoadState("networkidle").catch(() => undefined);
      await page.waitForTimeout(1500);
      const name = p.split("?")[0]!.replaceAll("/", "-");
      await page.screenshot({ path: `docs/screenshots/${name}-${width}.png`, fullPage: true });
    });
  }
}
