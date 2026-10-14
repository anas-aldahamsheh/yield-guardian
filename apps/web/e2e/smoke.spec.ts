import { expect, type Page, test } from "@playwright/test";

/** Every screen loads, has one h1 and a main landmark, and raises no page error or CSP violation. */
const ROUTES: { path: string; heading: RegExp }[] = [
  { path: "/", heading: /./ },
  { path: "/line", heading: /^Line$/ },
  { path: "/investigations", heading: /^Investigations$/ },
  { path: "/investigations/inv_01jae5x9k3m2q7r8s0t1v2w3x4", heading: /./ },
  { path: "/units/1062", heading: /^Unit 1,062$/ },
  { path: "/wafers", heading: /^Wafer lab$/ },
  { path: "/lots", heading: /^Lots$/ },
  { path: "/lots/lot47542", heading: /^Lot lot47542$/ },
  { path: "/sensors?sensor=S060", heading: /^Sensor health$/ },
  { path: "/work-orders", heading: /^Work orders$/ },
  { path: "/work-orders/WO-000012", heading: /./ },
  { path: "/models", heading: /^Models$/ },
  { path: "/methods", heading: /^Methods$/ },
];

function watch(page: Page) {
  const problems: string[] = [];
  page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    const text = m.text();
    if (m.type() === "error" && /Content Security Policy|Refused to|Hydration/i.test(text)) problems.push(`console: ${text}`);
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
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, "no horizontal page scroll").toBeLessThanOrEqual(1);
    expect(problems).toEqual([]);
  });
}

test("an unknown page is a 404 with a way back", async ({ page }) => {
  const response = await page.goto("/does-not-exist");
  expect(response?.status()).toBe(404);
  await expect(page.getByRole("link").first()).toBeVisible();
});

test("health check answers ok", async ({ request }) => {
  const response = await request.get("/healthz");
  expect(response.status()).toBe(200);
  expect(await response.text()).toBe("ok");
});
