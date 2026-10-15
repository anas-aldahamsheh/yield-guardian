import { mkdirSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { RUN_ID } from "./fixture";
import { GATEWAY, type StoryProxy, startStoryProxy } from "./stub";

/**
 * Screenshots of the Line page for review: 360, 768 and 1440 px, light and dark; idle, mid-run
 * (held before the control charts arrive), finished, and with a station's drawer open. Not a
 * test of behaviour: run on demand with
 *   STORY_SHOTS=<dir> pnpm exec playwright test --project=screenshots e2e/story/story-screenshots.shot.ts
 * With STORY_REAL=1 the page talks to the real runs API behind the gateway (no pacing: the
 * line plays the results as they arrive).
 */
const REAL = process.env.STORY_REAL === "1";
const OUT = process.env.STORY_SHOTS ?? path.join(process.cwd(), "test-results", "story-shots");
const WIDTHS = [360, 768, 1440] as const;
const SCHEMES = ["dark", "light"] as const;

let proxy: StoryProxy;
test.beforeAll(async () => {
  mkdirSync(OUT, { recursive: true });
  proxy = await startStoryProxy(GATEWAY);
});
test.afterAll(async () => proxy.close());

for (const width of WIDTHS) {
  for (const scheme of SCHEMES) {
    test(`line ${width} ${scheme}`, async ({ page }) => {
      test.setTimeout(120_000);
      await page.setViewportSize({ width, height: width < 768 ? 800 : 900 });
      await page.emulateMedia({ colorScheme: scheme });
      if (!REAL) proxy.configure({ pacing: { pace: 500, holdBefore: "control_charts" } });
      const origin = REAL ? GATEWAY : proxy.origin;
      // From the top, so the sticky header sits where it does for a reader.
      const shot = async (name: string, fullPage = true) => {
        if (fullPage) await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({ path: path.join(OUT, `${width}-${scheme}-${name}.png`), fullPage });
      };

      await page.goto(`${origin}/`);
      await page.waitForLoadState("networkidle").catch(() => undefined);
      await shot("idle");

      await page.getByRole("button", { name: "Try a real sample" }).click();
      await expect(page).toHaveURL(REAL ? /run=run_/ : new RegExp(`run=${RUN_ID}`));
      await page.waitForTimeout(3500);
      await shot("mid-run");

      if (!REAL) proxy.release();
      // "Show every result now" shows what has arrived; results that arrive later play in turn,
      // so it is pressed until the run is done and nothing is left to play.
      const showAll = page.getByRole("button", { name: "Show every result now" });
      const again = page.getByRole("button", { name: "Run the same sample again" });
      await expect(async () => {
        if (await showAll.isVisible()) await showAll.click();
        await expect(again).toBeVisible({ timeout: 1_000 });
        await expect(showAll).toBeHidden({ timeout: 1_000 });
      }).toPass({ timeout: 90_000 });
      await page.waitForTimeout(1500);
      // What the reader sees: the line scrolled into view when the run started.
      await shot("finished-view", false);
      await shot("finished");

      await page.getByRole("button", { name: "Open monitoring details" }).click();
      await page.waitForTimeout(800);
      await shot("drawer-monitoring");
      await page.getByRole("button", { name: "Open wafer test details" }).click();
      await page.waitForTimeout(800);
      await shot("drawer-wafers");
    });
  }
}
