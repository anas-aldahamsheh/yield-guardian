import { expect, type Page, test } from "@playwright/test";

import { TEST_DOUBLE } from "../src/mocks/test-doubles";

/**
 * Every screen loads, has one h1 and a main landmark, and raises no page error or CSP violation.
 * v1 addresses redirect (e2e/pages.spec.ts); a followed redirect lands on a screen listed here.
 */
const ROUTES: { path: string; heading: RegExp }[] = [
  { path: "/", heading: /./ },
  { path: "/investigations", heading: /^Investigations$/ },
  { path: "/investigations?tab=work-orders", heading: /^Investigations$/ },
  { path: "/investigations?tab=work-orders&order=WO-000012", heading: /^Investigations$/ },
  { path: "/investigations/inv_01jae5x9k3m2q7r8s0t1v2w3x4", heading: /./ },
  { path: `/investigations/${TEST_DOUBLE.investigationId}`, heading: /./ },
  { path: "/how", heading: /^كيف يعمل Yield Guardian$/ },
  { path: "/admin", heading: /^Model roles$/ },
  { path: "/join", heading: /^Continue on this device$/ },
];

function watch(page: Page) {
  const problems: string[] = [];
  page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    const text = m.text();
    if (m.type() === "error" && /Content Security Policy|Refused to|Hydration/i.test(text))
      problems.push(`console: ${text}`);
  });
  return problems;
}

for (const route of ROUTES) {
  test(`${route.path} renders`, async ({ page }) => {
    const problems = watch(page);
    const response = await page.goto(route.path);
    expect(response?.status()).toBe(200);
    await expect(page.locator("h1")).toHaveCount(1);
    await expect(page.locator("h1")).toHaveText(route.heading);
    await expect(page.locator("main")).toHaveCount(1);
    await page.waitForLoadState("networkidle").catch(() => undefined);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow, "no horizontal page scroll").toBeLessThanOrEqual(1);
    expect(problems).toEqual([]);
  });
}

test("an unknown page is a 404 with a way back", async ({ page }) => {
  const response = await page.goto("/does-not-exist");
  expect(response?.status()).toBe(404);
  await expect(page.getByRole("link").first()).toBeVisible();
});

test("the admin page stays out of search engines", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.locator("meta[name='robots']")).toHaveAttribute("content", /noindex/);
});

test("the join page stays out of search engines and sends no referrer", async ({ page }) => {
  await page.goto("/join");
  await expect(page.locator("meta[name='robots']")).toHaveAttribute("content", /noindex/);
  await expect(page.locator("meta[name='referrer']")).toHaveAttribute("content", "no-referrer");
});

test("health check answers ok", async ({ request }) => {
  const response = await request.get("/healthz");
  expect(response.status()).toBe(200);
  expect(await response.text()).toBe("ok");
});
